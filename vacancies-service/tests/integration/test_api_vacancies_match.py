"""Лента `/vacancies` с `resume_id`, `sort=match` и списком источников (этап 8)."""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import VacancyMatch, VacancyPosting
from app.services.seed_data import load_seed_dataset

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("seeded")]

VACANCIES = "/api/v1/vacancies"
RESUMES = "/api/v1/resumes"
RECOMMENDED = "/api/v1/vacancies/recommended"
MERGED_OFFER = "meridian-senior-python"


async def _resume_ids(client: AsyncClient) -> dict[str, str]:
    items = (await client.get(RESUMES)).json()["items"]
    by_title = {item["title"]: item["id"] for item in items}
    return {r.key: by_title[r.payload.title] for r in load_seed_dataset().resumes}


async def _offer_id(session: AsyncSession, offer: str) -> str:
    item = next(v for v in load_seed_dataset().vacancies if v.offer == offer)
    vacancy_id = await session.scalar(
        select(VacancyPosting.vacancy_id).where(
            VacancyPosting.source == item.source, VacancyPosting.external_id == item.external_id
        )
    )
    assert vacancy_id is not None
    return str(vacancy_id)


async def _feed(client: AsyncClient, **params: Any) -> dict[str, Any]:
    response = await client.get(VACANCIES, params={"page_size": 100, **params})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def _recommended(client: AsyncClient, resume_id: str, limit: int) -> list[dict[str, Any]]:
    response = await client.get(RECOMMENDED, params={"resume_id": resume_id, "limit": limit})
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


async def test_without_resume_no_match_and_sources(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    body = await _feed(api_client)
    assert body["items"]
    assert all(item["match_score"] is None for item in body["items"])
    assert all(item["match_details"] is None for item in body["items"])
    assert all(item["sources"] == sorted(set(item["sources"])) for item in body["items"])
    assert all(item["source"] in item["sources"] for item in body["items"])

    offer = await _offer_id(db_session, MERGED_OFFER)
    merged = next(item for item in body["items"] if item["id"] == offer)
    assert merged["sources"] == ["html_careerhub", "tg_it_jobs"]


async def test_match_score_equals_recommended(api_client: AsyncClient) -> None:
    strong = (await _resume_ids(api_client))["strong"]
    body = await _feed(api_client, resume_id=strong)
    assert all(item["match_score"] is not None for item in body["items"])
    assert all(item["match_details"] is not None for item in body["items"])
    scores = {item["id"]: item["score"] for item in await _recommended(api_client, strong, 200)}
    for item in body["items"]:
        assert item["match_score"] == scores[item["id"]]


async def test_sort_match_order_equals_recommended(api_client: AsyncClient) -> None:
    resumes = await _resume_ids(api_client)
    orders: dict[str, list[str]] = {}
    for key in ("strong", "medium", "weak"):
        body = await _feed(api_client, resume_id=resumes[key], sort="match")
        ids = [item["id"] for item in body["items"]]
        recommended = [item["id"] for item in await _recommended(api_client, resumes[key], 100)]
        assert ids == recommended, key
        scores = [item["match_score"] for item in body["items"]]
        assert scores == sorted(scores, reverse=True), key
        orders[key] = ids

    # п. 11.3 ТЗ: смена резюме меняет порядок и лидера.
    assert orders["strong"] != orders["weak"]
    assert orders["strong"][0] != orders["weak"][0]


async def test_sort_match_with_filters(api_client: AsyncClient) -> None:
    strong = (await _resume_ids(api_client))["strong"]
    filters = {"work_format": "remote", "has_salary": "true"}
    body = await _feed(api_client, resume_id=strong, sort="match", **filters)
    assert body["items"]
    for item in body["items"]:
        assert item["work_format"] == "remote"
        assert item["salary_min"] is not None or item["salary_max"] is not None
    scores = [item["match_score"] for item in body["items"]]
    assert scores == sorted(scores, reverse=True)
    assert body["total"] == (await _feed(api_client, **filters))["total"]


async def test_sort_match_pagination(api_client: AsyncClient) -> None:
    strong = (await _resume_ids(api_client))["strong"]
    full = await _feed(api_client, resume_id=strong, sort="match")
    pages: list[str] = []
    for page in (1, 2):
        body = await _feed(api_client, resume_id=strong, sort="match", page=page, page_size=10)
        assert body["total"] == full["total"]
        assert (body["page"], body["page_size"]) == (page, 10)
        pages.extend(item["id"] for item in body["items"])
    assert pages == [item["id"] for item in full["items"][:20]]


async def test_sort_match_errors(api_client: AsyncClient) -> None:
    response = await api_client.get(VACANCIES, params={"sort": "match"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    missing = await api_client.get(VACANCIES, params={"resume_id": str(uuid.uuid4())})
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"


async def test_other_users_resume_is_404(
    api_client: AsyncClient, request: pytest.FixtureRequest
) -> None:
    strong = (await _resume_ids(api_client))["strong"]
    request.getfixturevalue("other_user")
    for params in ({"resume_id": strong}, {"resume_id": strong, "sort": "match"}):
        response = await api_client.get(VACANCIES, params=params)
        assert response.status_code == 404, params
        assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_detail_match_score(api_client: AsyncClient, db_session: AsyncSession) -> None:
    strong = (await _resume_ids(api_client))["strong"]
    offer = await _offer_id(db_session, MERGED_OFFER)
    feed = await _feed(api_client, resume_id=strong)
    in_feed = next(item for item in feed["items"] if item["id"] == offer)

    detail = (await api_client.get(f"{VACANCIES}/{offer}", params={"resume_id": strong})).json()
    assert detail["match_score"] == in_feed["match_score"]
    assert detail["match_details"] == in_feed["match_details"]

    plain = (await api_client.get(f"{VACANCIES}/{offer}")).json()
    assert plain["match_score"] is None
    assert plain["match_details"] is None


async def test_repeat_get_keeps_computed_at(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    strong = (await _resume_ids(api_client))["strong"]

    async def _computed() -> dict[uuid.UUID, Any]:
        stmt = select(VacancyMatch.vacancy_id, VacancyMatch.computed_at).where(
            VacancyMatch.resume_id == uuid.UUID(strong)
        )
        return {row.vacancy_id: row.computed_at for row in await db_session.execute(stmt)}

    await _feed(api_client, resume_id=strong, sort="match")
    first = await _computed()
    assert first
    await _feed(api_client, resume_id=strong, sort="match")
    assert await _computed() == first
