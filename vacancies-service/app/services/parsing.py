"""Оркестратор одного прогона источника: parse_run, нормализация, ingest, commit.

# TODO: ошибки отдельных публикаций в ingest_batch не переводят run в failed;
# статус success, текст в error_text.
"""

import re
from collections.abc import Callable, Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import ParseRun, Source
from app.enums import RunStatus
from app.parsers import build_parser
from app.parsers.api_providers import ensure_source_runnable
from app.parsers.base import BaseParser
from app.parsers.hh_api import HHApiParser
from app.services.hh_catalog import load_hh_postings, touch_hh_seen
from app.services.ingest import IngestError, ingest_batch
from app.services.normalizer import normalize_vacancy
from app.utils.errors import SourceNotRunnableError
from app.utils.logging import get_logger

logger = get_logger(__name__)

_ERROR_LIMIT = 2000
# Порядок фиксирован: отсутствующий ключ пропускается, а не печатается пустым.
_SAFE_DETAIL_KEYS = ("status_code", "hh_error_type", "reason", "service")
# Короткий код или число. JSON-тело, токен и URL (слэш, вопрос, пробел) не проходят.
_SAFE_DETAIL_TEXT = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")

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
    slug = source.slug
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
        if isinstance(parser, HHApiParser):
            cursor, known = await load_hh_postings(session, slug)
            parser.bind(cursor, known, now)
        raw_items = await parser.fetch_raw()
        vacancies = []
        for item in raw_items:
            payload = dict(item)
            payload["parsed_at"] = now
            vacancies.append(normalize_vacancy(parser.to_normalized(payload)))
        batch = await ingest_batch(session, vacancies, seen_at=now)
        extra: Sequence[str] = ()
        touched = 0
        if isinstance(parser, HHApiParser):
            extra = parser.item_errors
            touched = await touch_hh_seen(session, slug, parser.seen_external_ids, now)
        note = _error_text(batch.errors, extra)
        run.status = RunStatus.SUCCESS
        run.finished_at = now
        run.items_found = batch.items_found + touched
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
    """Демо, выключенный и нерабочий источник не обходятся и не оставляют parse_run."""
    if source.config.get("demo") is True or not source.is_enabled:
        return True
    try:
        ensure_source_runnable(source)
    except SourceNotRunnableError:
        return True
    return False


def _clip(text: str) -> str:
    return text[:_ERROR_LIMIT]


def _error_text(errors: Sequence[IngestError], extra: Sequence[str]) -> str | None:
    parts = [f"{item.index}: {item.error_type}: {item.message}" for item in errors]
    parts.extend(extra)
    if not parts:
        return None
    return _clip("; ".join(parts))


def _failure_text(exc: BaseException) -> str:
    """Класс, сообщение и безопасные поля ``details``, если они есть.

    В скобки попадают только ``status_code``, ``hh_error_type``, ``reason`` и
    ``service``. Сырое тело ответа, токен и URL с секретами не дописываются.
    """
    base = f"{type(exc).__name__}: {exc}"
    extra = _safe_detail_parts(exc)
    if not extra:
        return _clip(base)
    return _clip(f"{base} ({', '.join(extra)})")


def _safe_detail_parts(exc: BaseException) -> list[str]:
    details = getattr(exc, "details", None)
    if not isinstance(details, dict):
        return []
    parts: list[str] = []
    for key in _SAFE_DETAIL_KEYS:
        if key not in details:
            continue
        rendered = _render_detail_value(details[key])
        if rendered is None:
            continue
        parts.append(f"{key}={rendered}")
    return parts


def _render_detail_value(value: object) -> str | None:
    if isinstance(value, str):
        if _SAFE_DETAIL_TEXT.fullmatch(value) is None:
            return None
        return value
    # bool — подкласс int; True/False в статус и код не пишем.
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return str(value)


async def _mark_failed(
    session: AsyncSession,
    run_id: UUID,
    source_id: UUID,
    exc: Exception,
    now: datetime,
) -> None:
    text = _failure_text(exc)
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
