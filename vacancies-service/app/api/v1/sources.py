"""Роутер источников вакансий (п. 5.1 ТЗ). Источники глобальные — без `user_id`.

`POST /{source_id}/run` появится на этапе 11. Когда появится маршрут
`/{source_id}`, статический `/runs` должен быть объявлен раньше него.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.db.session import SessionDep
from app.schemas.sources import (
    ParseRunListQuery,
    ParseRunListResponse,
    ParseRunRead,
    SourceListItem,
    SourceListResponse,
    source_location,
)
from app.services import sources

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
