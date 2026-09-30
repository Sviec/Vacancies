"""Лента, карточка и метаданные фильтров вакансий (п. 5.5, 5.7 ТЗ)."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Vacancy, VacancyPosting
from app.enums import UserAction
from app.schemas.common import VacancySort
from app.schemas.vacancies import VacancyFiltersMeta, VacancyListQuery
from app.services import resumes
from app.services.matching import MatchResult
from app.services.recommendations import match_sort_key, refresh_matches
from app.services.user_actions import actions_for
from app.services.vacancy_filters import (
    build_conditions,
    build_order_by,
    build_tsquery,
    normalize_query_text,
    rank_expression,
)
from app.utils.errors import NotFoundError

_NO_DATE = datetime.min.replace(tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class VacancyPage:
    """Страница ленты: вакансии, общее число, действия, матчи и источники."""

    items: list[Vacancy]
    total: int
    actions: dict[UUID, list[UserAction]]
    # Пусто, если `resume_id` не передан.
    matches: dict[UUID, MatchResult]
    sources: dict[UUID, list[str]]


async def _sources_for(session: AsyncSession, ids: list[UUID]) -> dict[UUID, list[str]]:
    """Источники публикаций каждого оффера по алфавиту — одним запросом."""
    if not ids:
        return {}
    stmt = (
        select(VacancyPosting.vacancy_id, VacancyPosting.source)
        .where(VacancyPosting.vacancy_id.in_(ids))
        .distinct()
        .order_by(VacancyPosting.vacancy_id, VacancyPosting.source)
    )
    result: dict[UUID, list[str]] = {}
    for vacancy_id, source in await session.execute(stmt):
        result.setdefault(vacancy_id, []).append(source)
    return result


async def list_vacancies(
    session: AsyncSession, user_id: UUID, query: VacancyListQuery, *, now: datetime
) -> VacancyPage:
    """Лента: count, страница, действия, источники; при `resume_id` — матчи.

    Делает flush кэша `vacancy_matches` и не коммитит.
    """
    # TODO: новых индексов нет; пересмотреть по `EXPLAIN (ANALYZE)` на
    # сид-данных этапа 7.
    resume = (
        await resumes.get_resume(session, user_id, query.resume_id)
        if query.resume_id is not None
        else None
    )
    text = normalize_query_text(query.q)
    tsquery = build_tsquery(text) if text is not None else None
    rank = rank_expression(tsquery) if tsquery is not None else None
    conditions = build_conditions(query, user_id, tsquery)
    offset = (query.page - 1) * query.page_size
    matches: dict[UUID, MatchResult] = {}

    if query.sort == VacancySort.MATCH and resume is not None:
        # TODO: при `sort=match` матчи считаются по всей отфильтрованной
        # выборке на каждый GET, и GET пишет в БД. При росте объёма читать
        # `vacancy_matches` через JOIN с `ORDER BY score` по индексу
        # `(resume_id, score)`.
        all_stmt = select(Vacancy).where(*conditions).execution_options(populate_existing=True)
        candidates = list((await session.execute(all_stmt)).scalars().all())
        all_matches = await refresh_matches(session, resume, candidates, now=now)
        ordered = sorted(candidates, key=lambda v: match_sort_key(v, all_matches[v.id]))
        items = ordered[offset : offset + query.page_size]
        matches = {vacancy.id: all_matches[vacancy.id] for vacancy in items}
        total = len(candidates)
    else:
        count = await session.scalar(select(func.count()).select_from(Vacancy).where(*conditions))
        total = int(count or 0)
        # `search_vector` остаётся deferred: в WHERE и ORDER BY он — выражение.
        stmt = (
            select(Vacancy)
            .where(*conditions)
            .order_by(*build_order_by(query.sort, rank))
            .limit(query.page_size)
            .offset(offset)
            .execution_options(populate_existing=True)
        )
        items = list((await session.execute(stmt)).scalars().all())
        if resume is not None:
            matches = await refresh_matches(session, resume, items, now=now)

    ids = [vacancy.id for vacancy in items]
    return VacancyPage(
        items=items,
        total=total,
        actions=await actions_for(session, user_id, ids),
        matches=matches,
        sources=await _sources_for(session, ids),
    )


def _posting_sort_key(posting: VacancyPosting) -> tuple[bool, datetime, str, str]:
    published = posting.published_at
    return (published is None, published or _NO_DATE, posting.source, str(posting.id))


async def get_vacancy(
    session: AsyncSession,
    user_id: UUID,
    vacancy_id: UUID,
    *,
    resume_id: UUID | None = None,
    now: datetime,
) -> tuple[Vacancy, list[UserAction], MatchResult | None]:
    """Карточка с публикациями, действиями и (при `resume_id`) матчем."""
    # TODO: неактивные и скрытые вакансии отдаются (`is_active` в ответе);
    # `viewed` автоматически не пишется — это отдельное действие клиента.
    stmt = (
        select(Vacancy)
        .options(selectinload(Vacancy.postings))
        .where(Vacancy.id == vacancy_id)
        .execution_options(populate_existing=True)
    )
    vacancy = (await session.execute(stmt)).scalar_one_or_none()
    if vacancy is None:
        raise NotFoundError(details={"resource": "vacancy", "id": str(vacancy_id)})
    # Сортировка на месте не порождает событий ORM и не делает объект dirty.
    vacancy.postings.sort(key=_posting_sort_key)
    match_result: MatchResult | None = None
    if resume_id is not None:
        resume = await resumes.get_resume(session, user_id, resume_id)
        match_result = (await refresh_matches(session, resume, [vacancy], now=now))[vacancy.id]
    actions = await actions_for(session, user_id, [vacancy.id])
    return vacancy, actions.get(vacancy.id, []), match_result


async def _distinct(session: AsyncSession, stmt: Select[Any]) -> list[str]:
    return [value for value in (await session.execute(stmt)).scalars().all() if value]


def _distinct_column(column: Any) -> Select[Any]:
    return (
        select(column)
        .distinct()
        .where(Vacancy.is_active.is_(True), column.is_not(None))
        .order_by(column)
    )


async def get_filters_meta(session: AsyncSession) -> VacancyFiltersMeta:
    """Доступные значения фильтров по активным вакансиям, по возрастанию."""
    # TODO: `sources` берутся из публикаций, а не из таблицы `sources`:
    # склеенный оффер отдаёт все свои каналы. `top_skills` нет (решение
    # пользователя, отклонение от п. 5.5 ТЗ).
    sources_stmt = (
        select(VacancyPosting.source)
        .distinct()
        .join(Vacancy, (Vacancy.id == VacancyPosting.vacancy_id) & Vacancy.is_active.is_(True))
        .order_by(VacancyPosting.source)
    )
    return VacancyFiltersMeta(
        countries=await _distinct(session, _distinct_column(Vacancy.country)),
        cities=await _distinct(session, _distinct_column(Vacancy.city)),
        sources=await _distinct(session, sources_stmt),
        currencies=await _distinct(session, _distinct_column(Vacancy.salary_currency)),
    )
