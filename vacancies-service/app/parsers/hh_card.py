"""Карточка вакансии hh.ru → `RawVacancy`.

Чистая функция: без сети, Redis, настроек и регистрации в реестре парсеров.
Соответствия справочников hh лежат в `app/data/hh_mapping.json`, не в коде.
Класс парсера и `fetch_raw` появятся на подэтапе обхода, не здесь.
"""

import json
import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

from selectolax.lexbor import LexborHTMLParser

from app.enums import (
    EmploymentType,
    ExperienceLevel,
    LanguageLevel,
    SalaryPeriod,
    SourceType,
    WorkFormat,
)
from app.services.normalizer import RawVacancy, extract_skills
from app.utils.skills_dict import SkillsDictionary, load_skills_dictionary, normalize_skill_token

_MAPPING_FILE = Path(__file__).resolve().parents[1] / "data" / "hh_mapping.json"

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_LANGUAGE_RE = re.compile(r"^[a-z]{2}$")
_INLINE_SPACE_RE = re.compile(r"[ \t]+")
_SPACE_LIKE = ("\u00a0", "\u202f", "\u2009")


@dataclass(frozen=True, slots=True)
class HhMapping:
    """Проверенные таблицы hh → поля `RawVacancy`. Порядок `work_format` — приоритет."""

    experience_min_years: Mapping[str, int]
    work_format: Mapping[str, WorkFormat]
    employment_form: Mapping[str, EmploymentType]
    employment: Mapping[str, EmploymentType]
    salary_range_mode: Mapping[str, SalaryPeriod | None]
    currency: Mapping[str, str]
    language: Mapping[str, str]
    language_level: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class AreaRecord:
    """Узел дерева регионов: имя, лист ли это, страна — имя корня ветки."""

    name: str
    is_leaf: bool
    country: str


@dataclass(frozen=True, slots=True)
class AreaIndex:
    """Поиск узла `/areas` по id."""

    by_id: Mapping[str, AreaRecord]

    def lookup(self, area_id: object) -> AreaRecord | None:
        """Запись с именем, признаком листа и страной корня, либо None."""
        key = _scalar_id(area_id)
        if key is None:
            return None
        return self.by_id.get(key)


@dataclass(frozen=True, slots=True)
class _Salary:
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_period: SalaryPeriod | None = None
    salary_is_gross: bool | None = None


def build_hh_mapping(data: object) -> HhMapping:
    """Проверить разобранный `hh_mapping.json`. Битая таблица — `ValueError`."""
    if not isinstance(data, Mapping):
        msg = "hh_mapping: expected an object"
        raise ValueError(msg)
    return HhMapping(
        experience_min_years=MappingProxyType(
            {
                key: _as_years(item, f"experience_min_years[{key!r}]")
                for key, item in _mapping_items(
                    data.get("experience_min_years"), "experience_min_years"
                )
            }
        ),
        work_format=MappingProxyType(
            {
                key: _as_work_format(item, f"work_format[{key!r}]")
                for key, item in _mapping_items(data.get("work_format"), "work_format")
            }
        ),
        employment_form=MappingProxyType(
            {
                key: _as_employment(item, f"employment_form[{key!r}]")
                for key, item in _mapping_items(data.get("employment_form"), "employment_form")
            }
        ),
        employment=MappingProxyType(
            {
                key: _as_employment(item, f"employment[{key!r}]")
                for key, item in _mapping_items(data.get("employment"), "employment")
            }
        ),
        salary_range_mode=MappingProxyType(
            {
                key: _as_salary_period(item, f"salary_range_mode[{key!r}]")
                for key, item in _mapping_items(data.get("salary_range_mode"), "salary_range_mode")
            }
        ),
        currency=MappingProxyType(
            {
                key: _as_currency(item, f"currency[{key!r}]")
                for key, item in _mapping_items(data.get("currency"), "currency")
            }
        ),
        language=MappingProxyType(
            {
                key: _as_language(item, f"language[{key!r}]")
                for key, item in _mapping_items(data.get("language"), "language")
            }
        ),
        language_level=MappingProxyType(
            {
                key: _as_language_level(item, f"language_level[{key!r}]")
                for key, item in _mapping_items(data.get("language_level"), "language_level")
            }
        ),
    )


@lru_cache(maxsize=1)
def load_hh_mapping() -> HhMapping:
    """Загрузить `app/data/hh_mapping.json` (один раз за процесс)."""
    with _MAPPING_FILE.open(encoding="utf-8") as file:
        data: Any = json.load(file)
    return build_hh_mapping(data)


def build_area_index(roots: object) -> AreaIndex:
    """Индекс дерева `/areas`. Повторный id — `ValueError`. Узел без id и name пропускается."""
    if not isinstance(roots, list):
        msg = "hh areas: expected a list of roots"
        raise ValueError(msg)
    records: dict[str, AreaRecord] = {}
    for root in roots:
        _walk_area(root, None, records)
    return AreaIndex(MappingProxyType(records))


def map_hh_card(
    card: Mapping[str, Any],
    *,
    slug: str,
    parsed_at: datetime,
    areas: AreaIndex | None = None,
) -> RawVacancy:
    """Собрать `RawVacancy` из карточки `GET /vacancies/{id}`. Незнакомый id не роняет разбор."""
    mapping = load_hh_mapping()
    title = card.get("name")
    title_text = title if isinstance(title, str) else ""
    description_raw = _description_text(card.get("description"))
    salary = _salary(card, mapping)
    years, level = _experience(card, mapping)
    city, country = _location(card, areas)
    payload = deepcopy(dict(card))
    return RawVacancy(
        external_id=_external_id(card.get("id")),
        source=slug,
        source_type=SourceType.API,
        title=title_text,
        description_raw=description_raw,
        parsed_at=parsed_at,
        url=_non_empty_str(card.get("alternate_url")),
        company=_company(card.get("employer")),
        city=city,
        country=country,
        skills_hint=_skills(title_text, description_raw, card),
        published_at=_published_at(card.get("published_at")),
        raw_payload=payload,
        work_format=_work_format(card, mapping),
        employment_type=_employment_type(card, mapping),
        experience_level=level,
        experience_min_years=years,
        salary_min=salary.salary_min,
        salary_max=salary.salary_max,
        salary_currency=salary.salary_currency,
        salary_period=salary.salary_period,
        salary_is_gross=salary.salary_is_gross,
        languages=_languages(card, mapping),
    )


def _mapping_items(value: object, where: str) -> list[tuple[str, object]]:
    if not isinstance(value, Mapping):
        msg = f"{where}: expected an object"
        raise ValueError(msg)
    items: list[tuple[str, object]] = []
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            msg = f"{where}: expected non-empty string keys"
            raise ValueError(msg)
        items.append((key, item))
    return items


def _as_years(value: object, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        msg = f"{where}: expected a non-negative integer"
        raise ValueError(msg)
    return value


def _as_work_format(value: object, where: str) -> WorkFormat:
    if isinstance(value, str):
        try:
            return WorkFormat(value)
        except ValueError:
            pass
    msg = f"{where}: {value!r} is not a work format"
    raise ValueError(msg)


def _as_employment(value: object, where: str) -> EmploymentType:
    if isinstance(value, str):
        try:
            return EmploymentType(value)
        except ValueError:
            pass
    msg = f"{where}: {value!r} is not an employment type"
    raise ValueError(msg)


def _as_salary_period(value: object, where: str) -> SalaryPeriod | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return SalaryPeriod(value)
        except ValueError:
            pass
    msg = f"{where}: {value!r} is not a salary period or null"
    raise ValueError(msg)


def _as_currency(value: object, where: str) -> str:
    if isinstance(value, str) and _CURRENCY_RE.fullmatch(value):
        return value
    msg = f"{where}: expected a three-letter currency code"
    raise ValueError(msg)


def _as_language(value: object, where: str) -> str:
    if isinstance(value, str) and _LANGUAGE_RE.fullmatch(value):
        return value
    msg = f"{where}: expected a two-letter language code"
    raise ValueError(msg)


def _as_language_level(value: object, where: str) -> str:
    if isinstance(value, str):
        try:
            return LanguageLevel(value).value
        except ValueError:
            pass
    msg = f"{where}: {value!r} is not a language level"
    raise ValueError(msg)


def _scalar_id(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return None


def _external_id(value: object) -> str:
    key = _scalar_id(value)
    return "" if key is None else key


def _non_empty_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _walk_area(node: object, country: str | None, records: dict[str, AreaRecord]) -> None:
    if not isinstance(node, dict):
        return
    children, is_leaf = _area_children(node)
    name = node.get("name")
    key = _scalar_id(node.get("id"))
    if not isinstance(name, str) or key is None:
        if country is None:
            return
        for child in children:
            _walk_area(child, country, records)
        return
    if key in records:
        msg = f"hh areas: duplicate id {key!r}"
        raise ValueError(msg)
    node_country = name if country is None else country
    records[key] = AreaRecord(name=name, is_leaf=is_leaf, country=node_country)
    for child in children:
        _walk_area(child, node_country, records)


def _area_children(node: Mapping[str, Any]) -> tuple[list[object], bool]:
    if "areas" not in node or node.get("areas") is None:
        return [], True
    areas = node.get("areas")
    if isinstance(areas, list):
        return list(areas), len(areas) == 0
    return [], False


def _description_text(value: object) -> str:
    if not isinstance(value, str) or not value:
        return ""
    tree = LexborHTMLParser(value)
    body = tree.body
    if body is None:
        return ""
    parts: list[str] = []
    _consume_html(body, parts)
    return _plain_lines("".join(parts))


def _consume_html(node: Any, parts: list[str]) -> None:
    tag = node.tag
    if not isinstance(tag, str) or tag in {"script", "style"}:
        return
    if tag == "-text":
        text = node.text(deep=False)
        if isinstance(text, str) and text:
            parts.append(text)
        return
    if tag == "br":
        parts.append("\n")
        return
    child = node.child
    while child is not None:
        _consume_html(child, parts)
        child = child.next
    if tag in {"p", "li"}:
        parts.append("\n")


def _plain_lines(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    for space in _SPACE_LIKE:
        normalized = normalized.replace(space, " ")
    lines: list[str] = []
    for line in normalized.split("\n"):
        collapsed = _INLINE_SPACE_RE.sub(" ", line).strip()
        if collapsed:
            lines.append(collapsed)
    return "\n".join(lines)


def _company(employer: object) -> str | None:
    if not isinstance(employer, dict):
        return None
    return _non_empty_str(employer.get("name"))


def _salary(card: Mapping[str, Any], mapping: HhMapping) -> _Salary:
    ranged = card.get("salary_range")
    if isinstance(ranged, dict):
        return _salary_from(ranged, _range_period(ranged, mapping), mapping)
    legacy = card.get("salary")
    if isinstance(legacy, dict):
        # Старое поле salary не несёт mode: в вакансиях hh это месячная вилка.
        return _salary_from(legacy, SalaryPeriod.MONTH, mapping)
    return _Salary()


def _salary_from(
    block: Mapping[str, Any], period: SalaryPeriod | None, mapping: HhMapping
) -> _Salary:
    return _Salary(
        salary_min=_amount(block.get("from")),
        salary_max=_amount(block.get("to")),
        salary_currency=_currency(block.get("currency"), mapping),
        salary_period=period,
        salary_is_gross=_gross(block.get("gross")),
    )


def _range_period(block: Mapping[str, Any], mapping: HhMapping) -> SalaryPeriod | None:
    mode = block.get("mode")
    if not isinstance(mode, dict) or "id" not in mode:
        return None
    mode_id = mode.get("id")
    if not isinstance(mode_id, str) or mode_id not in mapping.salary_range_mode:
        return None
    return mapping.salary_range_mode[mode_id]


def _amount(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _currency(value: object, mapping: HhMapping) -> str | None:
    if not isinstance(value, str):
        return None
    return mapping.currency.get(value)


def _gross(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _experience(
    card: Mapping[str, Any], mapping: HhMapping
) -> tuple[int | None, ExperienceLevel | None]:
    years: int | None = None
    experience = card.get("experience")
    if isinstance(experience, dict):
        experience_id = experience.get("id")
        if isinstance(experience_id, str) and experience_id in mapping.experience_min_years:
            years = mapping.experience_min_years[experience_id]
    level = ExperienceLevel.INTERN if card.get("internship") is True else None
    return years, level


def _employment_type(card: Mapping[str, Any], mapping: HhMapping) -> EmploymentType | None:
    if card.get("internship") is True:
        return EmploymentType.INTERNSHIP
    # TODO: значение таблицы unknown (вахта FLY_IN_FLY_OUT, волонтёрство) нормализатор
    # затем читает как «поля нет» и может заменить типом из текста. Закреплять вахту
    # отдельным enum в 13b нельзя.
    form = card.get("employment_form")
    if isinstance(form, dict):
        return _employment_value(form.get("id"), mapping.employment_form)
    legacy = card.get("employment")
    if isinstance(legacy, dict):
        return _employment_value(legacy.get("id"), mapping.employment)
    return None


def _employment_value(value: object, table: Mapping[str, EmploymentType]) -> EmploymentType | None:
    if not isinstance(value, str):
        return None
    return table.get(value)


def _work_format(card: Mapping[str, Any], mapping: HhMapping) -> WorkFormat | None:
    raw = card.get("work_format")
    if not isinstance(raw, list) or not raw:
        return None
    found: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if isinstance(item_id, str) and item_id in mapping.work_format:
            found.add(item_id)
    if not found:
        return None
    if len(found) == 1:
        return mapping.work_format[next(iter(found))]
    # TODO: несколько форматов hh схлопываются в один WorkFormat по приоритету
    # REMOTE, затем HYBRID, затем ON_SITE/FIELD_WORK; остальные остаются в raw_payload.
    for key, value in mapping.work_format.items():
        if key in found:
            return value
    return None


def _location(card: Mapping[str, Any], areas: AreaIndex | None) -> tuple[str | None, str | None]:
    city = _address_city(card)
    record = _area_record(card, areas)
    if city is None and record is not None and record.is_leaf:
        named = _area_name(card)
        if named is not None:
            city = named
        elif record.name.strip():
            city = record.name
    country = record.country if record is not None and record.country.strip() else None
    return city, country


def _address_city(card: Mapping[str, Any]) -> str | None:
    address = card.get("address")
    if not isinstance(address, dict):
        return None
    return _non_empty_str(address.get("city"))


def _area_name(card: Mapping[str, Any]) -> str | None:
    area = card.get("area")
    if not isinstance(area, dict):
        return None
    return _non_empty_str(area.get("name"))


def _area_record(card: Mapping[str, Any], areas: AreaIndex | None) -> AreaRecord | None:
    if areas is None:
        return None
    area = card.get("area")
    if not isinstance(area, dict):
        return None
    return areas.lookup(area.get("id"))


def _skills(title: str, description_raw: str, card: Mapping[str, Any]) -> tuple[str, ...]:
    dictionary = load_skills_dictionary()
    found: list[str] = []
    seen: set[str] = set()
    raw_skills = card.get("key_skills")
    if isinstance(raw_skills, list):
        for item in raw_skills:
            canon = _skill_canon(item, dictionary)
            if canon is None or canon in seen:
                continue
            seen.add(canon)
            found.append(canon)
    for canon in extract_skills(f"{title}\n{description_raw}", dictionary):
        if canon in seen:
            continue
        seen.add(canon)
        found.append(canon)
    return tuple(found)


def _skill_canon(item: object, dictionary: SkillsDictionary) -> str | None:
    if not isinstance(item, dict):
        return None
    name = item.get("name")
    if not isinstance(name, str):
        return None
    return dictionary.canon_by_alias.get(normalize_skill_token(name))


def _languages(card: Mapping[str, Any], mapping: HhMapping) -> tuple[str, ...]:
    raw = card.get("languages")
    if not isinstance(raw, list):
        return ()
    result: list[str] = []
    seen: set[str] = set()
    for item in raw:
        token = _language_token(item, mapping)
        if token is None or token in seen:
            continue
        seen.add(token)
        result.append(token)
    return tuple(result)


def _language_token(item: object, mapping: HhMapping) -> str | None:
    if not isinstance(item, dict):
        return None
    code_id = item.get("id")
    level = item.get("level")
    if not isinstance(code_id, str) or not isinstance(level, dict):
        return None
    level_id = level.get("id")
    if not isinstance(level_id, str):
        return None
    code = mapping.language.get(code_id)
    level_name = mapping.language_level.get(level_id)
    if code is None or level_name is None:
        return None
    return f"{code}:{level_name}"


def _published_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed
