"""Прогон парсера на локальном Postgres: ingest настоящий, сеть и Redis нет."""

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import ParseRun, Source, Vacancy
from app.enums import RunStatus, SourceType
from app.parsers.base import BaseParser
from app.services.parsing import perform_run

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 1, 12, tzinfo=UTC)
LATER = datetime(2026, 10, 1, 13, tzinfo=UTC)
AFTER = datetime(2026, 10, 1, 14, tzinfo=UTC)


class _GoodParser(BaseParser):
    source_type = SourceType.HTML

    def __init__(self, *, slug: str, config: Mapping[str, Any], settings: Settings) -> None:
        super().__init__(slug=slug, config=config, settings=settings)
        self.calls = 0

    async def fetch_raw(self) -> list[dict[str, Any]]:
        self.calls += 1
        return [
            {
                "external_id": "ext-1",
                "title": "Python Developer",
                "company": "Acme",
                "city": "Москва",
                "description_raw": "Ищем Python-разработчика. Удалёнка, FastAPI.",
                "url": "https://example.com/jobs/1",
                "salary_text": "от 200000 руб",
            },
            {
                "external_id": "ext-2",
                "title": "Go Developer",
                "company": "Beta",
                "city": "Берлин",
                "description_raw": "Нужен Go-разработчик в платёжный контур.",
                "url": "https://example.com/jobs/2",
            },
        ]

    def to_normalized(self, raw: dict[str, Any]) -> Any:
        from app.services.normalizer import RawVacancy

        return RawVacancy(
            external_id=str(raw["external_id"]),
            source=self.slug,
            source_type=self.source_type,
            title=str(raw.get("title") or ""),
            description_raw=str(raw.get("description_raw") or ""),
            parsed_at=raw["parsed_at"],
            url=raw.get("url"),
            company=raw.get("company"),
            city=raw.get("city"),
            salary_text=raw.get("salary_text"),
        )


class _BadParser(BaseParser):
    source_type = SourceType.TELEGRAM

    async def fetch_raw(self) -> list[dict[str, Any]]:
        raise RuntimeError("network down")

    def to_normalized(self, raw: dict[str, Any]) -> Any:
        raise AssertionError(raw)


class _DemoParser(BaseParser):
    source_type = SourceType.HTML

    async def fetch_raw(self) -> list[dict[str, Any]]:
        raise AssertionError("demo fetch")

    def to_normalized(self, raw: dict[str, Any]) -> Any:
        raise AssertionError(raw)


async def _count(session: AsyncSession, source_id: uuid.UUID | None = None) -> int:
    stmt = select(func.count()).select_from(ParseRun)
    if source_id is not None:
        stmt = stmt.where(ParseRun.source_id == source_id)
    return int(await session.scalar(stmt) or 0)


async def test_perform_run_ingests_and_isolates_failure(db_session: AsyncSession) -> None:
    good = Source(
        slug="html_live",
        source_type=SourceType.HTML,
        config={"demo": False, "url": "https://jobs.example.org/it", "list_selector": "div"},
        is_enabled=True,
    )
    bad = Source(
        slug="tg_live",
        source_type=SourceType.TELEGRAM,
        config={"demo": False, "channel": "@jobs"},
        is_enabled=True,
    )
    demo = Source(
        slug="html_demo",
        source_type=SourceType.HTML,
        config={"demo": True, "url": "https://careers.example.com/vacancies"},
        is_enabled=True,
    )
    db_session.add_all([good, bad, demo])
    await db_session.flush()

    good_parser = _GoodParser(slug=good.slug, config=good.config, settings=Settings(_env_file=None))
    settings = Settings(_env_file=None, parsers_enabled=True)

    def factory(source: Source, parser_settings: Settings) -> BaseParser:
        if source.id == good.id:
            return good_parser
        if source.id == bad.id:
            return _BadParser(slug=source.slug, config=source.config, settings=parser_settings)
        return _DemoParser(slug=source.slug, config=source.config, settings=parser_settings)

    await perform_run(db_session, good.id, settings, now=NOW, parser_factory=factory)
    runs = list(
        (
            await db_session.scalars(
                select(ParseRun).where(ParseRun.source_id == good.id).order_by(ParseRun.started_at)
            )
        ).all()
    )
    assert len(runs) == 1
    assert runs[0].status is RunStatus.SUCCESS
    assert runs[0].items_found == 2
    assert runs[0].items_new == 2
    assert runs[0].finished_at == NOW
    vacancies = list(
        (await db_session.scalars(select(Vacancy).where(Vacancy.source == "html_live"))).all()
    )
    assert len(vacancies) == 2
    await db_session.refresh(good)
    assert good.last_run_status is RunStatus.SUCCESS
    assert good.last_error is None

    with pytest.raises(RuntimeError, match="network down"):
        await perform_run(db_session, bad.id, settings, now=LATER, parser_factory=factory)
    bad_runs = list(
        (await db_session.scalars(select(ParseRun).where(ParseRun.source_id == bad.id))).all()
    )
    assert len(bad_runs) == 1
    assert bad_runs[0].status is RunStatus.FAILED
    assert bad_runs[0].items_found == 0
    assert bad_runs[0].items_new == 0
    assert bad_runs[0].error_text is not None
    assert "RuntimeError" in bad_runs[0].error_text
    await db_session.refresh(bad)
    assert bad.last_run_status is RunStatus.FAILED

    await perform_run(db_session, good.id, settings, now=AFTER, parser_factory=factory)
    good_runs = list(
        (
            await db_session.scalars(
                select(ParseRun).where(ParseRun.source_id == good.id).order_by(ParseRun.started_at)
            )
        ).all()
    )
    assert [run.status for run in good_runs] == [RunStatus.SUCCESS, RunStatus.SUCCESS]
    assert good_runs[1].items_found == 2
    assert good_runs[1].items_new == 0

    demo_before = await _count(db_session, demo.id)
    await perform_run(db_session, demo.id, settings, now=AFTER, parser_factory=factory)
    assert await _count(db_session, demo.id) == demo_before
    assert good_parser.calls == 2
