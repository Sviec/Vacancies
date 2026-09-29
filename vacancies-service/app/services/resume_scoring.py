"""Асинхронная часть оценки резюме: рынок навыков из БД и сохранение оценки.

Числа считает чистый `resume_scorer.py`; здесь только чтение вакансий и запись.
Функции делают flush и не коммитят: границу транзакции задаёт эндпоинт.
"""

from datetime import date
from typing import Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.db.models import Resume, Vacancy
from app.services import resumes
from app.services.normalizer import normalize_skills
from app.services.resume_scorer import (
    MarketBasis,
    MarketSkills,
    ResumeSnapshot,
    ScoreResult,
    score_resume,
)
from app.services.vacancy_filters import build_tsquery, normalize_query_text

MARKET_TOP_N: Final = 20
MIN_MARKET_SAMPLE: Final = 5


async def _count(session: AsyncSession, conditions: list[ColumnElement[bool]]) -> int:
    stmt = select(func.count()).select_from(Vacancy).where(*conditions)
    return int(await session.scalar(stmt) or 0)


async def _top_skills(
    session: AsyncSession, conditions: list[ColumnElement[bool]]
) -> tuple[str, ...]:
    skills = select(func.unnest(Vacancy.skills).label("skill")).where(*conditions).subquery()
    frequency = func.count().label("frequency")
    stmt = (
        select(skills.c.skill, frequency)
        .group_by(skills.c.skill)
        # COLLATE "C": порядок ничьих не зависит от локали кластера.
        .order_by(frequency.desc(), skills.c.skill.collate("C"))
        .limit(MARKET_TOP_N)
    )
    rows = (await session.execute(stmt)).all()
    return tuple(normalize_skills(row.skill for row in rows))


async def load_market_skills(session: AsyncSession, target_position: str | None) -> MarketSkills:
    """Топ-20 навыков активных вакансий: по целевой позиции, иначе по всем."""
    # TODO: рынок навыков — FTS по `target_position` при ≥5 вакансиях, иначе
    # все активные; топ-20. Оценка воспроизводима при неизменной базе вакансий.
    active: list[ColumnElement[bool]] = [Vacancy.is_active.is_(True)]
    text = normalize_query_text(target_position)
    if text is not None:
        by_position = [*active, Vacancy.search_vector.op("@@")(build_tsquery(text))]
        size = await _count(session, by_position)
        if size >= MIN_MARKET_SAMPLE:
            return await _market(session, "target_position", size, by_position)
    size = await _count(session, active)
    if size == 0:
        return MarketSkills(basis="none", sample_size=0, top_skills=())
    return await _market(session, "all_vacancies", size, active)


async def _market(
    session: AsyncSession,
    basis: MarketBasis,
    size: int,
    conditions: list[ColumnElement[bool]],
) -> MarketSkills:
    return MarketSkills(
        basis=basis, sample_size=size, top_skills=await _top_skills(session, conditions)
    )


async def rescore(session: AsyncSession, resume: Resume, *, today: date) -> ScoreResult:
    """Пересчитать и сохранить оценку, не трогая `updated_at` резюме."""
    # Незаписанные изменения резюме должны уйти в БД раньше Core-UPDATE ниже.
    await session.flush()
    market = await load_market_skills(session, resume.target_position)
    result = score_resume(ResumeSnapshot.from_resume(resume), market, today)
    details: dict[str, Any] = result.to_details()
    # Core-UPDATE с явным `updated_at=Resume.updated_at` глушит `onupdate`:
    # пересчёт оценки — не правка резюме пользователем.
    await session.execute(
        update(Resume)
        .where(Resume.id == resume.id)
        .values(score=result.score, score_details=details, updated_at=Resume.updated_at)
        .execution_options(synchronize_session=False)
    )
    set_committed_value(resume, "score", result.score)
    set_committed_value(resume, "score_details", details)
    await session.flush()
    return result


async def score_resume_by_id(
    session: AsyncSession, user_id: UUID, resume_id: UUID, *, today: date
) -> ScoreResult:
    """Оценка резюме пользователя; чужое или отсутствующее — 404."""
    resume = await resumes.get_resume(session, user_id, resume_id)
    return await rescore(session, resume, today=today)
