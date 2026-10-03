"""POST /resumes/generate и /tailor, устойчивость score к ошибке формулировки."""

import uuid
from collections.abc import Sequence
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.llm import MockLLMAdapter
from app.api.deps import get_current_user_id, get_llm_adapter
from app.db.models import Resume, Vacancy
from app.schemas.adapters import CriterionFailure
from app.schemas.ai import ResumeDraft, ResumeGenerateRequest
from app.schemas.scoring import ScoreCriterionKey, ScoreIssue
from app.services.resume_scorer import render_recommendation
from app.utils.errors import ExternalServiceError, LLMResponseInvalidError
from factories import ingest_raws, make_raw, make_resume_payload

pytestmark = pytest.mark.integration

URL = "/api/v1/resumes"


class _InvalidGenerate(MockLLMAdapter):
    async def generate_resume(self, _request: ResumeGenerateRequest) -> ResumeDraft:
        raise LLMResponseInvalidError(details={"reason": "test"})


class _BlankTitle(MockLLMAdapter):
    async def generate_resume(self, request: ResumeGenerateRequest) -> ResumeDraft:
        draft = await super().generate_resume(request)
        return draft.model_copy(update={"title": "   "})


class _FailPhrases(MockLLMAdapter):
    def __init__(self) -> None:
        self.called = False

    async def phrase_recommendations(self, _failures: Sequence[CriterionFailure]) -> list[str]:
        self.called = True
        raise ExternalServiceError(details={"service": "llm", "reason": "test"})


def _assert_error(response: Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    error: dict[str, Any] = response.json()["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str)
    assert isinstance(error["details"], dict)
    return error


async def _resume_count(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(Resume)) or 0)


async def test_generate_creates_resume_with_generated_origin(api_client: AsyncClient) -> None:
    response = await api_client.post(
        f"{URL}/generate",
        json={"raw_text": "три года python", "target_position": "  Analyst  "},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["origin"] == "generated"
    assert body["is_primary"] is True
    assert body["title"] == "Analyst"
    assert body["target_position"] == "Analyst"
    assert body["summary"] == "Черновик резюме из mock-адаптера."
    assert body["experience"][0]["company"] == "Mock Lab"


async def test_generate_empty_raw_text_is_422(api_client: AsyncClient) -> None:
    response = await api_client.post(f"{URL}/generate", json={"raw_text": ""})
    _assert_error(response, 422, "VALIDATION_ERROR")


async def test_generate_invalid_llm_is_502_and_does_not_persist(
    api_client: AsyncClient, app_for_db: FastAPI, db_session: AsyncSession
) -> None:
    assert await _resume_count(db_session) == 0
    app_for_db.dependency_overrides[get_llm_adapter] = lambda: _InvalidGenerate()
    response = await api_client.post(
        f"{URL}/generate",
        json={"raw_text": "текст", "target_position": None},
    )
    error = _assert_error(response, 502, "LLM_RESPONSE_INVALID")
    assert error["details"]["reason"] == "test"
    assert await _resume_count(db_session) == 0


async def test_generate_draft_outside_resume_create_is_502(
    api_client: AsyncClient, app_for_db: FastAPI, db_session: AsyncSession
) -> None:
    app_for_db.dependency_overrides[get_llm_adapter] = lambda: _BlankTitle()
    response = await api_client.post(f"{URL}/generate", json={"raw_text": "текст"})
    error = _assert_error(response, 502, "LLM_RESPONSE_INVALID")
    assert error["details"]["reason"] == "draft_does_not_match_resume_create"
    assert await _resume_count(db_session) == 0


async def test_tailor_keeps_origin_and_rewrites_summary(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    created_response = await api_client.post(URL, json=make_resume_payload())
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()
    (vacancy_id,) = await ingest_raws(db_session, make_raw())
    vacancy = await db_session.get(Vacancy, vacancy_id)
    assert vacancy is not None
    expected = f"Под вакансию «{vacancy.title}». Навыки: {', '.join(vacancy.skills)}."

    response = await api_client.post(
        f"{URL}/{created['id']}/tailor",
        json={"vacancy_id": str(vacancy_id)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["origin"] == "manual"
    assert body["is_primary"] is created["is_primary"]
    assert body["summary"] == expected
    assert body["title"] == created["title"]
    assert [item["company"] for item in body["experience"]] == [
        item["company"] for item in created["experience"]
    ]
    assert [item["description"] for item in body["experience"]] == [
        item["description"] for item in created["experience"]
    ]


async def test_tailor_missing_vacancy_is_404(api_client: AsyncClient) -> None:
    created_response = await api_client.post(URL, json=make_resume_payload(title="Своё"))
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()
    response = await api_client.post(
        f"{URL}/{created['id']}/tailor",
        json={"vacancy_id": str(uuid.uuid4())},
    )
    error = _assert_error(response, 404, "NOT_FOUND")
    assert error["details"]["resource"] == "vacancy"
    again = await api_client.get(f"{URL}/{created['id']}")
    assert again.status_code == 200
    assert again.json()["summary"] == created["summary"]


async def test_tailor_foreign_resume_is_404(
    api_client: AsyncClient, app_for_db: FastAPI, db_session: AsyncSession
) -> None:
    created_response = await api_client.post(URL, json=make_resume_payload(title="Чужое"))
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()
    (vacancy_id,) = await ingest_raws(db_session, make_raw(external_id="foreign-1"))
    app_for_db.dependency_overrides[get_current_user_id] = lambda: uuid.uuid4()
    response = await api_client.post(
        f"{URL}/{created['id']}/tailor",
        json={"vacancy_id": str(vacancy_id)},
    )
    error = _assert_error(response, 404, "NOT_FOUND")
    assert error["details"]["resource"] == "resume"


async def test_score_keeps_templates_when_phrasing_fails(
    api_client: AsyncClient, app_for_db: FastAPI
) -> None:
    created_response = await api_client.post(URL, json={"title": "Пустое"})
    assert created_response.status_code == 201, created_response.text
    resume_id = created_response.json()["id"]
    first = await api_client.post(f"{URL}/{resume_id}/score")
    assert first.status_code == 200, first.text
    broken = _FailPhrases()
    app_for_db.dependency_overrides[get_llm_adapter] = lambda: broken
    second = await api_client.post(f"{URL}/{resume_id}/score")
    assert second.status_code == 200, second.text
    assert broken.called
    before = first.json()
    body = second.json()
    assert body["score"] == before["score"]
    assert body["recommendations"] == before["recommendations"]
    assert any(item["recommendation"] is not None for item in body["score_details"])
    for item, previous in zip(body["score_details"], before["score_details"], strict=True):
        issues = [ScoreIssue.model_validate(issue) for issue in item["issues"]]
        expected = render_recommendation(ScoreCriterionKey(item["key"]), issues)
        assert item["recommendation"] == expected
        assert item["issues"] == previous["issues"]
        assert item["points"] == previous["points"]
        assert item["weight"] == previous["weight"]
