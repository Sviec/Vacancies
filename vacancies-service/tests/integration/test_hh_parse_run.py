"""Два прогона hh на vacancies_test: сеть заменена MockTransport."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import ParseRun, Source, Vacancy, VacancyPosting
from app.enums import RunStatus, SourceType
from app.parsers.base import BaseParser
from app.parsers.hh_api import HHApiParser
from app.parsers.hh_card import build_area_index
from app.services.parsing import perform_run

pytestmark = pytest.mark.integration

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "hh"
_CARD = json.loads((_FIXTURES / "no_salary.json").read_text(encoding="utf-8"))
_AREAS = build_area_index(json.loads((_FIXTURES / "areas.json").read_text(encoding="utf-8")))
_SLUG = "hh_it"
NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 11, 4, 15, 0, tzinfo=UTC)
_HIT = {
    "id": "1001",
    "name": "Специалист по качеству данных",
    "employer": {"name": "Северная лаборатория"},
    "published_at": "2026-10-28T15:04:05+0300",
}


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


def _forbid_http(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("HTTP client must not be created")


@pytest.fixture(autouse=True)
def _block_real_http(monkeypatch: pytest.MonkeyPatch) -> None:
    real_init = httpx.AsyncClient.__init__

    def guarded(self: httpx.AsyncClient, *args: object, **kwargs: object) -> None:
        if not isinstance(kwargs.get("transport"), httpx.MockTransport):
            raise AssertionError("real network is not allowed")
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", guarded)
    monkeypatch.setattr(httpx.Client, "__init__", _forbid_http)


def _redis_forbidden(url: str) -> Any:
    raise AssertionError(url)


async def _no_sleep(_seconds: float) -> None:
    return None


async def _count(session: AsyncSession, model: type[Vacancy] | type[VacancyPosting]) -> int:
    return int(
        await session.scalar(select(func.count()).select_from(model).where(model.source == _SLUG))
        or 0
    )


async def test_second_run_touches_seen_at_without_a_second_card_get(
    db_session: AsyncSession,
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "hh.test"
        assert request.url.host != "api.hh.ru"
        seen.append(request)
        if request.url.path == "/vacancies":
            return httpx.Response(200, json={"found": 1, "items": [_HIT]})
        if request.url.path == "/vacancies/1001":
            return httpx.Response(200, json=_CARD)
        raise AssertionError(request.url.path)

    transport = httpx.MockTransport(handler)
    source = Source(
        slug=_SLUG,
        source_type=SourceType.API,
        config={
            "provider": "hh",
            "query": {"text": "данные"},
            "backfill_days": 7,
            "max_vacancies_per_run": 400,
        },
        is_enabled=True,
    )
    db_session.add(source)
    await db_session.flush()
    settings = _settings()

    def factory(bound: Source, parser_settings: Settings) -> BaseParser:
        return HHApiParser(
            slug=bound.slug,
            config=bound.config,
            settings=parser_settings,
            transport=transport,
            sleep=_no_sleep,
            areas=_AREAS,
            redis_factory=_redis_forbidden,
        )

    await perform_run(db_session, source.id, settings, now=NOW, parser_factory=factory)
    posting = await _only(db_session, VacancyPosting)
    vacancy = await _only(db_session, Vacancy)
    assert await _count(db_session, Vacancy) == 1
    assert await _count(db_session, VacancyPosting) == 1
    assert posting.last_seen_at == NOW
    assert vacancy.last_seen_at == NOW
    content_hash = posting.content_hash
    payload = dict(posting.raw_payload)
    runs = await _runs(db_session, source.id)
    assert [run.status for run in runs] == [RunStatus.SUCCESS]
    assert runs[0].items_new == 1
    assert runs[0].items_found == 1

    await perform_run(db_session, source.id, settings, now=LATER, parser_factory=factory)
    posting = await _only(db_session, VacancyPosting)
    vacancy = await _only(db_session, Vacancy)
    assert await _count(db_session, Vacancy) == 1
    assert await _count(db_session, VacancyPosting) == 1
    assert posting.content_hash == content_hash
    assert posting.raw_payload == payload
    assert posting.last_seen_at == LATER
    assert vacancy.last_seen_at == LATER
    card_gets = [request for request in seen if request.url.path == "/vacancies/1001"]
    assert len(card_gets) == 1
    runs = await _runs(db_session, source.id)
    assert [run.status for run in runs] == [RunStatus.SUCCESS, RunStatus.SUCCESS]
    assert runs[1].items_new == 0
    assert runs[1].items_found == 1


async def _only[ModelT: (Vacancy, VacancyPosting)](
    session: AsyncSession, model: type[ModelT]
) -> ModelT:
    rows = list((await session.scalars(select(model).where(model.source == _SLUG))).all())
    assert len(rows) == 1
    return rows[0]


async def _runs(session: AsyncSession, source_id: object) -> list[ParseRun]:
    return list(
        (
            await session.scalars(
                select(ParseRun)
                .where(ParseRun.source_id == source_id)
                .order_by(ParseRun.started_at)
            )
        ).all()
    )
