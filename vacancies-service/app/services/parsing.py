"""Оркестратор одного прогона источника: parse_run, нормализация, ingest, commit.

# TODO: ошибки отдельных публикаций в ingest_batch не переводят run в failed;
# статус success, текст в error_text.
"""

from collections.abc import Callable, Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import ParseRun, Source
from app.enums import RunStatus
from app.parsers import build_parser, get_parser_class
from app.parsers.base import BaseParser
from app.services.ingest import IngestError, ingest_batch
from app.services.normalizer import normalize_vacancy
from app.utils.errors import SourceNotRunnableError
from app.utils.logging import get_logger

logger = get_logger(__name__)

_ERROR_LIMIT = 2000

ParserFactory = Callable[[Source, Settings], BaseParser]


async def perform_run(
    session: AsyncSession,
    source_id: UUID,
    settings: Settings,
    *,
    now: datetime,
    parser_factory: ParserFactory = build_parser,
) -> None:
    """Один прогон. Неподходящий источник — тихий return, в БД ничего не пишется.

    Успех и ошибка коммитятся здесь: ingest сам не коммитит. Исключение после
    записи failed пробрасывается наружу, соседние задачи RQ это не останавливает.
    """
    source = await session.get(Source, source_id)
    if source is None or _skipped(source):
        return
    if not settings.parsers_enabled:
        return
    if now.tzinfo is None or now.utcoffset() is None:
        msg = "now must be timezone-aware"
        raise ValueError(msg)

    parser = parser_factory(source, settings)
    run = ParseRun(
        source_id=source.id,
        started_at=now,
        status=RunStatus.RUNNING,
        items_found=0,
        items_new=0,
    )
    session.add(run)
    source.last_run_status = RunStatus.RUNNING
    await session.commit()
    run_id = run.id

    try:
        raw_items = await parser.fetch_raw()
        vacancies = []
        for item in raw_items:
            payload = dict(item)
            payload["parsed_at"] = now
            vacancies.append(normalize_vacancy(parser.to_normalized(payload)))
        batch = await ingest_batch(session, vacancies, seen_at=now)
        note = _ingest_errors_text(batch.errors)
        run.status = RunStatus.SUCCESS
        run.finished_at = now
        run.items_found = batch.items_found
        run.items_new = batch.items_new
        run.error_text = note
        source.last_run_status = RunStatus.SUCCESS
        source.last_run_at = now
        source.last_error = note
        await session.commit()
    except Exception as exc:
        await session.rollback()
        await _mark_failed(session, run_id, source.id, exc, now)
        raise


def _skipped(source: Source) -> bool:
    """Демо, выключенный и тип вне реестра не обходятся и не оставляют parse_run."""
    if source.config.get("demo") is True or not source.is_enabled:
        return True
    try:
        get_parser_class(source.source_type)
    except SourceNotRunnableError:
        return True
    return False


def _clip(text: str) -> str:
    return text[:_ERROR_LIMIT]


def _ingest_errors_text(errors: Sequence[IngestError]) -> str | None:
    if not errors:
        return None
    parts = [f"{item.index}: {item.error_type}: {item.message}" for item in errors]
    return _clip("; ".join(parts))


async def _mark_failed(
    session: AsyncSession,
    run_id: UUID,
    source_id: UUID,
    exc: Exception,
    now: datetime,
) -> None:
    text = _clip(f"{type(exc).__name__}: {exc}")
    try:
        run = await session.get(ParseRun, run_id)
        source = await session.get(Source, source_id)
        if run is not None:
            run.status = RunStatus.FAILED
            run.finished_at = now
            run.items_found = 0
            run.items_new = 0
            run.error_text = text
        if source is not None:
            source.last_run_status = RunStatus.FAILED
            source.last_run_at = now
            source.last_error = text
        await session.commit()
    except Exception:
        logger.exception("parse_run_failure_not_saved", source_id=str(source_id))
        await session.rollback()
