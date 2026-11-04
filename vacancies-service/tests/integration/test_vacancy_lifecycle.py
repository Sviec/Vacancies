"""Гашение, повторное включение и перепроверка hh на vacancies_test."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.constants import TEST_USER_ID

from app.config import Settings
from app.db.models import Source, UserVacancyAction, Vacancy, VacancyPosting
from app.enums import SourceType, UserAction
from app.services.hh_catalog import touch_hh_seen
from app.services.ingest import IngestStatus, ingest_vacancy
from app.services.vacancy_lifecycle import deactivate_stale_canons, recheck_saved_hh
from factories import ingest_raws, make_normalized, make_raw

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 4, 12, tzinfo=UTC)
_APP = "test-app-token"


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        parsers_enabled=True,
        hh_app_token=_APP,
        hh_user_agent="hh-test-agent/1 (tester@example.com)",
        hh_base_url="https://hh.test",
        hh_request_delay_seconds=0,
        hh_timeout_seconds=5,
        hh_max_retries=0,
    )


@pytest.fixture(autouse=True)
def _block_real_http(monkeypatch: pytest.MonkeyPatch) -> None:
    real_init = httpx.AsyncClient.__init__

    def guarded(self: httpx.AsyncClient, *args: object, **kwargs: object) -> None:
        if not isinstance(kwargs.get("transport"), httpx.MockTransport):
            raise AssertionError("real network is not allowed")
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", guarded)

    def _forbid_sync(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("sync HTTP client is not allowed")

    monkeypatch.setattr(httpx.Client, "__init__", _forbid_sync)


async def _canon(session: AsyncSession, vacancy_id: object) -> Vacancy:
    stmt = select(Vacancy).where(Vacancy.id == vacancy_id).execution_options(populate_existing=True)
    return (await session.execute(stmt)).scalar_one()


async def test_old_last_seen_with_key_deactivates(db_session: AsyncSession) -> None:
    db_session.add(
        Source(
            slug="tg_old",
            source_type=SourceType.TELEGRAM,
            config={"stale_after_days": 30},
        )
    )
    vacancy_id = (
        await ingest_raws(
            db_session,
            make_raw(
                source="tg_old",
                external_id="1",
                company="Старая лаборатория",
                url="https://t.me/old/1",
            ),
        )
    )[0]
    posting = (await db_session.scalars(select(VacancyPosting))).one()
    posting.last_seen_at = NOW - timedelta(days=31)
    await db_session.flush()

    assert await deactivate_stale_canons(db_session, NOW) == 1
    assert (await _canon(db_session, vacancy_id)).is_active is False


async def test_missing_key_and_missing_source_stay_active(db_session: AsyncSession) -> None:
    db_session.add(Source(slug="tg_nokey", source_type=SourceType.TELEGRAM, config={}))
    ids = await ingest_raws(
        db_session,
        make_raw(
            source="tg_nokey",
            external_id="1",
            company="Без ключа",
            url="https://t.me/nokey/1",
        ),
        make_raw(
            source="tg_nosource",
            external_id="2",
            company="Без строки",
            url="https://t.me/nosource/2",
        ),
    )
    for posting in (await db_session.scalars(select(VacancyPosting))).all():
        posting.last_seen_at = NOW - timedelta(days=90)
    await db_session.flush()

    assert await deactivate_stale_canons(db_session, NOW) == 0
    for vacancy_id in ids:
        assert (await _canon(db_session, vacancy_id)).is_active is True


async def test_fresh_sibling_keeps_canon_and_deactivate_does_not_reactivate(
    db_session: AsyncSession,
) -> None:
    db_session.add_all(
        [
            Source(
                slug="src_a",
                source_type=SourceType.TELEGRAM,
                config={"stale_after_days": 30},
            ),
            Source(
                slug="src_b",
                source_type=SourceType.TELEGRAM,
                config={"stale_after_days": 30},
            ),
        ]
    )
    ids = await ingest_raws(
        db_session,
        make_raw(source="src_a", external_id="1", url="https://t.me/a/1"),
        make_raw(source="src_b", external_id="2", url="https://t.me/b/2"),
    )
    assert ids[0] == ids[1]
    for posting in (await db_session.scalars(select(VacancyPosting))).all():
        posting.last_seen_at = NOW if posting.source == "src_b" else NOW - timedelta(days=40)
    await db_session.flush()

    assert await deactivate_stale_canons(db_session, NOW) == 0
    assert (await _canon(db_session, ids[0])).is_active is True

    canon = await _canon(db_session, ids[0])
    canon.is_active = False
    await db_session.flush()
    assert await deactivate_stale_canons(db_session, NOW) == 0
    assert (await _canon(db_session, ids[0])).is_active is False


async def test_repeat_ingest_and_touch_reactivate(db_session: AsyncSession) -> None:
    vacancy = make_normalized(
        source="hh_touch",
        external_id="77",
        source_type=SourceType.API,
        company="Касание",
        url="https://hh.test/77",
    )
    created = await ingest_vacancy(db_session, vacancy)
    assert created.status == IngestStatus.CREATED_VACANCY
    canon = await _canon(db_session, created.vacancy_id)
    canon.is_active = False
    await db_session.flush()

    again = await ingest_vacancy(db_session, vacancy, seen_at=NOW)
    assert again.status == IngestStatus.POSTING_SEEN_AGAIN
    assert (await _canon(db_session, created.vacancy_id)).is_active is True

    canon = await _canon(db_session, created.vacancy_id)
    canon.is_active = False
    await db_session.flush()
    touched = await touch_hh_seen(db_session, vacancy.source, [vacancy.external_id], NOW)
    assert touched == 1
    assert (await _canon(db_session, created.vacancy_id)).is_active is True


async def test_recheck_with_mock_transport_writes_the_flag(db_session: AsyncSession) -> None:
    live = Source(
        slug="hh_it",
        source_type=SourceType.API,
        is_enabled=True,
        config={"provider": "hh", "max_vacancies_per_run": 400},
    )
    demo = Source(
        slug="hh_demo",
        source_type=SourceType.API,
        config={"provider": "hh", "demo": True},
    )
    disabled = Source(
        slug="hh_off",
        source_type=SourceType.API,
        is_enabled=False,
        config={"provider": "hh"},
    )
    db_session.add_all([live, demo, disabled])
    await db_session.flush()

    specs = (
        ("hh_it", "1001", "Живая", UserAction.SAVED),
        ("hh_demo", "1002", "Демо", UserAction.SAVED),
        ("hh_off", "1003", "Выключенный", UserAction.APPLIED),
    )
    ids: dict[str, object] = {}
    seen_at: dict[str, object] = {}
    payloads: dict[str, object] = {}
    hashes: dict[str, str] = {}
    for slug, external_id, company, action in specs:
        vacancy_id = (
            await ingest_raws(
                db_session,
                make_raw(
                    source=slug,
                    source_type=SourceType.API,
                    external_id=external_id,
                    company=company,
                    url=f"https://hh.test/{external_id}",
                ),
            )
        )[0]
        ids[external_id] = vacancy_id
        posting = (
            await db_session.scalars(
                select(VacancyPosting).where(VacancyPosting.external_id == external_id)
            )
        ).one()
        seen_at[external_id] = posting.last_seen_at
        payloads[external_id] = dict(posting.raw_payload)
        hashes[external_id] = posting.content_hash
        db_session.add(
            UserVacancyAction(
                user_id=TEST_USER_ID,
                vacancy_id=vacancy_id,
                action=action,
            )
        )
    await db_session.flush()

    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "hh.test"
        assert request.url.host != "api.hh.ru"
        requested.append(request.url.path)
        if request.url.path == "/vacancies/1001":
            return httpx.Response(200, json={"archived": True, "id": "1001"})
        if request.url.path == "/vacancies/1003":
            return httpx.Response(404, json={"errors": [{"type": "not_found"}]})
        raise AssertionError(request.url.path)

    cursors = await recheck_saved_hh(
        db_session,
        _settings(),
        cursors={},
        transport=httpx.MockTransport(handler),
    )
    assert set(requested) == {"/vacancies/1001", "/vacancies/1003"}
    assert (await _canon(db_session, ids["1001"])).is_active is False
    assert (await _canon(db_session, ids["1002"])).is_active is True
    assert (await _canon(db_session, ids["1003"])).is_active is False
    assert cursors == {live.id: None, disabled.id: None}

    for external_id in ("1001", "1002", "1003"):
        posting = (
            await db_session.scalars(
                select(VacancyPosting)
                .where(VacancyPosting.external_id == external_id)
                .execution_options(populate_existing=True)
            )
        ).one()
        assert posting.last_seen_at == seen_at[external_id]
        assert posting.raw_payload == payloads[external_id]
        assert posting.content_hash == hashes[external_id]
