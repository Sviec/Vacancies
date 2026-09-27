"""Словари нормализатора, кроме навыков: ОПФ, города, паттерны уровня и формата.

Данные — `app/data/vocab.json`. Паттерны там записаны lowercase и без `ё`:
текст перед поиском проходит `fold`, и заглавная буква или `ё` в паттерне
означала бы паттерн, который не сработает никогда.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType
from typing import Any

from app.enums import EmploymentType, ExperienceLevel, WorkFormat
from app.utils.skills_dict import DATA_DIR
from app.utils.text import city_key_base, fold

_LEVEL_ORDER = (
    ExperienceLevel.INTERN,
    ExperienceLevel.JUNIOR,
    ExperienceLevel.MIDDLE,
    ExperienceLevel.SENIOR,
    ExperienceLevel.LEAD,
)


@dataclass(frozen=True, slots=True)
class CityEntry:
    """Канонический город и его страна."""

    name: str
    country: str | None


@dataclass(frozen=True, slots=True)
class Vocabulary:
    """Скомпилированные словари. Порядок кортежей паттернов — приоритет."""

    legal_forms: tuple[str, ...]
    city_by_key: Mapping[str, CityEntry]
    level_patterns: tuple[tuple[ExperienceLevel, tuple[re.Pattern[str], ...]], ...]
    work_format_patterns: tuple[tuple[WorkFormat, tuple[re.Pattern[str], ...]], ...]
    employment_patterns: tuple[tuple[EmploymentType, tuple[re.Pattern[str], ...]], ...]
    relocation_patterns: tuple[re.Pattern[str], ...]


def _str_list(value: Any, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        msg = f"{where}: expected a list of strings"
        raise ValueError(msg)
    return list(value)


def _compile_patterns(value: Any, where: str) -> tuple[re.Pattern[str], ...]:
    compiled: list[re.Pattern[str]] = []
    for pattern in _str_list(value, where):
        if "ё" in pattern or pattern != pattern.lower():
            msg = f"{where}: pattern {pattern!r} must be lowercase and without 'ё'"
            raise ValueError(msg)
        compiled.append(re.compile(rf"\b(?:{pattern})\b"))
    return tuple(compiled)


def _ordered_patterns(value: Any, where: str) -> list[tuple[str, tuple[re.Pattern[str], ...]]]:
    if not isinstance(value, list):
        msg = f"{where}: expected a list"
        raise ValueError(msg)
    result: list[tuple[str, tuple[re.Pattern[str], ...]]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping) or not isinstance(item.get("value"), str):
            msg = f"{where}[{index}]: expected {{'value': str, 'patterns': [...]}}"
            raise ValueError(msg)
        result.append((item["value"], _compile_patterns(item.get("patterns"), f"{where}[{index}]")))
    return result


def _build_cities(value: Any) -> dict[str, CityEntry]:
    if not isinstance(value, Mapping):
        msg = "cities: expected an object"
        raise ValueError(msg)
    city_by_key: dict[str, CityEntry] = {}
    for name, spec in value.items():
        if not isinstance(name, str) or not isinstance(spec, Mapping):
            msg = f"cities[{name!r}]: expected an object"
            raise ValueError(msg)
        country = spec.get("country")
        if country is not None and not isinstance(country, str):
            msg = f"cities[{name!r}].country: expected a string or null"
            raise ValueError(msg)
        entry = CityEntry(name=name, country=country)
        for alias in [name, *_str_list(spec.get("aliases", []), f"cities[{name!r}]")]:
            key = city_key_base(alias)
            if not key:
                msg = f"cities[{name!r}]: empty alias"
                raise ValueError(msg)
            previous = city_by_key.get(key)
            if previous is not None and previous.name != name:
                msg = f"cities: alias {alias!r} maps to both {previous.name!r} and {name!r}"
                raise ValueError(msg)
            city_by_key[key] = entry
    return city_by_key


def build_vocabulary(data: Mapping[str, Any]) -> Vocabulary:
    """Проверить и скомпилировать словари из разобранного JSON."""
    legal_forms = tuple(
        fold(form) for form in _str_list(data.get("company_legal_forms", []), "legal_forms")
    )

    levels = data.get("experience_level_patterns")
    if not isinstance(levels, Mapping):
        msg = "experience_level_patterns: expected an object"
        raise ValueError(msg)
    level_map = {
        ExperienceLevel(key): _compile_patterns(patterns, f"experience_level_patterns.{key}")
        for key, patterns in levels.items()
    }
    if ExperienceLevel.UNKNOWN in level_map:
        msg = "experience_level_patterns: 'unknown' is not detectable"
        raise ValueError(msg)

    return Vocabulary(
        legal_forms=legal_forms,
        city_by_key=MappingProxyType(_build_cities(data.get("cities"))),
        level_patterns=tuple((lvl, level_map[lvl]) for lvl in _LEVEL_ORDER if lvl in level_map),
        work_format_patterns=tuple(
            (WorkFormat(value), patterns)
            for value, patterns in _ordered_patterns(
                data.get("work_format_patterns"), "work_format_patterns"
            )
        ),
        employment_patterns=tuple(
            (EmploymentType(value), patterns)
            for value, patterns in _ordered_patterns(
                data.get("employment_type_patterns"), "employment_type_patterns"
            )
        ),
        relocation_patterns=_compile_patterns(
            data.get("relocation_patterns", []), "relocation_patterns"
        ),
    )


@lru_cache(maxsize=1)
def load_vocabulary() -> Vocabulary:
    """Загрузить `app/data/vocab.json` (один раз за процесс)."""
    with (DATA_DIR / "vocab.json").open(encoding="utf-8") as file:
        data: Any = json.load(file)
    if not isinstance(data, Mapping):
        msg = "vocab.json: expected an object at the top level"
        raise ValueError(msg)
    return build_vocabulary(data)
