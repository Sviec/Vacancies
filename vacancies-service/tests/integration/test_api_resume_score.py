"""POST /resumes/{id}/score и автоматический пересчёт оценки (этап 6, живой PostgreSQL)."""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.models import Resume
from app.schemas.scoring import ResumeScoreDetails, ScoreCriterionKey
from factories import ingest_raws, make_raw, make_resume_payload

pytestmark = pytest.mark.integration

URL = "/api/v1/resumes"
OLD = datetime(2026, 1, 1, 9, tzinfo=UTC)


async def _create(client: AsyncClient, **overrides: Any) -> dict[str, Any]:
    response = await client.post(URL, json=make_resume_payload(**overrides))
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def _score(client: AsyncClient, resume_id: str) -> dict[str, Any]:
    response = await client.post(f"{URL}/{resume_id}/score")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def _row(session: AsyncSession, resume_id: str) -> Resume:
    stmt = (
        select(Resume)
        .where(Resume.id == uuid.UUID(resume_id))
        .execution_options(populate_existing=True)
    )
    return (await session.execute(stmt)).scalar_one()


async def _seed(session: AsyncSession, python: int, other: int) -> None:
    raws = [
        make_raw(
            external_id=f"py{i}",
            company=f"Python Co {i}",
            title="Senior Python Developer",
            description_raw=f"Python, FastAPI, PostgreSQL, Redis. Команда {i}.",
        )
        for i in range(python)
    ]
    raws += [
        make_raw(
            external_id=f"fe{i}",
            company=f"Front Co {i}",
            title="Frontend Developer",
            description_raw=f"React, TypeScript, CSS. Команда {i}.",
        )
        for i in range(other)
    ]
    await ingest_raws(session, *raws)


def _dump(details: dict[str, Any]) -> str:
    return json.dumps(details, sort_keys=True, ensure_ascii=False)


async def test_score_endpoint_persists_valid_details(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    created = await _create(api_client)
    body = await _score(api_client, created["id"])
    assert set(body) == {"score", "recommendations", "score_details"}
    assert [c["key"] for c in body["score_details"]] == [k.value for k in ScoreCriterionKey]
    assert 0 <= body["score"] <= 10
    assert all("issues" in c for c in body["score_details"])

    row = await _row(db_session, created["id"])
    assert row.score == body["score"]
    details = ResumeScoreDetails.model_validate(row.score_details)
    assert details.score == body["score"]
    assert details.recommendations == body["recommendations"]


async def test_score_is_reproducible_and_keeps_updated_at(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed(db_session, python=5, other=2)
    created = await _create(api_client)
    # now() в PostgreSQL — время начала транзакции, а тест целиком в одной
    # транзакции; поэтому штамп сдвигается вручную, иначе проверка пустая.
    await db_session.execute(
        update(Resume).where(Resume.id == uuid.UUID(created["id"])).values(updated_at=OLD)
    )
    await db_session.flush()

    first = await _score(api_client, created["id"])
    first_row = await _row(db_session, created["id"])
    first_details = _dump(first_row.score_details)
    second = await _score(api_client, created["id"])
    second_row = await _row(db_session, created["id"])
    assert second == first
    assert _dump(second_row.score_details) == first_details
    assert first_row.updated_at == second_row.updated_at == OLD


@pytest.mark.parametrize(
    ("python", "other", "basis", "sample"),
    [(5, 2, "target_position", 5), (3, 2, "all_vacancies", 5), (0, 0, "none", 0)],
)
async def test_market_basis(
    api_client: AsyncClient,
    db_session: AsyncSession,
    python: int,
    other: int,
    basis: str,
    sample: int,
) -> None:
    await _seed(db_session, python=python, other=other)
    created = await _create(api_client, target_position="Senior Python Developer")
    await _score(api_client, created["id"])
    market = (await _row(db_session, created["id"])).score_details["market"]
    assert (market["basis"], market["sample_size"]) == (basis, sample)
    if basis == "target_position":
        assert "react" not in market["top_skills"]
        assert market["top_skills"][0] == "fastapi"
    if basis == "none":
        assert market["top_skills"] == []


async def test_market_top_skills_order(api_client: AsyncClient, db_session: AsyncSession) -> None:
    await _seed(db_session, python=3, other=2)
    created = await _create(api_client, target_position=None)
    await _score(api_client, created["id"])
    market = (await _row(db_session, created["id"])).score_details["market"]
    # Частота DESC (python-навыки ×3, react-навыки ×2), при равенстве — по алфавиту.
    assert market["top_skills"] == [
        "fastapi",
        "postgresql",
        "python",
        "redis",
        "css",
        "react",
        "typescript",
    ]


async def test_missing_and_foreign_resume_are_404(
    api_client: AsyncClient, app_for_db: FastAPI
) -> None:
    missing = uuid.uuid4()
    response = await api_client.post(f"{URL}/{missing}/score")
    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "NOT_FOUND",
        "message": "Requested resource was not found",
        "details": {"resource": "resume", "id": str(missing)},
    }

    created = await _create(api_client)
    app_for_db.dependency_overrides[get_current_user_id] = uuid.uuid4
    foreign = await api_client.post(f"{URL}/{created['id']}/score")
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "NOT_FOUND"


async def test_invalid_uuid_is_422(api_client: AsyncClient) -> None:
    response = await api_client.post(f"{URL}/not-a-uuid/score")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_create_scores_immediately(api_client: AsyncClient) -> None:
    created = await _create(api_client)
    assert isinstance(created["score"], float)
    assert 0 <= created["score"] <= 10
    ResumeScoreDetails.model_validate(created["score_details"])


async def test_patch_summary_rescores_and_title_does_not(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    created = await _create(api_client, summary=None)
    before = created["score"]

    renamed = await api_client.patch(f"{URL}/{created['id']}", json={"title": "Другое имя"})
    assert renamed.status_code == 200
    assert renamed.json()["score"] == before

    with_summary = await api_client.patch(f"{URL}/{created['id']}", json={"summary": "О себе"})
    assert with_summary.status_code == 200
    body = with_summary.json()
    # Полнота 4/5 → 5/5: +0.4.
    assert body["score"] == pytest.approx(before + 0.4)
    assert (await _row(db_session, created["id"])).score == body["score"]
