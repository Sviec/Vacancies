"""Асинхронная часть оценки резюме: рынок навыков, формулировки и сохранение.

Числа считает чистый `resume_scorer.py`. Адаптер подменяет только тексты
рекомендаций. Функции делают flush и не коммитят: границу транзакции задаёт
эндпоинт. `get_settings()` здесь не вызывается — адаптер приходит параметром.
"""

from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.adapters.llm import LLMAdapter
from app.db.models import Resume, Vacancy
from app.schemas.adapters import CriterionFailure
from app.schemas.scoring import ScoreCriterionDetail
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
from app.utils.errors import ExternalServiceError
from app.utils.logging import get_logger

logger = get_logger(__name__)

_CENT: Final = Decimal("0.01")

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


def _points_loss(weight: float, points: float) -> Decimal:
    """Потеря критерия `(weight - points)` с двумя знаками."""
    return (Decimal(str(weight)) - Decimal(str(points))).quantize(_CENT)


def _flat_recommendations(criteria: Sequence[ScoreCriterionDetail]) -> list[str]:
    """Тексты по убыванию потери, при равенстве — по индексу критерия."""
    ranked: list[tuple[Decimal, int, str]] = []
    for index, item in enumerate(criteria):
        text = item.recommendation
        if text is None:
            continue
        ranked.append((_points_loss(item.weight, item.points), index, text))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    return [text for _, _, text in ranked]


async def _apply_recommendation_phrases(result: ScoreResult, llm: LLMAdapter) -> ScoreResult:
    """Подменить тексты рекомендаций. `score`, баллы, вес и issues не меняются.

    Провалы — критерии с уже посчитанной рекомендацией, в порядке `criteria`.
    """
    # TODO: пустой список провалов — адаптер не вызывается.
    failures = [
        CriterionFailure(key=item.key, issues=item.issues)
        for item in result.criteria
        if item.recommendation is not None
    ]
    if not failures:
        return result
    try:
        phrases = await llm.phrase_recommendations(failures)
    except ExternalServiceError as exc:
        # TODO: ошибка формулировки (включая LLMResponseInvalidError) оставляет
        # шаблон и не становится ответом клиенту.
        logger.warning(
            "recommendation_phrases_failed",
            error_type=type(exc).__name__,
            code=exc.code,
        )
        return result
    if len(phrases) != len(failures):
        # TODO: несовпадение длины фраз оставляет шаблонные рекомендации.
        logger.warning(
            "recommendation_phrases_length_mismatch",
            expected=len(failures),
            actual=len(phrases),
        )
        return result
    by_key = {failure.key: phrase for failure, phrase in zip(failures, phrases, strict=True)}
    criteria = [
        item.model_copy(update={"recommendation": by_key[item.key]}) if item.key in by_key else item
        for item in result.criteria
    ]
    return replace(result, criteria=criteria, recommendations=_flat_recommendations(criteria))


async def rescore(
    session: AsyncSession,
    resume: Resume,
    *,
    today: date,
    llm: LLMAdapter,
) -> ScoreResult:
    """Пересчитать и сохранить оценку, не трогая `updated_at` резюме."""
    # Незаписанные изменения резюме должны уйти в БД раньше Core-UPDATE ниже.
    await session.flush()
    market = await load_market_skills(session, resume.target_position)
    result = score_resume(ResumeSnapshot.from_resume(resume), market, today)
    result = await _apply_recommendation_phrases(result, llm)
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
    session: AsyncSession,
    user_id: UUID,
    resume_id: UUID,
    *,
    today: date,
    llm: LLMAdapter,
) -> ScoreResult:
    """Оценка резюме пользователя; чужое или отсутствующее — 404."""
    resume = await resumes.get_resume(session, user_id, resume_id)
    return await rescore(session, resume, today=today, llm=llm)
