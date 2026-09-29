"""GET /vacancies/recommended и кэш vacancy_matches (этап 6, живой PostgreSQL)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.config import get_settings
from app.db.models import Vacancy, VacancyMatch
from app.enums import WorkFormat
from app.schemas.recommendations import RecommendationsQuery
from app.schemas.scoring import MatchDetails
from app.services.recommendations import get_recommendations
from factories import ingest_raws, make_raw, make_resume_payload

pytestmark = pytest.mark.integration

URL = "/api/v1/vacancies/recommended"
RESUMES = "/api/v1/resumes"

NOW = datetime.now(UTC)
RECENT = NOW - timedelta(days=1)
TIE = NOW - timedelta(days=2)


def _raw(key: str, title: str, skills: str, fmt: WorkFormat, **extra: Any) -> Any:
    fields: dict[str, Any] = {
        "external_id": key,
        "company": f"Компания {key}",
        "title": title,
        "description_raw": f"Стек: {skills}. Команда {key}.",
        "work_format": fmt,
        "published_at": RECENT,
    }
    fields.update(extra)
    return make_raw(**fields)


@pytest.fixture
async def vacancies(db_session: AsyncSession) -> dict[str, str]:
    raws = {
        "py_remote": _raw(
            "py_remote",
            "Senior Python Developer",
            "Python, FastAPI, PostgreSQL, Docker",
            WorkFormat.REMOTE,
        ),
        "py_office": _raw(
            "py_office", "Python Developer", "Python, Django, PostgreSQL", WorkFormat.OFFICE
        ),
        "fe_remote": _raw(
            "fe_remote", "Senior Frontend Developer", "React, TypeScript, CSS", WorkFormat.REMOTE
        ),
        "fe_office": _raw(
            "fe_office", "Frontend Developer", "React, JavaScript, HTML", WorkFormat.OFFICE
        ),
        "go_a": _raw("go_a", "Go Developer", "Go, Kafka", WorkFormat.HYBRID, published_at=TIE),
        "go_b": _raw("go_b", "Go Developer", "Go, Kafka", WorkFormat.HYBRID, published_at=TIE),
        "no_date": _raw(
            "no_date", "Java Developer", "Java, Spring", WorkFormat.HYBRID, published_at=None
        ),
    }
    ids = await ingest_raws(db_session, *raws.values())
    return {key: str(vacancy_id) for key, vacancy_id in zip(raws, ids, strict=True)}


async def _resume(client: AsyncClient, **overrides: Any) -> str:
    response = await client.post(RESUMES, json=make_resume_payload(**overrides))
    assert response.status_code == 201, response.text
    resume_id: str = response.json()["id"]
    return resume_id


@pytest.fixture
async def backend(api_client: AsyncClient) -> str:
    skills = [{"skill": s} for s in ("Python", "FastAPI", "PostgreSQL", "Docker", "Django")]
    return await _resume(api_client, title="Backend", skills=skills)


@pytest.fixture
async def frontend(api_client: AsyncClient, backend: str) -> str:
    skills = [{"skill": s} for s in ("React", "TypeScript", "CSS", "JavaScript", "HTML")]
    return await _resume(
        api_client,
        title="Frontend",
        target_position="Senior Frontend Developer",
        skills=skills,
    )


async def _get(client: AsyncClient, query: str = "") -> dict[str, Any]:
    response = await client.get(f"{URL}?{query}" if query else URL)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _ids(body: dict[str, Any]) -> list[str]:
    return [item["id"] for item in body["items"]]


async def _matches(
    session: AsyncSession, resume_id: str
) -> dict[uuid.UUID, tuple[float, datetime]]:
    stmt = select(VacancyMatch.vacancy_id, VacancyMatch.score, VacancyMatch.computed_at).where(
        VacancyMatch.resume_id == uuid.UUID(resume_id)
    )
    rows = (await session.execute(stmt)).all()
    return {row.vacancy_id: (row.score, row.computed_at) for row in rows}


# --- Выбор резюме ---


async def test_primary_resume_by_default(
    api_client: AsyncClient, vacancies: dict[str, str], backend: str, frontend: str
) -> None:
    body = await _get(api_client)
    assert body["resume_id"] == backend
    assert body["items"][0]["id"] == vacancies["py_remote"]
    item = body["items"][0]
    assert 0 <= item["score"] <= 100
    details = MatchDetails.model_validate(item["match_details"])
    assert details.skills.matched == ["docker", "fastapi", "postgresql", "python"]
    for field in ("title", "company", "skills", "postings_count", "user_actions"):
        assert field in item


async def test_resume_id_changes_order(
    api_client: AsyncClient, vacancies: dict[str, str], backend: str, frontend: str
) -> None:
    default = await _get(api_client)
    other = await _get(api_client, f"resume_id={frontend}")
    assert other["resume_id"] == frontend
    assert other["items"][0]["id"] == vacancies["fe_remote"]
    assert _ids(default) != _ids(other)


async def test_switching_primary_changes_default(
    api_client: AsyncClient, vacancies: dict[str, str], backend: str, frontend: str
) -> None:
    before = await _get(api_client)
    patched = await api_client.patch(f"{RESUMES}/{frontend}", json={"is_primary": True})
    assert patched.status_code == 200
    after = await _get(api_client)
    assert after["resume_id"] == frontend
    assert after["items"][0]["id"] == vacancies["fe_remote"]
    assert _ids(after) != _ids(before)


# --- Сортировка и limit ---


async def test_sorted_by_score_with_deterministic_ties(
    api_client: AsyncClient, vacancies: dict[str, str], backend: str
) -> None:
    first = await _get(api_client)
    scores = [item["score"] for item in first["items"]]
    assert scores == sorted(scores, reverse=True)
    assert len(first["items"]) == len(vacancies)
    assert _ids(await _get(api_client)) == _ids(first)

    by_id = {item["id"]: item for item in first["items"]}
    go = sorted([vacancies["go_a"], vacancies["go_b"]])
    assert by_id[go[0]]["score"] == by_id[go[1]]["score"]
    ids = _ids(first)
    assert ids.index(go[0]) == ids.index(go[1]) - 1


async def test_limit(api_client: AsyncClient, vacancies: dict[str, str], backend: str) -> None:
    full = await _get(api_client)
    limited = await _get(api_client, "limit=2")
    assert _ids(limited) == _ids(full)[:2]


# --- Действия и активность ---


async def test_hidden_saved_and_inactive(
    api_client: AsyncClient,
    db_session: AsyncSession,
    vacancies: dict[str, str],
    backend: str,
) -> None:
    hide = await api_client.post(
        f"/api/v1/vacancies/{vacancies['py_remote']}/action", json={"action": "hidden"}
    )
    assert hide.status_code == 200
    save = await api_client.post(
        f"/api/v1/vacancies/{vacancies['py_office']}/action", json={"action": "saved"}
    )
    assert save.status_code == 200
    await db_session.execute(
        update(Vacancy).where(Vacancy.id == uuid.UUID(vacancies["no_date"])).values(is_active=False)
    )
    await db_session.flush()

    default = await _get(api_client)
    assert vacancies["py_remote"] not in _ids(default)
    assert vacancies["no_date"] not in _ids(default)
    saved = next(i for i in default["items"] if i["id"] == vacancies["py_office"])
    assert saved["user_actions"] == ["saved"]

    shown = await _get(api_client, "exclude_hidden=false")
    hidden = next(i for i in shown["items"] if i["id"] == vacancies["py_remote"])
    assert hidden["user_actions"] == ["hidden"]
    assert vacancies["no_date"] not in _ids(shown)


# --- Кэш vacancy_matches ---


async def test_cache_rows_and_computed_at(
    api_client: AsyncClient,
    db_session: AsyncSession,
    vacancies: dict[str, str],
    backend: str,
) -> None:
    await _get(api_client)
    first = await _matches(db_session, backend)
    assert len(first) == len(vacancies)

    await _get(api_client)
    assert await _matches(db_session, backend) == first


async def test_patch_skills_drops_and_rebuilds_cache(
    api_client: AsyncClient,
    db_session: AsyncSession,
    vacancies: dict[str, str],
    backend: str,
) -> None:
    await _get(api_client)
    py_remote = uuid.UUID(vacancies["py_remote"])
    old_score = (await _matches(db_session, backend))[py_remote][0]

    patched = await api_client.patch(f"{RESUMES}/{backend}", json={"skills": [{"skill": "Go"}]})
    assert patched.status_code == 200
    assert await _matches(db_session, backend) == {}

    await _get(api_client)
    rebuilt = await _matches(db_session, backend)
    assert len(rebuilt) == len(vacancies)
    assert rebuilt[py_remote][0] < old_score


async def test_new_vacancy_appears_in_feed_and_cache(
    api_client: AsyncClient,
    db_session: AsyncSession,
    vacancies: dict[str, str],
    backend: str,
) -> None:
    await _get(api_client)
    (new_id,) = await ingest_raws(
        db_session, _raw("py_new", "Python Backend Engineer", "Python, FastAPI", WorkFormat.REMOTE)
    )
    body = await _get(api_client)
    assert str(new_id) in _ids(body)
    assert new_id in await _matches(db_session, backend)
    assert len(await _matches(db_session, backend)) == len(vacancies) + 1


async def test_later_now_updates_only_changed_rows(
    api_client: AsyncClient,
    db_session: AsyncSession,
    vacancies: dict[str, str],
    backend: str,
) -> None:
    await _get(api_client)
    before = await _matches(db_session, backend)

    later = datetime.now(UTC) + timedelta(days=10)
    result = await get_recommendations(
        db_session, get_settings().demo_user_id, RecommendationsQuery(), now=later
    )
    assert result.resume_id == uuid.UUID(backend)
    after = await _matches(db_session, backend)

    no_date = uuid.UUID(vacancies["no_date"])
    assert after[no_date] == before[no_date]
    for key in ("py_remote", "py_office", "go_a"):
        vacancy_id = uuid.UUID(vacancies[key])
        assert after[vacancy_id][0] < before[vacancy_id][0]
        assert after[vacancy_id][1] == later


# --- Пустые и ошибочные запросы ---


async def test_no_resume_is_empty_200(api_client: AsyncClient, vacancies: dict[str, str]) -> None:
    assert await _get(api_client) == {"resume_id": None, "items": []}


async def test_foreign_and_missing_resume_are_404(
    api_client: AsyncClient, app_for_db: FastAPI, backend: str
) -> None:
    missing = uuid.uuid4()
    response = await api_client.get(f"{URL}?resume_id={missing}")
    assert response.status_code == 404
    assert response.json()["error"]["details"] == {"resource": "resume", "id": str(missing)}

    app_for_db.dependency_overrides[get_current_user_id] = uuid.uuid4
    foreign = await api_client.get(f"{URL}?resume_id={backend}")
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize("query", ["limit=0", "limit=201", "resume_id=x", "sort=score"])
async def test_invalid_query_is_422(api_client: AsyncClient, query: str) -> None:
    response = await api_client.get(f"{URL}?{query}")
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert isinstance(error["details"], dict)


async def test_match_rows_count_matches_active(
    api_client: AsyncClient,
    db_session: AsyncSession,
    vacancies: dict[str, str],
    backend: str,
) -> None:
    await _get(api_client, "limit=1")
    # limit ограничивает выдачу, но кэш считается по всем кандидатам.
    count = await db_session.scalar(
        select(func.count()).where(VacancyMatch.resume_id == uuid.UUID(backend))
    )
    assert count == len(vacancies)
