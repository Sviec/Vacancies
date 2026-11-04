"""Карточка hh → RawVacancy и NormalizedVacancy. Без сети, настроек и клиента."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.enums import (
    EmploymentType,
    ExperienceLevel,
    ParseQuality,
    SalaryPeriod,
    SourceType,
    WorkFormat,
)
from app.parsers.hh_card import (
    AreaIndex,
    build_area_index,
    build_hh_mapping,
    load_hh_mapping,
    map_hh_card,
)
from app.parsers.registry import get_parser_class, register, unregister
from app.schemas.normalized import NormalizedVacancy
from app.services.normalizer import RawVacancy, normalize_vacancy
from app.utils.errors import SourceNotRunnableError
from app.utils.skills_dict import DATA_DIR

FIXTURES = Path(__file__).parent / "fixtures" / "hh"
PARSED_AT = datetime(2026, 11, 4, 10, 0, tzinfo=UTC)
SLUG = "hh_it"
PUBLISHED_AT = datetime.fromisoformat("2026-10-28T15:04:05+0300")
HTML_DESCRIPTION = (
    "<p>Ищем разработчика в R&amp;D.</p>"
    "<ul><li>PostgreSQL</li><li>код-ревью</li></ul>"
    "<p>Офис<br>в будни</p>"
)
PLAIN_DESCRIPTION = "Ищем разработчика в R&D.\nPostgreSQL\nкод-ревью\nОфис\nв будни"
CARD_FILES = (
    "no_salary.json",
    "salary_range_usd.json",
    "salary_legacy_rur.json",
    "anonymous_employer.json",
    "internship.json",
    "remote.json",
    "hybrid_and_office.json",
    "oblast_without_city.json",
    "salary_shift.json",
    "skills_mixed.json",
    "description_html.json",
)

AREAS = build_area_index(json.loads((FIXTURES / "areas.json").read_text(encoding="utf-8")))


def _load(name: str) -> dict[str, Any]:
    loaded: Any = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        msg = f"{name}: expected an object"
        raise ValueError(msg)
    return {str(key): value for key, value in loaded.items()}


def _mapped(
    card: dict[str, Any], areas: AreaIndex | None = AREAS
) -> tuple[RawVacancy, NormalizedVacancy]:
    raw = map_hh_card(card, slug=SLUG, parsed_at=PARSED_AT, areas=areas)
    return raw, normalize_vacancy(raw)


@pytest.mark.parametrize("name", CARD_FILES)
def test_card_keeps_identity_and_payload(name: str) -> None:
    card = _load(name)
    raw, vacancy = _mapped(card)
    assert vacancy.external_id == card["id"]
    assert vacancy.source == SLUG
    assert vacancy.source_type == SourceType.API
    assert vacancy.url == f"https://hh.ru/vacancy/{card['id']}"
    assert vacancy.parsed_at == PARSED_AT
    assert vacancy.published_at == PUBLISHED_AT
    assert vacancy.raw_payload == card
    assert "parsed_at" not in vacancy.raw_payload
    assert raw.salary_text is None
    assert raw.education_required is None
    assert raw.relocation_support is None
    assert vacancy.education_required is None
    assert vacancy.relocation_support is None
    assert isinstance(raw.skills_hint, tuple)
    assert vacancy.title
    assert vacancy.description_clean
    assert "<" not in vacancy.description_raw
    assert "<" not in vacancy.description_clean


def test_no_salary() -> None:
    _, vacancy = _mapped(_load("no_salary.json"))
    assert vacancy.salary_min is None
    assert vacancy.salary_max is None
    assert vacancy.salary_currency is None
    assert vacancy.salary_period is None
    assert vacancy.salary_is_gross is None
    assert vacancy.work_format == WorkFormat.UNKNOWN
    assert vacancy.experience_min_years == 3
    assert vacancy.experience_level == ExperienceLevel.MIDDLE
    assert vacancy.parse_quality == ParseQuality.FULL
    assert vacancy.company == "Северная лаборатория"


def test_salary_range_usd() -> None:
    _, vacancy = _mapped(_load("salary_range_usd.json"))
    assert vacancy.salary_min == 3000
    assert vacancy.salary_max == 5000
    assert vacancy.salary_currency == "USD"
    assert vacancy.salary_period == SalaryPeriod.MONTH
    assert vacancy.salary_is_gross is False
    assert vacancy.employment_type == EmploymentType.FULL_TIME
    assert vacancy.work_format == WorkFormat.REMOTE


def test_salary_legacy_rur() -> None:
    _, vacancy = _mapped(_load("salary_legacy_rur.json"))
    assert vacancy.salary_min == 150_000
    assert vacancy.salary_max == 200_000
    assert vacancy.salary_currency == "RUB"
    assert vacancy.salary_period == SalaryPeriod.MONTH
    assert vacancy.salary_is_gross is True


def test_anonymous_employer() -> None:
    _, vacancy = _mapped(_load("anonymous_employer.json"))
    assert vacancy.company is None
    assert vacancy.parse_quality == ParseQuality.PARTIAL
    assert vacancy.title
    assert vacancy.description_clean


def test_fly_in_fly_out_unknown_yields_to_full_time_in_text() -> None:
    card = {
        "id": "1302",
        "name": "Оператор склада",
        "description": "График: полная занятость.",
        "employment_form": {"id": "FLY_IN_FLY_OUT"},
    }
    raw, vacancy = _mapped(card)
    assert raw.employment_type == EmploymentType.UNKNOWN
    assert vacancy.employment_type == EmploymentType.FULL_TIME


def test_internship_overrides_form_and_keeps_years() -> None:
    _, vacancy = _mapped(_load("internship.json"))
    assert vacancy.experience_level == ExperienceLevel.INTERN
    assert vacancy.employment_type == EmploymentType.INTERNSHIP
    assert vacancy.experience_min_years == 1


def test_remote() -> None:
    _, vacancy = _mapped(_load("remote.json"))
    assert vacancy.work_format == WorkFormat.REMOTE


def test_hybrid_wins_over_office_by_mapping_order() -> None:
    _, vacancy = _mapped(_load("hybrid_and_office.json"))
    assert vacancy.work_format == WorkFormat.HYBRID


def test_oblast_is_not_a_city() -> None:
    _, with_index = _mapped(_load("oblast_without_city.json"))
    assert with_index.city is None
    assert with_index.country == "Россия"
    _, without_index = _mapped(_load("oblast_without_city.json"), areas=None)
    assert without_index.city is None
    assert without_index.country is None


def test_salary_shift_keeps_amounts_without_period() -> None:
    _, vacancy = _mapped(_load("salary_shift.json"))
    assert vacancy.salary_min == 4000
    assert vacancy.salary_max == 6000
    assert vacancy.salary_currency == "RUB"
    assert vacancy.salary_period is None
    assert vacancy.salary_is_gross is True


def test_skills_come_from_dictionary_and_text() -> None:
    _, vacancy = _mapped(_load("skills_mixed.json"))
    assert vacancy.skills == ["python", "docker"]


def test_description_html() -> None:
    card = _load("description_html.json")
    assert card["description"] == HTML_DESCRIPTION
    raw, vacancy = _mapped(card)
    assert raw.work_format is None
    assert raw.description_raw == PLAIN_DESCRIPTION
    assert vacancy.description_raw == PLAIN_DESCRIPTION
    assert "<" not in vacancy.description_raw
    assert vacancy.raw_payload["description"] == HTML_DESCRIPTION
    assert "<" not in vacancy.description_clean
    assert vacancy.skills == ["postgresql"]
    assert vacancy.languages == ["en:B2", "ru:native"]
    assert vacancy.work_format == WorkFormat.OFFICE
    assert vacancy.city == "Москва"
    assert vacancy.country == "Россия"


def test_description_html_is_deterministic() -> None:
    card = _load("description_html.json")
    first = _mapped(card)[1]
    second = _mapped(card)[1]
    assert first.model_dump() == second.model_dump()
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


@pytest.mark.parametrize("value", ["вчера", "2026-10-28T15:04:05"])
def test_bad_published_at_drops_the_date_and_keeps_the_card(value: str) -> None:
    card = _load("no_salary.json")
    card["published_at"] = value
    raw, vacancy = _mapped(card)
    assert raw.published_at is None
    assert vacancy.published_at is None
    assert vacancy.external_id == card["id"]


def test_unknown_experience_id_does_not_set_years() -> None:
    card = _load("no_salary.json")
    card["experience"] = {"id": "tenYears"}
    raw, vacancy = _mapped(card)
    assert raw.experience_min_years is None
    assert vacancy.experience_min_years is None
    assert vacancy.experience_level == ExperienceLevel.UNKNOWN


def test_unknown_currency_keeps_amounts() -> None:
    card = _load("salary_range_usd.json")
    card["salary_range"]["currency"] = "XXX"
    raw, vacancy = _mapped(card)
    assert raw.salary_min == 3000
    assert raw.salary_max == 5000
    assert raw.salary_currency is None
    assert vacancy.salary_min == 3000
    assert vacancy.salary_max == 5000
    assert vacancy.salary_currency is None


def test_unknown_language_level_is_skipped() -> None:
    card = _load("description_html.json")
    card["languages"].append({"id": "eng", "level": {"id": "z9"}})
    card["languages"].append({"id": "eng", "level": {"id": "b2"}})
    _, vacancy = _mapped(card)
    assert vacancy.languages == ["en:B2", "ru:native"]


def test_leaf_brest_without_address_city() -> None:
    card = _load("no_salary.json")
    card["area"] = {"id": 9001}
    card["address"] = None
    _, vacancy = _mapped(card)
    assert vacancy.city == "Брест"
    assert vacancy.country == "Беларусь"


def test_leaf_khimki_uses_root_country() -> None:
    card = _load("no_salary.json")
    card["area"] = {"id": 2077}
    card["address"] = None
    _, vacancy = _mapped(card)
    assert vacancy.city == "Химки"
    assert vacancy.country == "Россия"


def test_build_hh_mapping_rejects_work_format_outside_enum() -> None:
    data = json.loads((DATA_DIR / "hh_mapping.json").read_text(encoding="utf-8"))
    data["work_format"]["REMOTE"] = "orbit"
    with pytest.raises(ValueError):
        build_hh_mapping(data)


def test_load_hh_mapping_converts_rur_to_rub() -> None:
    mapping = load_hh_mapping()
    assert mapping.currency["RUR"] == "RUB"
    assert list(mapping.work_format) == ["REMOTE", "HYBRID", "ON_SITE", "FIELD_WORK"]
    assert load_hh_mapping() is mapping


def test_importing_hh_card_does_not_register_api() -> None:
    """Карточка сама API не регистрирует. Пакет `app.parsers` регистрирует HHApiParser."""
    import importlib

    import app.parsers
    import app.parsers.hh_card as hh_card
    from app.parsers.hh_api import HHApiParser

    assert hh_card.map_hh_card.__module__ == "app.parsers.hh_card"
    assert "HHClient" not in vars(hh_card)
    assert "HHApiParser" not in vars(hh_card)
    unregister(SourceType.API)
    try:
        importlib.import_module("app.parsers.hh_card")
        with pytest.raises(SourceNotRunnableError):
            get_parser_class(SourceType.API)
    finally:
        register(HHApiParser)
    assert app.parsers.get_parser_class(SourceType.API) is HHApiParser
