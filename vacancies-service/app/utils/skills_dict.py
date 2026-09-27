"""Словарь навыков: синонимы → канон и паттерны поиска навыков в тексте.

Данные живут в `app/data/skills.json`, а не в коде: новый навык или синоним —
правка JSON без изменения Python. Модуль только валидирует и компилирует.
"""

import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

from app.utils.text import collapse_spaces

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

_CYRILLIC_RE = re.compile(r"[а-я]")
_CYRILLIC_VOWELS = frozenset("аеиоуыэюяйь")

# Границы навыка в тексте. Слева не должно быть буквы/цифры, `+`, `#` и точки
# (иначе `js` ловится внутри `node.js`, а `.net` — внутри `asp.net`); справа —
# буквы/цифры, `+`, `#` и «точка + слово» (`vue` не ловится в `vue.js`).
_LEFT_BOUNDARY = r"(?<![\w+#.])"
_RIGHT_BOUNDARY = r"(?![\w+#]|\.\w)"


@dataclass(frozen=True, slots=True)
class SkillsDictionary:
    """Скомпилированный словарь навыков. Неизменяемый — безопасно кэшировать."""

    canon_by_alias: Mapping[str, str]
    extraction_patterns: tuple[tuple[re.Pattern[str], str], ...]
    case_sensitive_patterns: tuple[tuple[re.Pattern[str], str], ...]
    text_extraction_exclude: frozenset[str]


def normalize_skill_token(value: str) -> str:
    """NFKC, нижний регистр, `ё`→`е`, схлопнутые пробелы."""
    return collapse_spaces(unicodedata.normalize("NFKC", value).lower().replace("ё", "е"))


def fold_case_keep_length(text: str) -> str:
    """Нижний регистр и `ё`→`е` посимвольно, с сохранением длины и позиций.

    `str.lower()` длину не сохраняет (`"İ".lower()` — два символа), а позиции
    совпадений по свёрнутому тексту сравниваются с позициями по исходному.
    """
    lowered = text.lower()
    if len(lowered) != len(text):
        lowered = "".join(low if len(low := char.lower()) == 1 else char for char in text)
    return lowered.replace("ё", "е")


def _alias_pattern(alias: str) -> re.Pattern[str]:
    stem = alias
    suffix = ""
    if _CYRILLIC_RE.fullmatch(alias[-1]):
        # TODO: кириллические синонимы ловят падежные окончания до 3 букв; у
        # синонима на гласную она отбрасывается («кафка» → «кафкой»).
        if alias[-1] in _CYRILLIC_VOWELS and len(alias) > 3:
            stem = alias[:-1]
        suffix = "[а-я]{0,3}"
    body = r"\s+".join(re.escape(part) for part in stem.split(" "))
    return re.compile(_LEFT_BOUNDARY + body + suffix + _RIGHT_BOUNDARY)


def _require_str_list(value: Any, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        msg = f"{where}: expected a list of strings"
        raise ValueError(msg)
    return list(value)


def build_skills_dictionary(data: Mapping[str, Any]) -> SkillsDictionary:
    """Проверить и скомпилировать словарь навыков из разобранного JSON."""
    skills = data.get("skills")
    if not isinstance(skills, Mapping):
        msg = "skills: expected an object"
        raise ValueError(msg)

    canons: set[str] = set()
    for canon in skills:
        if not isinstance(canon, str) or not canon or canon != normalize_skill_token(canon):
            msg = f"skills: canon {canon!r} must be a non-empty normalized lowercase string"
            raise ValueError(msg)
        canons.add(canon)

    canon_by_alias: dict[str, str] = {}
    for canon, synonyms in skills.items():
        aliases = [canon, *_require_str_list(synonyms, f"skills[{canon!r}]")]
        for alias in aliases:
            key = normalize_skill_token(alias)
            if not key:
                msg = f"skills[{canon!r}]: empty synonym"
                raise ValueError(msg)
            if key in canons and key != canon:
                msg = f"skills[{canon!r}]: synonym {key!r} is itself a canon"
                raise ValueError(msg)
            previous = canon_by_alias.get(key)
            if previous is not None and previous != canon:
                msg = f"skills: synonym {key!r} maps to both {previous!r} and {canon!r}"
                raise ValueError(msg)
            canon_by_alias[key] = canon

    exclude = {
        normalize_skill_token(item)
        for item in _require_str_list(data.get("text_extraction_exclude", []), "exclude")
    }
    for alias in sorted(exclude):
        if alias not in canon_by_alias:
            msg = f"text_extraction_exclude: {alias!r} is not in the dictionary"
            raise ValueError(msg)

    case_sensitive: dict[str, str] = {}
    for item in _require_str_list(
        data.get("text_extraction_case_sensitive", []), "text_extraction_case_sensitive"
    ):
        token = collapse_spaces(unicodedata.normalize("NFKC", item))
        alias = normalize_skill_token(token)
        if alias not in canon_by_alias:
            msg = f"text_extraction_case_sensitive: {item!r} is not in the dictionary"
            raise ValueError(msg)
        case_sensitive[token] = canon_by_alias[alias]
    case_insensitive_skip = exclude | {normalize_skill_token(token) for token in case_sensitive}

    # TODO: однобуквенные и омонимичные навыки (c, r, express) в тексте не
    # ищутся — только в явном списке навыков источника.
    patterns = tuple(
        (_alias_pattern(alias), canon)
        for alias, canon in sorted(canon_by_alias.items(), key=lambda kv: (-len(kv[0]), kv[0]))
        if alias not in case_insensitive_skip
    )
    # TODO: регистрозависимый поиск не спасает от «Go» в начале английского
    # предложения; принято, т.к. посты в основном русскоязычные.
    exact_case_patterns = tuple(
        (_alias_pattern(token), canon)
        for token, canon in sorted(case_sensitive.items(), key=lambda kv: (-len(kv[0]), kv[0]))
    )
    return SkillsDictionary(
        canon_by_alias=MappingProxyType(canon_by_alias),
        extraction_patterns=patterns,
        case_sensitive_patterns=exact_case_patterns,
        text_extraction_exclude=frozenset(exclude),
    )


@lru_cache(maxsize=1)
def load_skills_dictionary() -> SkillsDictionary:
    """Загрузить `app/data/skills.json` (один раз за процесс)."""
    with (DATA_DIR / "skills.json").open(encoding="utf-8") as file:
        data: Any = json.load(file)
    if not isinstance(data, Mapping):
        msg = "skills.json: expected an object at the top level"
        raise ValueError(msg)
    return build_skills_dictionary(data)
