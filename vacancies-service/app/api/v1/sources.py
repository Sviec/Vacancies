"""Роутер источников вакансий (п. 5.1 ТЗ). Источники глобальные — без `user_id`.

Статический `/runs` объявлен раньше `/{source_id}/run`.
# TODO: demo is True проверяется раньше parsers_enabled, чтобы сид получал DEMO_SOURCE.
"""

from typing import Annotated
from uuid import UUID

import redis
from fastapi import APIRouter, Query

from app.config import get_settings
from app.db.models import Source
from app.db.session import SessionDep
from app.parsers import get_parser_class
from app.schemas.sources import (
    ParseRunListQuery,
    ParseRunListResponse,
    ParseRunRead,
    SourceListItem,
    SourceListResponse,
    SourceRunAccepted,
    source_location,
)
from app.services import sources
from app.tasks.queue import enqueue_manual_run
from app.utils.errors import (
    DemoSourceError,
    DependencyUnavailableError,
    NotFoundError,
    ParsersDisabledError,
    SourceAlreadyRunningError,
    SourceDisabledError,
    SourceNotRunnableError,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=SourceListResponse)
async def list_sources(session: SessionDep) -> SourceListResponse:
    rows = await sources.list_sources(session)
    items = [
        SourceListItem.model_validate(source).model_copy(
            update={
                "location": source_location(source.source_type, source.config),
                "last_run_items_found": run.items_found if run is not None else None,
                "last_run_items_new": run.items_new if run is not None else None,
            }
        )
        for source, run in rows
    ]
    return SourceListResponse(items=items)


@router.get("/runs", response_model=ParseRunListResponse)
async def list_runs(
    query: Annotated[ParseRunListQuery, Query()], session: SessionDep
) -> ParseRunListResponse:
    runs = await sources.list_runs(session, query)
    return ParseRunListResponse(items=[ParseRunRead.model_validate(run) for run in runs])


def _details(source: Source) -> dict[str, str]:
    return {"source_id": str(source.id), "slug": source.slug}


@router.post("/{source_id}/run", status_code=202, response_model=SourceRunAccepted)
async def enqueue_source_run(source_id: UUID, session: SessionDep) -> SourceRunAccepted:
    """Поставить ручной обход. До Redis ничего не пишется и парсер не вызывается."""
    settings = get_settings()
    source = await session.get(Source, source_id)
    if source is None:
        raise NotFoundError(details={"source_id": str(source_id)})
    details = _details(source)
    # Демо раньше флага парсеров: кнопка сида должна говорить именно про демо.
    if source.config.get("demo") is True:
        raise DemoSourceError(details=details)
    if not settings.parsers_enabled:
        raise ParsersDisabledError(details=details)
    if not source.is_enabled:
        raise SourceDisabledError(details=details)
    try:
        get_parser_class(source.source_type)
    except SourceNotRunnableError:
        raise SourceNotRunnableError(details=details) from None
    connection: redis.Redis | None = None
    try:
        connection = redis.Redis.from_url(settings.redis_url)
        job_id = enqueue_manual_run(source, settings, connection)
    except SourceAlreadyRunningError:
        raise
    except Exception as exc:
        logger.warning("source_enqueue_failed", error_type=type(exc).__name__)
        raise DependencyUnavailableError(details=details) from exc
    finally:
        if connection is not None:
            connection.close()
    return SourceRunAccepted(source_id=source.id, job_id=job_id)
