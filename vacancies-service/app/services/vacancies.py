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
from app.schemas.vacancies import VacancyFiltersMeta, VacancyListQuery
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
    """Страница ленты: вакансии, общее число и действия пользователя по ним."""

    items: list[Vacancy]
    total: int
    actions: dict[UUID, list[UserAction]]


async def list_vacancies(
    session: AsyncSession, user_id: UUID, query: VacancyListQuery
) -> VacancyPage:
    """Лента тремя запросами (count, страница, действия) — без N+1."""
    # TODO: новых индексов нет; пересмотреть по `EXPLAIN (ANALYZE)` на
    # сид-данных этапа 7.
    text = normalize_query_text(query.q)
    tsquery = build_tsquery(text) if text is not None else None
    rank = rank_expression(tsquery) if tsquery is not None else None
    conditions = build_conditions(query, user_id, tsquery)

    total = await session.scalar(select(func.count()).select_from(Vacancy).where(*conditions))

    # `search_vector` остаётся deferred: в WHERE и ORDER BY он — выражение.
    stmt = (
        select(Vacancy)
        .where(*conditions)
        .order_by(*build_order_by(query.sort, rank))
        .limit(query.page_size)
        .offset((query.page - 1) * query.page_size)
        .execution_options(populate_existing=True)
    )
    items = list((await session.execute(stmt)).scalars().all())
    actions = await actions_for(session, user_id, [vacancy.id for vacancy in items])
    return VacancyPage(items=items, total=int(total or 0), actions=actions)


def _posting_sort_key(posting: VacancyPosting) -> tuple[bool, datetime, str, str]:
    published = posting.published_at
    return (published is None, published or _NO_DATE, posting.source, str(posting.id))


async def get_vacancy(
    session: AsyncSession, user_id: UUID, vacancy_id: UUID
) -> tuple[Vacancy, list[UserAction]]:
    """Карточка с публикациями и действиями пользователя."""
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
    actions = await actions_for(session, user_id, [vacancy.id])
    return vacancy, actions.get(vacancy.id, [])


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
