"""Рекомендации вакансий под резюме и кэш `vacancy_matches` (п. 5.6 ТЗ).

Числа считает чистый `matching.py`; здесь выборка, кэш и сортировка.
Функции делают flush и не коммитят: границу транзакции задаёт эндпоинт.
"""

# TODO: кэш пересчитывается при каждом GET, пишутся только изменившиеся
# строки; `computed_at` — время последнего изменения результата; GET пишет
# в БД. При росте объёма — инкрементальный пересчёт по событиям (RQ после
# ingest и PATCH резюме) и чтение `ORDER BY score` по индексу
# `(resume_id, score)`, свежесть вынести из сохранённого балла.
# TODO: строки матчей неактивных вакансий не удаляются.

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Resume, Vacancy, VacancyMatch
from app.enums import UserAction
from app.schemas.recommendations import RecommendationsQuery
from app.services import resumes
from app.services.matching import MatchResult, ResumeMatchProfile, VacancyMatchInput, match
from app.services.user_actions import actions_for
from app.services.vacancy_filters import user_action_exists

# 5 параметров на строку; предел asyncpg — 32767 параметров на запрос.
_UPSERT_CHUNK: Final = 1000


@dataclass(frozen=True, slots=True)
class RecommendedItem:
    """Вакансия и её балл соответствия."""

    vacancy: Vacancy
    result: MatchResult


@dataclass(frozen=True, slots=True)
class Recommendations:
    """Выдача: резюме, по которому считали, вакансии и действия пользователя."""

    resume_id: UUID | None
    items: list[RecommendedItem]
    actions: dict[UUID, list[UserAction]]


async def _primary_resume(session: AsyncSession, user_id: UUID) -> Resume | None:
    stmt = (
        select(Resume)
        .options(selectinload(Resume.experience), selectinload(Resume.skills))
        .where(Resume.user_id == user_id, Resume.is_primary.is_(True))
        .execution_options(populate_existing=True)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _candidate_vacancies(
    session: AsyncSession, user_id: UUID, *, exclude_hidden: bool
) -> list[Vacancy]:
    conditions: list[ColumnElement[bool]] = [Vacancy.is_active.is_(True)]
    if exclude_hidden:
        conditions.append(~user_action_exists(user_id, UserAction.HIDDEN))
    stmt = select(Vacancy).where(*conditions).execution_options(populate_existing=True)
    return list((await session.execute(stmt)).scalars().all())


async def refresh_matches(
    session: AsyncSession,
    resume: Resume,
    vacancies: Sequence[Vacancy],
    *,
    now: datetime,
) -> dict[UUID, MatchResult]:
    """Посчитать матчи и записать в кэш только новые и изменившиеся строки."""
    stmt = select(VacancyMatch.vacancy_id, VacancyMatch.score, VacancyMatch.match_details).where(
        VacancyMatch.resume_id == resume.id
    )
    cached = {row.vacancy_id: (row.score, row.match_details) for row in await session.execute(stmt)}

    profile = ResumeMatchProfile.from_resume(resume, now.date())
    results: dict[UUID, MatchResult] = {}
    changed: list[dict[str, Any]] = []
    for vacancy in sorted(vacancies, key=lambda v: str(v.id)):
        result = match(profile, VacancyMatchInput.from_vacancy(vacancy), now)
        results[vacancy.id] = result
        details = result.details.model_dump(mode="json")
        if cached.get(vacancy.id) != (result.score, details):
            changed.append(
                {
                    "id": uuid.uuid4(),
                    "resume_id": resume.id,
                    "vacancy_id": vacancy.id,
                    "score": result.score,
                    "match_details": details,
                    "computed_at": now,
                }
            )

    for start in range(0, len(changed), _UPSERT_CHUNK):
        insert = pg_insert(VacancyMatch).values(changed[start : start + _UPSERT_CHUNK])
        await session.execute(
            insert.on_conflict_do_update(
                index_elements=["resume_id", "vacancy_id"],
                set_={
                    "score": insert.excluded.score,
                    "match_details": insert.excluded.match_details,
                    "computed_at": insert.excluded.computed_at,
                },
            )
        )
    if changed:
        await session.flush()
    return results


def _sort_key(item: RecommendedItem) -> tuple[float, bool, float, str]:
    published = item.vacancy.published_at
    return (
        -item.result.score,
        published is None,
        -published.timestamp() if published is not None else 0.0,
        str(item.vacancy.id),
    )


async def get_recommendations(
    session: AsyncSession,
    user_id: UUID,
    query: RecommendationsQuery,
    *,
    now: datetime,
) -> Recommendations:
    """Вакансии под резюме по убыванию балла; без резюме — пустая выдача."""
    # TODO: без `resume_id` берётся основное резюме; нет ни одного резюме —
    # 200 и пустой список, а не 404.
    if query.resume_id is not None:
        resume: Resume | None = await resumes.get_resume(session, user_id, query.resume_id)
    else:
        resume = await _primary_resume(session, user_id)
    if resume is None:
        return Recommendations(resume_id=None, items=[], actions={})

    vacancies = await _candidate_vacancies(session, user_id, exclude_hidden=query.exclude_hidden)
    results = await refresh_matches(session, resume, vacancies, now=now)
    items = sorted(
        (RecommendedItem(vacancy=v, result=results[v.id]) for v in vacancies), key=_sort_key
    )[: query.limit]
    actions = await actions_for(session, user_id, [item.vacancy.id for item in items])
    return Recommendations(resume_id=resume.id, items=items, actions=actions)
