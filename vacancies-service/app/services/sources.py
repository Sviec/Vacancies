"""Чтение источников и истории запусков парсера (п. 5.1 ТЗ). Без flush и commit."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ParseRun, Source
from app.schemas.sources import ParseRunListQuery


async def list_sources(session: AsyncSession) -> list[tuple[Source, ParseRun | None]]:
    """Источники по slug и последний запуск каждого — двумя запросами."""
    sources = (await session.execute(select(Source).order_by(Source.slug))).scalars().all()
    last_runs_stmt = (
        select(ParseRun)
        .distinct(ParseRun.source_id)
        .order_by(ParseRun.source_id, ParseRun.started_at.desc(), ParseRun.id.desc())
    )
    last_runs = {run.source_id: run for run in (await session.execute(last_runs_stmt)).scalars()}
    return [(source, last_runs.get(source.id)) for source in sources]


async def list_runs(session: AsyncSession, query: ParseRunListQuery) -> list[ParseRun]:
    """Запуски, свежие сверху."""
    # TODO: неизвестный `source_id` даёт пустой список, а не 404.
    stmt = select(ParseRun)
    if query.source_id is not None:
        stmt = stmt.where(ParseRun.source_id == query.source_id)
    if query.status is not None:
        stmt = stmt.where(ParseRun.status == query.status)
    stmt = stmt.order_by(ParseRun.started_at.desc(), ParseRun.id.desc()).limit(query.limit)
    return list((await session.execute(stmt)).scalars().all())
