"""Карточка вакансии и действия пользователя (этап 5, живой PostgreSQL)."""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import UserVacancyAction, Vacancy
from app.enums import UserAction
from factories import ingest_raws, make_raw

pytestmark = pytest.mark.integration

URL = "/api/v1/vacancies"
EARLY = datetime(2026, 9, 1, 9, tzinfo=UTC)
LATE = datetime(2026, 9, 4, 9, tzinfo=UTC)


@pytest.fixture
async def merged_id(db_session: AsyncSession) -> str:
    """Одна вакансия, опубликованная в двух каналах (сначала поздняя)."""
    ids = await ingest_raws(
        db_session,
        make_raw(source="tg_z", external_id="1", url="https://t.me/z/1", published_at=LATE),
        make_raw(source="tg_a", external_id="2", url="https://t.me/a/2", published_at=EARLY),
    )
    assert ids[0] == ids[1]
    return str(ids[0])


async def _action_rows(session: AsyncSession, vacancy_id: str) -> int:
    stmt = select(func.count()).where(UserVacancyAction.vacancy_id == uuid.UUID(vacancy_id))
    return int(await session.scalar(stmt) or 0)


async def _post(client: AsyncClient, vacancy_id: str, action: str) -> Any:
    return await client.post(f"{URL}/{vacancy_id}/action", json={"action": action})


async def test_detail_with_postings(api_client: AsyncClient, merged_id: str) -> None:
    response = await api_client.get(f"{URL}/{merged_id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == merged_id
    assert body["is_active"] is True
    assert body["postings_count"] == 2
    assert body["user_actions"] == []
    # Публикации — от ранней к поздней.
    assert [p["source"] for p in body["postings"]] == ["tg_a", "tg_z"]
    for forbidden in ("raw_payload", "content_hash", "description_raw", "search_vector"):
        assert forbidden not in body
        assert all(forbidden not in posting for posting in body["postings"])
    assert body["description_clean"]


async def test_inactive_detail_is_still_returned(
    api_client: AsyncClient, merged_id: str, db_session: AsyncSession
) -> None:
    await db_session.execute(
        update(Vacancy).where(Vacancy.id == uuid.UUID(merged_id)).values(is_active=False)
    )
    await db_session.flush()
    response = await api_client.get(f"{URL}/{merged_id}")
    assert response.status_code == 200
    assert response.json()["is_active"] is False


async def test_detail_404_and_422(api_client: AsyncClient) -> None:
    missing = uuid.uuid4()
    response = await api_client.get(f"{URL}/{missing}")
    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "NOT_FOUND",
        "message": "Requested resource was not found",
        "details": {"resource": "vacancy", "id": str(missing)},
    }
    invalid = await api_client.get(f"{URL}/not-a-uuid")
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_post_action_is_idempotent(
    api_client: AsyncClient, merged_id: str, db_session: AsyncSession
) -> None:
    first = await _post(api_client, merged_id, "viewed")
    second = await _post(api_client, merged_id, "viewed")
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == {"vacancy_id": merged_id, "actions": ["viewed"]}
    assert await _action_rows(db_session, merged_id) == 1
    row = await db_session.scalar(
        select(UserVacancyAction).where(UserVacancyAction.vacancy_id == uuid.UUID(merged_id))
    )
    assert row is not None
    assert row.user_id == get_settings().demo_user_id


async def test_saved_and_hidden_are_mutually_exclusive(
    api_client: AsyncClient, merged_id: str
) -> None:
    await _post(api_client, merged_id, "viewed")
    hidden = await _post(api_client, merged_id, "hidden")
    assert hidden.json()["actions"] == ["viewed", "hidden"]
    saved = await _post(api_client, merged_id, "saved")
    assert saved.json()["actions"] == ["viewed", "saved"]
    hidden_again = await _post(api_client, merged_id, "hidden")
    assert hidden_again.json()["actions"] == ["viewed", "hidden"]
    applied = await _post(api_client, merged_id, "applied")
    assert applied.json()["actions"] == ["viewed", "hidden", "applied"]


async def test_delete_action_is_idempotent(
    api_client: AsyncClient, merged_id: str, db_session: AsyncSession
) -> None:
    await _post(api_client, merged_id, "saved")
    first = await api_client.delete(f"{URL}/{merged_id}/action/saved")
    second = await api_client.delete(f"{URL}/{merged_id}/action/saved")
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == {"vacancy_id": merged_id, "actions": []}
    assert await _action_rows(db_session, merged_id) == 0


async def test_actions_on_missing_vacancy_are_404(api_client: AsyncClient) -> None:
    missing = uuid.uuid4()
    post = await _post(api_client, str(missing), "saved")
    delete = await api_client.delete(f"{URL}/{missing}/action/saved")
    for response in (post, delete):
        assert response.status_code == 404
        assert response.json()["error"]["details"] == {"resource": "vacancy", "id": str(missing)}


async def test_invalid_action_is_422(api_client: AsyncClient, merged_id: str) -> None:
    post = await _post(api_client, merged_id, "liked")
    delete = await api_client.delete(f"{URL}/{merged_id}/action/liked")
    extra = await api_client.post(
        f"{URL}/{merged_id}/action", json={"action": "saved", "note": "x"}
    )
    for response in (post, delete, extra):
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_actions_on_inactive_vacancy_allowed(
    api_client: AsyncClient, merged_id: str, db_session: AsyncSession
) -> None:
    await db_session.execute(
        update(Vacancy).where(Vacancy.id == uuid.UUID(merged_id)).values(is_active=False)
    )
    await db_session.flush()
    assert (await _post(api_client, merged_id, "applied")).status_code == 200


async def test_user_actions_visible_in_feed_and_detail(
    api_client: AsyncClient, merged_id: str
) -> None:
    await _post(api_client, merged_id, "saved")
    await _post(api_client, merged_id, "viewed")
    detail = (await api_client.get(f"{URL}/{merged_id}")).json()
    assert detail["user_actions"] == ["viewed", "saved"]
    feed = (await api_client.get(URL)).json()
    assert feed["items"][0]["user_actions"] == ["viewed", "saved"]


async def test_actions_are_per_user(
    api_client: AsyncClient, merged_id: str, other_user: uuid.UUID, db_session: AsyncSession
) -> None:
    db_session.add(
        UserVacancyAction(
            user_id=get_settings().demo_user_id,
            vacancy_id=uuid.UUID(merged_id),
            action=UserAction.HIDDEN,
        )
    )
    await db_session.flush()
    # Для другого пользователя вакансия не скрыта и действий у него нет.
    detail = (await api_client.get(f"{URL}/{merged_id}")).json()
    assert detail["user_actions"] == []
    assert (await api_client.get(URL)).json()["total"] == 1


async def test_recommended_is_not_yet_implemented(api_client: AsyncClient) -> None:
    # До этапа 6 строка "recommended" разбирается как vacancy_id → 422.
    # Этап 6 добавит GET /vacancies/recommended и этот тест изменится.
    response = await api_client.get(f"{URL}/recommended")
    assert response.status_code == 422
