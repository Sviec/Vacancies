"""Матчинг п. 5.6: таблицы по каждой компоненте и инварианты суммы."""

import json
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from app.enums import ExperienceLevel, SalaryPeriod, WorkFormat
from app.services.matching import (
    LEVEL_ORDER,
    MAX_POINTS,
    ResumeMatchProfile,
    VacancyMatchInput,
    match,
    match_freshness,
    match_level,
    match_location,
    match_salary,
    match_skills,
    resume_level,
)

L = ExperienceLevel
TODAY = date(2026, 9, 28)
NOW = datetime(2026, 9, 28, 12, tzinfo=UTC)
VACANCY_ID = UUID("00000000-0000-0000-0000-000000000001")


@dataclass(frozen=True)
class Exp:
    company: str
    position: str
    start_date: date
    end_date: date | None = None
    is_current: bool = False
    description: str | None = None
    achievements: str | None = None


def profile(**overrides: Any) -> ResumeMatchProfile:
    base: dict[str, Any] = {
        "skills": frozenset({"python", "docker"}),
        "level": L.SENIOR,
        "desired_salary_min": 200_000,
        "desired_salary_currency": "RUB",
        "city": "Москва",
        "country": "Россия",
        "desired_work_format": WorkFormat.HYBRID,
    }
    base.update(overrides)
    return ResumeMatchProfile(**base)


def vacancy(**overrides: Any) -> VacancyMatchInput:
    base: dict[str, Any] = {
        "id": VACANCY_ID,
        "skills": ("python", "docker", "kubernetes", "redis"),
        "experience_level": L.SENIOR,
        "salary_min": 150_000,
        "salary_max": 250_000,
        "salary_currency": "RUB",
        "salary_period": SalaryPeriod.MONTH,
        "city": "Москва",
        "country": "Россия",
        "work_format": WorkFormat.OFFICE,
        "relocation_support": None,
        "published_at": NOW - timedelta(days=1),
    }
    base.update(overrides)
    return VacancyMatchInput(**base)


# --- Навыки, 45 ---


@pytest.mark.parametrize(
    ("resume_skills", "vacancy_skills", "points", "reason", "matched", "missing"),
    [
        (["python"], ["python", "docker"], 22.5, "ratio", ["python"], ["docker"]),
        (["js"], ["JavaScript"], 45.0, "ratio", ["javascript"], []),
        (
            ["Python", "Docker"],
            ["python", "docker", "redis"],
            30.0,
            "ratio",
            ["docker", "python"],
            ["redis"],
        ),
        (["go"], ["python", "docker", "redis"], 0.0, "ratio", [], ["docker", "python", "redis"]),
        (["python"], [], 22.5, "vacancy_skills_unknown", [], []),
        (
            [],
            ["a", "b", "c", "d", "e", "f", "g"],
            0.0,
            "ratio",
            [],
            ["a", "b", "c", "d", "e", "f", "g"],
        ),
        (
            ["a", "b"],
            ["a", "b", "c", "d", "e", "f", "g"],
            12.86,
            "ratio",
            ["a", "b"],
            ["c", "d", "e", "f", "g"],
        ),
    ],
)
def test_match_skills(
    resume_skills: list[str],
    vacancy_skills: list[str],
    points: float,
    reason: str,
    matched: list[str],
    missing: list[str],
) -> None:
    result = match_skills(resume_skills, vacancy_skills)
    assert (result.points, result.reason, result.matched, result.missing) == (
        points,
        reason,
        matched,
        missing,
    )
    assert result.max_points == 45


# --- Уровень, 20 ---


@pytest.mark.parametrize(
    ("resume", "vacancy_level", "points", "reason"),
    [
        (L.SENIOR, L.SENIOR, 20, "exact"),
        (L.SENIOR, L.MIDDLE, 10, "adjacent"),
        (L.JUNIOR, L.MIDDLE, 10, "adjacent"),
        (L.JUNIOR, L.SENIOR, 0, "gap"),
        (L.INTERN, L.LEAD, 0, "gap"),
        (L.SENIOR, L.UNKNOWN, 10, "level_unknown"),
        (L.UNKNOWN, L.SENIOR, 10, "level_unknown"),
    ],
)
def test_match_level(resume: L, vacancy_level: L, points: float, reason: str) -> None:
    result = match_level(resume, vacancy_level)
    assert (result.points, result.reason) == (points, reason)
    assert result.context == {"resume_level": resume.value, "vacancy_level": vacancy_level.value}


def test_resume_level_title_beats_experience() -> None:
    long_experience = [Exp("A", "Dev", date(2010, 1, 1), is_current=True)]
    assert resume_level("Senior Python Developer", [], TODAY) == L.SENIOR
    assert resume_level("Junior Python Developer", long_experience, TODAY) == L.JUNIOR
    assert resume_level("Python Developer", long_experience, TODAY) == L.LEAD
    assert resume_level(None, [], TODAY) == L.JUNIOR
    assert resume_level("  ", [Exp("A", "Dev", date(2023, 1, 1), is_current=True)], TODAY) == (
        L.MIDDLE
    )


# --- Зарплата, 15 ---


@pytest.mark.parametrize(
    ("resume_overrides", "vacancy_overrides", "points", "reason"),
    [
        ({}, {"salary_min": None, "salary_max": None}, 7, "vacancy_salary_unknown"),
        ({"desired_salary_min": None}, {}, 7, "resume_salary_unknown"),
        ({"desired_salary_currency": None}, {}, 7, "currency_unknown"),
        ({}, {"salary_currency": None}, 7, "currency_unknown"),
        ({}, {"salary_currency": "USD"}, 7, "currency_mismatch"),
        ({}, {"salary_period": SalaryPeriod.YEAR}, 7, "period_not_comparable"),
        ({}, {"salary_period": SalaryPeriod.HOUR}, 7, "period_not_comparable"),
        ({}, {"salary_min": 100_000, "salary_max": 180_000}, 0, "below"),
        ({}, {"salary_min": None, "salary_max": 199_999}, 0, "below"),
        ({}, {}, 15, "covers"),
        ({}, {"salary_min": 250_000, "salary_max": 300_000}, 15, "covers"),
        ({}, {"salary_min": None, "salary_max": 200_000}, 15, "covers"),
        ({}, {"salary_min": 200_000, "salary_max": None}, 15, "covers"),
        ({}, {"salary_min": 300_000, "salary_max": None}, 15, "covers"),
        ({}, {"salary_min": 150_000, "salary_max": None}, 7, "partial"),
        ({}, {"salary_period": None}, 15, "covers"),
    ],
)
def test_match_salary(
    resume_overrides: dict[str, Any],
    vacancy_overrides: dict[str, Any],
    points: float,
    reason: str,
) -> None:
    result = match_salary(profile(**resume_overrides), vacancy(**vacancy_overrides))
    assert (result.points, result.reason) == (points, reason)
    assert result.max_points == 15


def test_salary_example_inside_range_is_full() -> None:
    result = match_salary(
        profile(desired_salary_min=200_000),
        vacancy(salary_min=150_000, salary_max=250_000),
    )
    assert result.points == 15
    assert result.context == {
        "desired": 200_000,
        "currency": "RUB",
        "salary_min": 150_000,
        "salary_max": 250_000,
    }


# --- Локация и формат, 12 ---


@pytest.mark.parametrize(
    ("resume_overrides", "vacancy_overrides", "points", "reason"),
    [
        ({}, {"work_format": WorkFormat.REMOTE, "city": "Берлин", "country": None}, 12, "remote"),
        ({"desired_work_format": WorkFormat.REMOTE}, {}, 0, "remote_wanted"),
        ({"city": None, "country": None}, {}, 6, "resume_location_unknown"),
        ({}, {"city": None, "country": None}, 6, "vacancy_location_unknown"),
        ({"city": "мск"}, {"city": "Москва"}, 12, "city"),
        ({}, {"city": "Казань"}, 8, "country"),
        ({}, {"city": "Берлин", "country": None, "relocation_support": True}, 6, "relocation"),
        ({}, {"city": "Берлин", "country": None}, 0, "mismatch"),
        (
            {"desired_work_format": WorkFormat.REMOTE},
            {"work_format": WorkFormat.HYBRID},
            12,
            "city",
        ),
        (
            {"desired_work_format": WorkFormat.REMOTE},
            {"work_format": WorkFormat.UNKNOWN, "city": "Берлин", "country": "Германия"},
            0,
            "mismatch",
        ),
    ],
)
def test_match_location(
    resume_overrides: dict[str, Any],
    vacancy_overrides: dict[str, Any],
    points: float,
    reason: str,
) -> None:
    result = match_location(profile(**resume_overrides), vacancy(**vacancy_overrides))
    assert (result.points, result.reason) == (points, reason)
    assert result.max_points == 12


def test_country_is_taken_from_city_dictionary() -> None:
    # У вакансии страна не указана — берётся из словаря города (Казань → Россия).
    result = match_location(
        profile(city="Москва", country=None), vacancy(city="Казань", country=None)
    )
    assert (result.points, result.reason) == (8, "country")
    # Регистр страны не важен.
    result = match_location(
        profile(city=None, country="россия"), vacancy(city="Казань", country="РОССИЯ")
    )
    assert result.reason == "country"


def test_profile_from_resume() -> None:
    resume = SimpleNamespace(
        skills=[SimpleNamespace(skill="JS"), SimpleNamespace(skill="python")],
        target_position="Senior Python Developer",
        experience=[],
        desired_salary_min=100,
        desired_salary_currency="RUB",
        desired_city="мск",
        desired_country=None,
        desired_work_format=WorkFormat.REMOTE,
    )
    result = ResumeMatchProfile.from_resume(resume, TODAY)  # type: ignore[arg-type]
    assert result.skills == frozenset({"javascript", "python"})
    assert result.level == L.SENIOR
    assert (result.city, result.country) == ("Москва", "Россия")


def test_vacancy_input_from_vacancy() -> None:
    source = vacancy()
    namespace = SimpleNamespace(
        id=source.id,
        skills=["python"],
        experience_level=source.experience_level,
        salary_min=source.salary_min,
        salary_max=source.salary_max,
        salary_currency=source.salary_currency,
        salary_period=source.salary_period,
        city=source.city,
        country=source.country,
        work_format=source.work_format,
        relocation_support=source.relocation_support,
        published_at=source.published_at,
    )
    built = VacancyMatchInput.from_vacancy(namespace)  # type: ignore[arg-type]
    assert built == replace(source, skills=("python",))


# --- Свежесть, 8 ---


@pytest.mark.parametrize(
    ("age", "points", "reason"),
    [
        (timedelta(0), 8, "le_3d"),
        (timedelta(days=3), 8, "le_3d"),
        (timedelta(days=3, seconds=1), 6, "le_7d"),
        (timedelta(days=7), 6, "le_7d"),
        (timedelta(days=14), 4, "le_14d"),
        (timedelta(days=30), 2, "le_30d"),
        (timedelta(days=31), 0, "older"),
        (-timedelta(days=2), 8, "le_3d"),
    ],
)
def test_match_freshness(age: timedelta, points: float, reason: str) -> None:
    result = match_freshness(NOW - age, NOW)
    assert (result.points, result.reason) == (points, reason)
    assert result.context["age_days"] == max(age, timedelta(0)).days


def test_freshness_without_date() -> None:
    result = match_freshness(None, NOW)
    assert (result.points, result.reason) == (0, "date_unknown")


def test_freshness_naive_datetime_is_utc() -> None:
    result = match_freshness(datetime(2026, 9, 27, 12), NOW)  # noqa: DTZ001
    assert result.reason == "le_3d"


# --- Итог и инварианты ---


def test_max_points_sum_to_hundred() -> None:
    assert sum(MAX_POINTS.values()) == 100
    assert len(LEVEL_ORDER) == 5


def _parts(result: Any) -> list[Any]:
    d = result.details
    return [d.skills, d.level, d.salary, d.location, d.freshness]


@pytest.mark.parametrize(
    ("resume", "item"),
    [
        (profile(), vacancy()),
        (profile(skills=frozenset()), vacancy(skills=(), published_at=None)),
        (
            profile(skills=frozenset({"python", "docker", "kubernetes", "redis"})),
            vacancy(work_format=WorkFormat.REMOTE),
        ),
        (profile(level=L.INTERN, desired_work_format=WorkFormat.REMOTE), vacancy(salary_max=10)),
    ],
)
def test_invariants(resume: ResumeMatchProfile, item: VacancyMatchInput) -> None:
    result = match(resume, item, NOW)
    parts = _parts(result)
    for part, name in zip(
        parts, ("skills", "level", "salary", "location", "freshness"), strict=True
    ):
        assert 0 <= part.points <= part.max_points == MAX_POINTS[name]
    assert 0 <= result.score <= 100
    assert Decimal(str(result.score)) == sum(Decimal(str(p.points)) for p in parts)
    skills = result.details.skills
    assert skills.matched == sorted(skills.matched)
    assert skills.missing == sorted(skills.missing)
    assert set(skills.matched).isdisjoint(skills.missing)


def test_perfect_match_is_hundred() -> None:
    result = match(
        profile(skills=frozenset({"python", "docker", "kubernetes", "redis"})),
        vacancy(),
        NOW,
    )
    assert result.score == 100.0


def test_example_score() -> None:
    # 22.5 (2 из 4) + 20 + 15 + 12 (город) + 8 = 77.5
    assert match(profile(), vacancy(), NOW).score == 77.5


def _dump(result: Any) -> str:
    return json.dumps(
        {"score": result.score, "details": result.details.model_dump(mode="json")},
        sort_keys=True,
        ensure_ascii=False,
    )


def test_repeat_and_skill_order_are_stable() -> None:
    first = match(profile(), vacancy(), NOW)
    again = match(profile(), vacancy(), NOW)
    reordered = match(profile(), vacancy(skills=("redis", "kubernetes", "docker", "python")), NOW)
    assert _dump(first) == _dump(again) == _dump(reordered)
