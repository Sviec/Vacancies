"""CRUD резюме через HTTP поверх живого PostgreSQL (этап 5)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.models import Resume, VacancyMatch
from factories import ingest_raws, make_raw, make_resume_payload

pytestmark = pytest.mark.integration

URL = "/api/v1/resumes"
OLD = datetime(2026, 1, 1, 9, tzinfo=UTC)


async def _create(client: AsyncClient, **overrides: Any) -> dict[str, Any]:
    response = await client.post(URL, json=make_resume_payload(**overrides))
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def _get(client: AsyncClient, resume_id: str) -> dict[str, Any]:
    response = await client.get(f"{URL}/{resume_id}")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def _set_updated_at(session: AsyncSession, resume_id: str, moment: datetime) -> None:
    await session.execute(
        update(Resume).where(Resume.id == uuid.UUID(resume_id)).values(updated_at=moment)
    )
    await session.flush()


def _assert_error(response: Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    error: dict[str, Any] = response.json()["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str)
    assert isinstance(error["details"], dict)
    return error


# --- создание и is_primary ---


async def test_first_resume_is_primary_and_manual(api_client: AsyncClient) -> None:
    body = await _create(api_client, is_primary=False)
    assert body["is_primary"] is True
    assert body["origin"] == "manual"
    assert body["score"] is None
    assert body["contacts"]["email"] == "dev@example.com"


async def test_second_primary_takes_over_without_touching_old_updated_at(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    first = await _create(api_client, title="Первое")
    await _set_updated_at(db_session, first["id"], OLD)

    second = await _create(api_client, title="Второе", is_primary=True)
    assert second["is_primary"] is True

    old = await _get(api_client, first["id"])
    assert old["is_primary"] is False
    assert datetime.fromisoformat(old["updated_at"]) == OLD


async def test_non_primary_second_resume(api_client: AsyncClient) -> None:
    await _create(api_client, title="Первое")
    second = await _create(api_client, title="Второе", is_primary=False)
    assert second["is_primary"] is False


async def test_list_order_and_shape(api_client: AsyncClient, db_session: AsyncSession) -> None:
    primary = await _create(api_client, title="Основное")
    older = await _create(api_client, title="Старое")
    newer = await _create(api_client, title="Новое")
    await _set_updated_at(db_session, primary["id"], OLD)
    await _set_updated_at(db_session, older["id"], OLD + timedelta(days=1))
    await _set_updated_at(db_session, newer["id"], OLD + timedelta(days=2))

    response = await api_client.get(URL)
    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == [primary["id"], newer["id"], older["id"]]
    assert set(items[0]) == {
        "id",
        "title",
        "target_position",
        "is_primary",
        "origin",
        "score",
        "created_at",
        "updated_at",
    }


async def test_sections_order_and_skill_canonicalization(api_client: AsyncClient) -> None:
    created = await _create(api_client)
    body = await _get(api_client, created["id"])
    # Опыт — свежий первым; навыки и языки — по алфавиту.
    assert [e["company"] for e in body["experience"]] == ["Ozon", "Яндекс"]
    assert [(s["skill"], s["level"]) for s in body["skills"]] == [
        ("docker", 4),
        ("javascript", 3),
        ("python", 5),
    ]
    assert [lang["language"] for lang in body["languages"]] == ["English", "Русский"]
    assert body["education"][0]["institution"] == "МГУ"
    assert body["courses"][0]["provider"] == "Slurm"


# --- PATCH ---


async def test_patch_scalars_only_keeps_sections(api_client: AsyncClient) -> None:
    created = await _create(api_client)
    response = await api_client.patch(
        f"{URL}/{created['id']}", json={"summary": None, "desired_city": "Казань"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"] is None
    assert body["desired_city"] == "Казань"
    assert len(body["skills"]) == 3
    assert len(body["experience"]) == 2


async def test_patch_replaces_skill_with_same_canon(api_client: AsyncClient) -> None:
    created = await _create(api_client)
    response = await api_client.patch(
        f"{URL}/{created['id']}",
        json={"skills": [{"skill": "PYTHON", "level": 2}, {"skill": "docker", "level": 1}]},
    )
    assert response.status_code == 200, response.text
    assert [(s["skill"], s["level"]) for s in response.json()["skills"]] == [
        ("docker", 1),
        ("python", 2),
    ]


async def test_patch_replaces_language_with_same_name(api_client: AsyncClient) -> None:
    created = await _create(api_client)
    response = await api_client.patch(
        f"{URL}/{created['id']}", json={"languages": [{"language": "English", "level": "C1"}]}
    )
    assert response.status_code == 200, response.text
    assert [(x["language"], x["level"]) for x in response.json()["languages"]] == [
        ("English", "C1")
    ]


async def test_patch_empty_list_clears_only_that_section(api_client: AsyncClient) -> None:
    created = await _create(api_client)
    response = await api_client.patch(f"{URL}/{created['id']}", json={"courses": []})
    assert response.status_code == 200
    body = response.json()
    assert body["courses"] == []
    assert len(body["education"]) == 1
    assert len(body["languages"]) == 2


async def test_patch_null_title_is_422(api_client: AsyncClient) -> None:
    created = await _create(api_client)
    response = await api_client.patch(f"{URL}/{created['id']}", json={"title": None})
    _assert_error(response, 422, "VALIDATION_ERROR")


async def test_patch_unset_primary_is_409(api_client: AsyncClient) -> None:
    created = await _create(api_client)
    response = await api_client.patch(f"{URL}/{created['id']}", json={"is_primary": False})
    error = _assert_error(response, 409, "CONFLICT")
    assert error["details"] == {"field": "is_primary"}
    assert (await _get(api_client, created["id"]))["is_primary"] is True


async def test_patch_make_other_primary(api_client: AsyncClient) -> None:
    first = await _create(api_client, title="Первое")
    second = await _create(api_client, title="Второе")
    response = await api_client.patch(f"{URL}/{second['id']}", json={"is_primary": True})
    assert response.status_code == 200
    assert response.json()["is_primary"] is True
    assert (await _get(api_client, first["id"]))["is_primary"] is False
    # Повтор на уже основном ничего не делает; false на неосновном — тоже.
    assert (await api_client.patch(f"{URL}/{second['id']}", json={"is_primary": True})).is_success
    assert (await api_client.patch(f"{URL}/{first['id']}", json={"is_primary": False})).is_success


async def _prefill_derived(session: AsyncSession, resume_id: str) -> None:
    (vacancy_id,) = await ingest_raws(session, make_raw())
    rid = uuid.UUID(resume_id)
    session.add(VacancyMatch(resume_id=rid, vacancy_id=vacancy_id, score=55.0))
    await session.execute(
        update(Resume).where(Resume.id == rid).values(score=6.5, score_details={"completeness": 2})
    )
    await session.flush()


async def _match_count(session: AsyncSession, resume_id: str) -> int:
    stmt = select(func.count()).where(VacancyMatch.resume_id == uuid.UUID(resume_id))
    return int(await session.scalar(stmt) or 0)


async def test_patch_title_keeps_derived(api_client: AsyncClient, db_session: AsyncSession) -> None:
    created = await _create(api_client)
    await _prefill_derived(db_session, created["id"])
    response = await api_client.patch(f"{URL}/{created['id']}", json={"title": "Новое имя"})
    assert response.status_code == 200
    assert response.json()["score"] == 6.5
    assert response.json()["score_details"] == {"completeness": 2}
    assert await _match_count(db_session, created["id"]) == 1


async def test_patch_summary_invalidates_derived(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    created = await _create(api_client)
    await _prefill_derived(db_session, created["id"])
    response = await api_client.patch(f"{URL}/{created['id']}", json={"summary": "Новое"})
    assert response.status_code == 200
    assert response.json()["score"] is None
    assert response.json()["score_details"] == {}
    assert await _match_count(db_session, created["id"]) == 0


# --- DELETE и duplicate ---


async def test_delete_primary_promotes_freshest(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    primary = await _create(api_client, title="Основное")
    older = await _create(api_client, title="Старое")
    newer = await _create(api_client, title="Новое")
    await _set_updated_at(db_session, older["id"], OLD)
    await _set_updated_at(db_session, newer["id"], OLD + timedelta(days=3))

    response = await api_client.delete(f"{URL}/{primary['id']}")
    assert response.status_code == 204
    assert response.content == b""

    items = (await api_client.get(URL)).json()["items"]
    assert [(i["id"], i["is_primary"]) for i in items] == [
        (newer["id"], True),
        (older["id"], False),
    ]
    assert datetime.fromisoformat(items[0]["updated_at"]) == OLD + timedelta(days=3)


async def test_delete_last_resume(api_client: AsyncClient) -> None:
    created = await _create(api_client)
    assert (await api_client.delete(f"{URL}/{created['id']}")).status_code == 204
    assert (await api_client.get(URL)).json()["items"] == []
    _assert_error(await api_client.get(f"{URL}/{created['id']}"), 404, "NOT_FOUND")


async def test_duplicate(api_client: AsyncClient, db_session: AsyncSession) -> None:
    created = await _create(api_client)
    await _prefill_derived(db_session, created["id"])
    source = await _get(api_client, created["id"])

    response = await api_client.post(f"{URL}/{created['id']}/duplicate")
    assert response.status_code == 201, response.text
    copy = response.json()
    assert copy["id"] != source["id"]
    assert copy["origin"] == "duplicated"
    assert copy["title"] == f"{source['title']} (копия)"
    assert copy["is_primary"] is False
    assert copy["score"] == 6.5
    assert copy["contacts"] == source["contacts"]
    for section in ("experience", "education", "skills", "courses", "languages"):
        assert len(copy[section]) == len(source[section])
        assert {x["id"] for x in copy[section]}.isdisjoint({x["id"] for x in source[section]})
    assert [s["skill"] for s in copy["skills"]] == [s["skill"] for s in source["skills"]]
    assert await _match_count(db_session, copy["id"]) == 0


async def test_duplicate_truncates_long_title(api_client: AsyncClient) -> None:
    created = await _create(api_client, title="x" * 255)
    response = await api_client.post(f"{URL}/{created['id']}/duplicate")
    assert response.status_code == 201
    assert len(response.json()["title"]) == 255


# --- 404 / 422 ---


@pytest.mark.parametrize(
    ("method", "suffix"),
    [("GET", ""), ("PATCH", ""), ("DELETE", ""), ("POST", "/duplicate")],
)
async def test_missing_resume_is_404(api_client: AsyncClient, method: str, suffix: str) -> None:
    missing = uuid.uuid4()
    kwargs: dict[str, Any] = {"json": {"title": "x"}} if method == "PATCH" else {}
    response = await api_client.request(method, f"{URL}/{missing}{suffix}", **kwargs)
    error = _assert_error(response, 404, "NOT_FOUND")
    assert error["details"] == {"resource": "resume", "id": str(missing)}


@pytest.mark.parametrize(
    ("method", "suffix"),
    [("GET", ""), ("PATCH", ""), ("DELETE", ""), ("POST", "/duplicate")],
)
async def test_foreign_resume_is_404(
    api_client: AsyncClient, app_for_db: FastAPI, method: str, suffix: str
) -> None:
    created = await _create(api_client)
    other = uuid.uuid4()
    app_for_db.dependency_overrides[get_current_user_id] = lambda: other
    kwargs: dict[str, Any] = {"json": {"title": "x"}} if method == "PATCH" else {}
    response = await api_client.request(method, f"{URL}/{created['id']}{suffix}", **kwargs)
    _assert_error(response, 404, "NOT_FOUND")
    assert (await api_client.get(URL)).json()["items"] == []


async def test_other_user_sees_only_own(api_client: AsyncClient, other_user: uuid.UUID) -> None:
    created = await _create(api_client)
    assert created["user_id"] == str(other_user)
    assert len((await api_client.get(URL)).json()["items"]) == 1


async def test_invalid_uuid_is_422(api_client: AsyncClient) -> None:
    _assert_error(await api_client.get(f"{URL}/not-a-uuid"), 422, "VALIDATION_ERROR")


def _future(days: int = 30) -> str:
    return (datetime.now(tz=UTC).date() + timedelta(days=days)).isoformat()


@pytest.mark.parametrize(
    "overrides",
    [
        {"experience": [{"company": "A", "position": "B", "start_date": _future()}]},
        {
            "experience": [
                {
                    "company": "A",
                    "position": "B",
                    "start_date": "2024-06-01",
                    "end_date": "2024-06-01",
                }
            ]
        },
        {
            "experience": [
                {
                    "company": "A",
                    "position": "B",
                    "start_date": "2024-01-01",
                    "end_date": "2024-06-01",
                    "is_current": True,
                }
            ]
        },
        {
            "languages": [
                {"language": "English", "level": "B2"},
                {"language": " english ", "level": "C1"},
            ]
        },
        {"title": "x" * 256},
        {"unexpected": 1},
        {"user_id": str(uuid.uuid4())},
        {"origin": "generated"},
    ],
)
async def test_invalid_body_is_422(api_client: AsyncClient, overrides: dict[str, Any]) -> None:
    response = await api_client.post(URL, json=make_resume_payload(**overrides))
    error = _assert_error(response, 422, "VALIDATION_ERROR")
    assert isinstance(error["details"]["errors"], list)
    assert (await api_client.get(URL)).json()["items"] == []
