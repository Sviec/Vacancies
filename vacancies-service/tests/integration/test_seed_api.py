"""Демо-данные сида глазами API: лента, карточка, фильтры, резюме, рекомендации."""

from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import VacancyPosting
from app.enums import EmploymentType, ExperienceLevel, WorkFormat
from app.services.seed import SeedReport
from app.services.seed_data import load_seed_dataset

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("no_app_engine")]

VACANCIES = "/api/v1/vacancies"
RESUMES = "/api/v1/resumes"
RECOMMENDED = "/api/v1/vacancies/recommended"


async def _offer_ids(session: AsyncSession) -> dict[str, str]:
    """offer сида → id канона в БД."""
    result: dict[str, str] = {}
    for item in load_seed_dataset().vacancies:
        vacancy_id = await session.scalar(
            select(VacancyPosting.vacancy_id).where(
                VacancyPosting.source == item.source,
                VacancyPosting.external_id == item.external_id,
            )
        )
        assert vacancy_id is not None, item.key
        result.setdefault(item.offer, str(vacancy_id))
    return result


async def _feed_ids(client: AsyncClient, **params: Any) -> set[str]:
    response = await client.get(VACANCIES, params={"page_size": 100, **params})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] <= 100
    return {item["id"] for item in body["items"]}


async def _resume_ids(client: AsyncClient) -> dict[str, str]:
    items = (await client.get(RESUMES)).json()["items"]
    by_title = {item["title"]: item["id"] for item in items}
    dataset = load_seed_dataset()
    return {r.key: by_title[r.payload.title] for r in dataset.resumes}


@pytest.mark.usefixtures("seeded")
async def test_feed_and_sorts(api_client: AsyncClient) -> None:
    response = await api_client.get(VACANCIES, params={"page_size": 100})
    assert response.status_code == 200
    assert response.json()["total"] >= 60
    for sort in ("relevance", "date", "salary"):
        sorted_response = await api_client.get(VACANCIES, params={"sort": sort, "q": "python"})
        assert sorted_response.status_code == 200, sort
        assert sorted_response.json()["total"] > 0, sort


@pytest.mark.usefixtures("seeded")
async def test_merged_offer_detail(api_client: AsyncClient, db_session: AsyncSession) -> None:
    offers = await _offer_ids(db_session)
    response = await api_client.get(f"{VACANCIES}/{offers['meridian-senior-python']}")
    assert response.status_code == 200
    body = response.json()
    assert body["postings_count"] == 2
    assert {p["source"] for p in body["postings"]} == {"tg_it_jobs", "html_careerhub"}
    assert body["parse_quality"] == "full"


@pytest.mark.usefixtures("seeded")
async def test_filters_meta(api_client: AsyncClient) -> None:
    body = (await api_client.get(f"{VACANCIES}/filters/meta")).json()
    assert len(body["sources"]) == 4
    assert len(body["countries"]) >= 7
    assert {"RUB", "USD", "EUR", "KZT", "GBP"} <= set(body["currencies"])


async def test_resumes_and_rescore(seeded: SeedReport, api_client: AsyncClient) -> None:
    items = (await api_client.get(RESUMES)).json()["items"]
    assert len(items) == 3
    strong = next(r for r in seeded.resumes if r.key == "strong")
    assert items[0]["is_primary"] is True
    assert items[0]["title"] == strong.title
    assert [item["is_primary"] for item in items[1:]] == [False, False]

    first = await api_client.post(f"{RESUMES}/{items[0]['id']}/score")
    second = await api_client.post(f"{RESUMES}/{items[0]['id']}/score")
    assert first.status_code == second.status_code == 200
    assert first.json()["score"] == second.json()["score"] == strong.score
    assert first.json()["score_details"] == second.json()["score_details"]


async def _recommended(client: AsyncClient, resume_id: str) -> list[dict[str, Any]]:
    response = await client.get(RECOMMENDED, params={"resume_id": resume_id, "limit": 10})
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


@pytest.mark.usefixtures("seeded")
async def test_recommendations_differ_by_resume(api_client: AsyncClient) -> None:
    resumes = await _resume_ids(api_client)
    tops = {key: await _recommended(api_client, rid) for key, rid in resumes.items()}
    ids = {key: [item["id"] for item in items] for key, items in tops.items()}
    assert all(len(v) == 10 for v in ids.values())
    assert ids["strong"] != ids["medium"]
    assert ids["strong"] != ids["weak"]
    assert ids["medium"] != ids["weak"]
    assert ids["strong"][0] != ids["weak"][0]

    assert all("python" in item["skills"] for item in tops["strong"][:5])
    remote = [item for item in tops["weak"][:5] if item["work_format"] == "remote"]
    assert len(remote) >= 3
    scores = [item["score"] for item in tops["strong"]]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.usefixtures("seeded")
async def test_hidden_and_saved(api_client: AsyncClient, db_session: AsyncSession) -> None:
    offers = await _offer_ids(db_session)
    hidden = {offers["altair-senior-backend"], offers["altair-head-platform"]}
    saved = {
        offers["meridian-senior-python"],
        offers["sevmarket-senior-python"],
        offers["nevsky-fullstack"],
    }
    assert not hidden & await _feed_ids(api_client)
    assert hidden <= await _feed_ids(api_client, exclude_hidden="false")
    assert await _feed_ids(api_client, saved_only="true") == saved

    resumes = await _resume_ids(api_client)
    response = await api_client.get(RECOMMENDED, params={"resume_id": resumes["strong"]})
    assert not hidden & {item["id"] for item in response.json()["items"]}


async def test_filters_return_results(seeded: SeedReport, api_client: AsyncClient) -> None:
    published_after = (seeded.now - timedelta(days=3)).isoformat()
    cases: list[dict[str, Any]] = [
        {"q": "python"},
        {"q": "аналитик"},
        *({"experience_level": level.value} for level in ExperienceLevel),
        *(
            {"employment_type": kind.value}
            for kind in (
                EmploymentType.FULL_TIME,
                EmploymentType.PART_TIME,
                EmploymentType.CONTRACT,
                EmploymentType.INTERNSHIP,
            )
        ),
        *({"work_format": fmt.value} for fmt in WorkFormat),
        {"country": "Россия"},
        {"country": "Кипр"},
        {"city": "Москва"},
        {"city": "СПб"},
        {"salary_min": 300000},
        *({"salary_currency": code} for code in ("RUB", "USD", "EUR", "KZT", "GBP")),
        *({"source": slug} for slug in seeded.sources_created),
        {"published_after": published_after},
        {"has_salary": "true"},
        {"has_salary": "false"},
        {"relocation_support": "true"},
        {"relocation_support": "false"},
        {"work_format": "remote", "has_salary": "true", "salary_currency": "USD"},
        {"city": "Москва", "experience_level": "senior", "sort": "salary"},
        {"source": "html_jobboard", "relocation_support": "true"},
    ]
    failures: list[str] = []
    for params in cases:
        response = await api_client.get(VACANCIES, params=params)
        if response.status_code != 200:
            failures.append(f"{params}: HTTP {response.status_code} {response.text}")
        elif response.json()["total"] == 0:
            failures.append(f"{params}: empty result")
    assert failures == []
