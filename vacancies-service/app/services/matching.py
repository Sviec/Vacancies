"""Детерминированный балл соответствия резюме и вакансии 0–100 (п. 5.6 ТЗ).

Чистый модуль: ни БД, ни часов, ни LLM. «Сейчас» — параметр `match`.
Компоненты: навыки 45, уровень 20, зарплата 15, локация и формат 12,
свежесть 8. Каждая компонента округляется в `Decimal` до 0.01, итог —
точная сумма компонент; `float` только на выходе.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import TYPE_CHECKING, Final
from uuid import UUID

from app.enums import ExperienceLevel, SalaryPeriod, WorkFormat
from app.schemas.scoring import (
    MatchContextValue,
    MatchCriterionBreakdown,
    MatchDetails,
    MatchSkillsBreakdown,
)
from app.services.normalizer import (
    canonicalize_city,
    detect_level_from_title,
    level_from_years,
    normalize_skills,
)
from app.services.resume_scorer import q2
from app.services.timeline import ExperienceLike, position_spans, total_experience_months
from app.utils.text import collapse_spaces

if TYPE_CHECKING:
    from app.db.models import Resume, Vacancy

# TODO: компоненты округляются до 0.01 (ROUND_HALF_UP), итог — точная сумма.
MAX_POINTS: Final[Mapping[str, int]] = MappingProxyType(
    {"skills": 45, "level": 20, "salary": 15, "location": 12, "freshness": 8}
)

LEVEL_ORDER: Final = (
    ExperienceLevel.INTERN,
    ExperienceLevel.JUNIOR,
    ExperienceLevel.MIDDLE,
    ExperienceLevel.SENIOR,
    ExperienceLevel.LEAD,
)

# TODO: вакансия без навыков — 22.5 из 45 (решение пользователя);
# уровень `unknown` — 10 из 20.
_SKILLS_UNKNOWN = Fraction(45, 2)
_LEVEL_UNKNOWN = 10
_LEVEL_ADJACENT = 10
_SALARY_NEUTRAL = 7
_LOCATION_UNKNOWN = 6
_LOCATION_COUNTRY = 8
_LOCATION_RELOCATION = 6

# Границы свежести включительные: ровно 3 дня → 8 баллов.
_FRESHNESS_STEPS: Final = (
    (timedelta(days=3), 8, "le_3d"),
    (timedelta(days=7), 6, "le_7d"),
    (timedelta(days=14), 4, "le_14d"),
    (timedelta(days=30), 2, "le_30d"),
)

_MONTHS_PER_YEAR = 12


@dataclass(frozen=True, slots=True)
class ResumeMatchProfile:
    """Сторона резюме в матчинге."""

    skills: frozenset[str]
    level: ExperienceLevel
    desired_salary_min: int | None
    desired_salary_currency: str | None
    city: str | None
    country: str | None
    desired_work_format: WorkFormat | None

    @classmethod
    def from_resume(cls, resume: "Resume", today: date) -> "ResumeMatchProfile":
        city, city_country = canonicalize_city(resume.desired_city)
        return cls(
            skills=frozenset(normalize_skills(skill.skill for skill in resume.skills)),
            level=resume_level(resume.target_position, resume.experience, today),
            desired_salary_min=resume.desired_salary_min,
            desired_salary_currency=resume.desired_salary_currency,
            city=city,
            country=_clean(resume.desired_country) or city_country,
            desired_work_format=resume.desired_work_format,
        )


@dataclass(frozen=True, slots=True)
class VacancyMatchInput:
    """Сторона вакансии в матчинге."""

    id: UUID
    skills: tuple[str, ...]
    experience_level: ExperienceLevel
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    salary_period: SalaryPeriod | None
    city: str | None
    country: str | None
    work_format: WorkFormat
    relocation_support: bool | None
    published_at: datetime | None

    @classmethod
    def from_vacancy(cls, vacancy: "Vacancy") -> "VacancyMatchInput":
        return cls(
            id=vacancy.id,
            skills=tuple(vacancy.skills or ()),
            experience_level=vacancy.experience_level,
            salary_min=vacancy.salary_min,
            salary_max=vacancy.salary_max,
            salary_currency=vacancy.salary_currency,
            salary_period=vacancy.salary_period,
            city=vacancy.city,
            country=vacancy.country,
            work_format=vacancy.work_format,
            relocation_support=vacancy.relocation_support,
            published_at=vacancy.published_at,
        )


@dataclass(frozen=True, slots=True)
class MatchResult:
    """Итоговый балл и разбивка по пяти компонентам."""

    score: float
    details: MatchDetails


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    return collapse_spaces(value) or None


def resume_level(
    target_position: str | None, experience: Sequence[ExperienceLike], today: date
) -> ExperienceLevel:
    """Грейд резюме: из `target_position`, иначе по суммарному стажу."""
    # TODO: уровень резюме — грейд из `target_position` (явное намерение
    # важнее стажа), иначе `level_from_years(стаж // 12)`; без опыта — junior.
    if target_position is not None and target_position.strip():
        from_title = detect_level_from_title(target_position)
        if from_title is not None:
            return from_title
    months = total_experience_months(position_spans(experience, today))
    return level_from_years(months // _MONTHS_PER_YEAR)


def _criterion(
    name: str, points: Fraction | int, reason: str, context: Mapping[str, MatchContextValue]
) -> MatchCriterionBreakdown:
    return MatchCriterionBreakdown(
        points=float(q2(Fraction(points))),
        max_points=MAX_POINTS[name],
        reason=reason,
        context=dict(context),
    )


def match_skills(
    resume_skills: Iterable[str], vacancy_skills: Iterable[str]
) -> MatchSkillsBreakdown:
    """45 · |V ∩ R| / |V|; вакансия без навыков — нейтральные 22.5."""
    wanted = set(normalize_skills(vacancy_skills))
    have = set(normalize_skills(resume_skills))
    matched = sorted(wanted & have)
    missing = sorted(wanted - have)
    if not wanted:
        points = _SKILLS_UNKNOWN
        reason = "vacancy_skills_unknown"
    else:
        points = Fraction(MAX_POINTS["skills"] * len(matched), len(wanted))
        reason = "ratio"
    return MatchSkillsBreakdown(
        matched=matched,
        missing=missing,
        points=float(q2(points)),
        max_points=MAX_POINTS["skills"],
        reason=reason,
        context={"matched_count": len(matched), "vacancy_count": len(wanted)},
    )


def match_level(resume: ExperienceLevel, vacancy: ExperienceLevel) -> MatchCriterionBreakdown:
    """20 за точное совпадение грейда, 10 за соседний, 0 дальше."""
    context: dict[str, MatchContextValue] = {
        "resume_level": resume.value,
        "vacancy_level": vacancy.value,
    }
    if ExperienceLevel.UNKNOWN in (resume, vacancy):
        return _criterion("level", _LEVEL_UNKNOWN, "level_unknown", context)
    distance = abs(LEVEL_ORDER.index(resume) - LEVEL_ORDER.index(vacancy))
    if distance == 0:
        return _criterion("level", MAX_POINTS["level"], "exact", context)
    if distance == 1:
        return _criterion("level", _LEVEL_ADJACENT, "adjacent", context)
    return _criterion("level", 0, "gap", context)


def match_salary(resume: ResumeMatchProfile, vacancy: VacancyMatchInput) -> MatchCriterionBreakdown:
    """Правила зарплаты по порядку; первое сработавшее побеждает."""
    # TODO: зарплата (решение пользователя): желаемое внутри вилки или ниже
    # её — 15; «от X» без верха и X < желаемого — 7; верх ниже желаемого — 0;
    # разные валюты/периоды или нет данных — нейтральные 7. Валюта не
    # додумывается.
    desired = resume.desired_salary_min
    low, high = vacancy.salary_min, vacancy.salary_max
    context: dict[str, MatchContextValue] = {
        "desired": desired,
        "currency": resume.desired_salary_currency,
        "salary_min": low,
        "salary_max": high,
    }

    def neutral(reason: str) -> MatchCriterionBreakdown:
        return _criterion("salary", _SALARY_NEUTRAL, reason, context)

    if low is None and high is None:
        return neutral("vacancy_salary_unknown")
    if desired is None:
        return neutral("resume_salary_unknown")
    if resume.desired_salary_currency is None or vacancy.salary_currency is None:
        return neutral("currency_unknown")
    if resume.desired_salary_currency.upper() != vacancy.salary_currency.upper():
        return neutral("currency_mismatch")
    if vacancy.salary_period not in (None, SalaryPeriod.MONTH):
        return neutral("period_not_comparable")
    if high is not None:
        if high < desired:
            return _criterion("salary", 0, "below", context)
        return _criterion("salary", MAX_POINTS["salary"], "covers", context)
    if low is not None and low >= desired:
        return _criterion("salary", MAX_POINTS["salary"], "covers", context)
    return neutral("partial")


def _city_key(city: str | None) -> str | None:
    canon, _ = canonicalize_city(city)
    return canon.casefold() if canon is not None else None


def _country_key(country: str | None, city: str | None) -> str | None:
    value = _clean(country) or canonicalize_city(city)[1]
    return value.casefold() if value is not None else None


def match_location(
    resume: ResumeMatchProfile, vacancy: VacancyMatchInput
) -> MatchCriterionBreakdown:
    """Формат и география: удалёнка, город, страна, релокация."""
    # TODO: желаемый remote против office — 0 (решение пользователя); нет
    # локации у одной из сторон — 6. hybrid и unknown при желаемом remote
    # оцениваются по географии.
    resume_city = _city_key(resume.city)
    resume_country = _country_key(resume.country, resume.city)
    vacancy_city = _city_key(vacancy.city)
    vacancy_country = _country_key(vacancy.country, vacancy.city)
    context: dict[str, MatchContextValue] = {
        "desired_work_format": (
            resume.desired_work_format.value if resume.desired_work_format else None
        ),
        "work_format": vacancy.work_format.value,
    }

    if vacancy.work_format == WorkFormat.REMOTE:
        return _criterion("location", MAX_POINTS["location"], "remote", context)
    if resume.desired_work_format == WorkFormat.REMOTE and vacancy.work_format == WorkFormat.OFFICE:
        return _criterion("location", 0, "remote_wanted", context)
    if resume_city is None and resume_country is None:
        return _criterion("location", _LOCATION_UNKNOWN, "resume_location_unknown", context)
    if vacancy_city is None and vacancy_country is None:
        return _criterion("location", _LOCATION_UNKNOWN, "vacancy_location_unknown", context)
    if resume_city is not None and resume_city == vacancy_city:
        return _criterion("location", MAX_POINTS["location"], "city", context)
    if resume_country is not None and resume_country == vacancy_country:
        return _criterion("location", _LOCATION_COUNTRY, "country", context)
    if vacancy.relocation_support is True:
        return _criterion("location", _LOCATION_RELOCATION, "relocation", context)
    return _criterion("location", 0, "mismatch", context)


def match_freshness(published_at: datetime | None, now: datetime) -> MatchCriterionBreakdown:
    """8 баллов за ≤3 дня, затем 6/4/2 до 30 дней; без даты — 0."""
    # TODO: `published_at=NULL` — 0 баллов свежести; границы включительные;
    # дата из будущего (рассинхрон часов) считается возрастом 0.
    if published_at is None:
        return _criterion("freshness", 0, "date_unknown", {"age_days": None})
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    age = max(now - published_at, timedelta(0))
    context: dict[str, MatchContextValue] = {"age_days": age.days}
    for limit, points, reason in _FRESHNESS_STEPS:
        if age <= limit:
            return _criterion("freshness", points, reason, context)
    return _criterion("freshness", 0, "older", context)


def match(resume: ResumeMatchProfile, vacancy: VacancyMatchInput, now: datetime) -> MatchResult:
    """Балл 0–100 и разбивка по пяти компонентам."""
    details = MatchDetails(
        skills=match_skills(resume.skills, vacancy.skills),
        level=match_level(resume.level, vacancy.experience_level),
        salary=match_salary(resume, vacancy),
        location=match_location(resume, vacancy),
        freshness=match_freshness(vacancy.published_at, now),
    )
    parts = (details.skills, details.level, details.salary, details.location, details.freshness)
    total = sum((Decimal(str(part.points)) for part in parts), Decimal(0))
    return MatchResult(score=float(total), details=details)
