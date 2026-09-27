"""`normalize_vacancy`: сборка NormalizedVacancy и приоритет явных полей (п. 5.9 плана)."""

from datetime import datetime

import pytest

from app.enums import (
    EmploymentType,
    ExperienceLevel,
    ParseQuality,
    SalaryPeriod,
    WorkFormat,
)
from app.services.normalizer import compute_content_hash, normalize_vacancy
from factories import PARSED_AT, make_normalized, make_raw


def test_full_vacancy() -> None:
    vacancy = make_normalized()
    assert vacancy.parse_quality == ParseQuality.FULL
    assert vacancy.skills == ["python", "fastapi", "postgresql", "docker"]
    assert all(skill == skill.lower() for skill in vacancy.skills)
    assert vacancy.content_hash == compute_content_hash(
        vacancy.title, vacancy.company, vacancy.description_clean
    )
    assert vacancy.city == "Москва"
    assert vacancy.country == "Россия"
    assert vacancy.experience_level == ExperienceLevel.SENIOR
    assert vacancy.work_format == WorkFormat.REMOTE
    assert vacancy.employment_type == EmploymentType.FULL_TIME
    assert vacancy.relocation_support is None


def test_without_company_is_partial() -> None:
    assert make_normalized(company=None).parse_quality == ParseQuality.PARTIAL
    assert make_normalized(company="   ").company is None


def test_empty_title_is_partial_and_valid() -> None:
    vacancy = make_normalized(title="   ")
    assert vacancy.title == ""
    assert vacancy.parse_quality == ParseQuality.PARTIAL


def test_empty_description_is_partial() -> None:
    assert make_normalized(description_raw="🔥 #python").parse_quality == ParseQuality.PARTIAL


def test_explicit_level_wins() -> None:
    vacancy = make_normalized(title="Junior Python", experience_level=ExperienceLevel.SENIOR)
    assert vacancy.experience_level == ExperienceLevel.SENIOR


def test_unknown_explicit_level_falls_back_to_detection() -> None:
    vacancy = make_normalized(title="Junior Python", experience_level=ExperienceLevel.UNKNOWN)
    assert vacancy.experience_level == ExperienceLevel.JUNIOR


def test_explicit_work_format_and_employment_win() -> None:
    vacancy = make_normalized(
        work_format=WorkFormat.OFFICE,
        employment_type=EmploymentType.CONTRACT,
        relocation_support=False,
    )
    assert vacancy.work_format == WorkFormat.OFFICE
    assert vacancy.employment_type == EmploymentType.CONTRACT
    assert vacancy.relocation_support is False


def test_explicit_salary_wins_over_text() -> None:
    vacancy = make_normalized(
        salary_min=300000, salary_max=100000, salary_currency="rub", salary_text="200к"
    )
    assert (vacancy.salary_min, vacancy.salary_max) == (100000, 300000)
    assert vacancy.salary_currency == "RUB"
    assert vacancy.salary_period is None


def test_unparsed_salary_text_does_not_fall_back_to_description() -> None:
    vacancy = make_normalized(
        salary_text="по договорённости", description_raw="Зарплата 300к, Python"
    )
    assert vacancy.salary_min is None
    assert vacancy.salary_max is None


def test_salary_from_salary_text_and_description() -> None:
    from_text = make_normalized(salary_text="от 200к руб")
    assert (from_text.salary_min, from_text.salary_currency) == (200000, "RUB")
    from_description = make_normalized(description_raw="Python\nЗарплата: 250-300к на руки")
    assert (from_description.salary_min, from_description.salary_max) == (250000, 300000)
    assert from_description.salary_period == SalaryPeriod.MONTH
    assert from_description.salary_is_gross is False


def test_skills_hint_replaces_text_extraction() -> None:
    vacancy = make_normalized(skills_hint=("Питон",), description_raw="Docker и Kafka")
    assert vacancy.skills == ["python"]


def test_hashtags_give_skills() -> None:
    vacancy = make_normalized(title="Разработчик", description_raw="Ищем в команду #python #django")
    assert vacancy.skills == ["python", "django"]
    assert "#" not in vacancy.description_clean


def test_city_from_vocabulary() -> None:
    vacancy = make_normalized(city="мск")
    assert (vacancy.city, vacancy.country) == ("Москва", "Россия")


def test_explicit_country_wins() -> None:
    vacancy = make_normalized(city="мск", country="  Russia ")
    assert (vacancy.city, vacancy.country) == ("Москва", "Russia")


def test_unknown_city_without_country() -> None:
    vacancy = make_normalized(city="г. Урюпинск")
    assert (vacancy.city, vacancy.country) == ("Урюпинск", None)


def test_experience_years_from_text_and_explicit() -> None:
    assert make_normalized(description_raw="Опыт от 3 лет").experience_min_years == 3
    assert make_normalized(experience_min_years=7).experience_min_years == 7


def test_naive_datetimes_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        normalize_vacancy(make_raw(parsed_at=datetime(2026, 9, 1, 12)))  # noqa: DTZ001
    with pytest.raises(ValueError, match="timezone-aware"):
        normalize_vacancy(make_raw(published_at=datetime(2026, 9, 1, 12)))  # noqa: DTZ001


def test_description_raw_is_kept_verbatim() -> None:
    raw = "**Python**\r\n🔥 #remote\u00a0"
    assert make_normalized(description_raw=raw).description_raw == raw


def test_truncation_and_payload_copy() -> None:
    payload = {"views": 10}
    vacancy = make_normalized(
        title="x" * 700, company="y" * 300, raw_payload=payload, languages=("en",)
    )
    assert len(vacancy.title) == 500
    assert len(vacancy.company or "") == 255
    assert vacancy.raw_payload == payload
    assert vacancy.raw_payload is not payload
    assert vacancy.languages == ["en"]


def test_deterministic() -> None:
    raw = make_raw()
    assert normalize_vacancy(raw).model_dump() == normalize_vacancy(raw).model_dump()
    assert make_normalized().parsed_at == PARSED_AT
