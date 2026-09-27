"""Общие текстовые примитивы нормализатора и словарей.

Модуль не зависит ни от `vocab.py`, ни от `normalizer.py`: оба импортируют его,
и именно поэтому здесь же живёт `city_key_base` — иначе словарь городов и
нормализатор ссылались бы друг на друга.
"""

import re
import unicodedata

DASHES = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"
_DASH_TABLE = str.maketrans(dict.fromkeys(DASHES, "-"))

_SPACES_RE = re.compile(r"\s+")

# Категории, снимаемые по краям строки: символы-пиктограммы, модификаторы,
# невидимые форматные, комбинирующие и вся пунктуация, кроме скобок (Ps/Pe) —
# «Python Developer (Backend)» обязан сохранить закрывающую скобку.
_EDGE_JUNK_CATEGORIES = frozenset({"So", "Sk", "Cf", "Mn", "Me", "Pd", "Pi", "Pf", "Po", "Pc"})
# `+` и `#` — часть названий (C++, C#), по краям их не снимаем.
_EDGE_KEEP = frozenset("+#")

# Служебные кодпоинты эмодзи-последовательностей: модификаторы тона кожи,
# селекторы вариантов, ZWJ и комбинирующий «keycap».
_EMOJI_EXTRA = frozenset(
    [chr(cp) for cp in range(0x1F3FB, 0x1F400)] + ["\ufe0e", "\ufe0f", "\u200d", "\u20e3"]
)

_CITY_PREFIX_RE = re.compile(r"^(?:г\.\s*|г\s+|город\s+)")


def unify_dashes(value: str) -> str:
    """Привести все виды тире и дефисов к ASCII `-`."""
    return value.translate(_DASH_TABLE)


def fold(value: str) -> str:
    """NFKC + casefold + `ё`→`е`: форма для сравнения и поиска по словарям."""
    return unicodedata.normalize("NFKC", value).casefold().replace("ё", "е")


def collapse_spaces(value: str) -> str:
    """Схлопнуть любые пробельные последовательности в один пробел и обрезать края."""
    return _SPACES_RE.sub(" ", value).strip()


def _is_edge_junk(char: str) -> bool:
    if char in _EDGE_KEEP:
        return False
    return char.isspace() or unicodedata.category(char) in _EDGE_JUNK_CATEGORIES


def strip_edge_junk(value: str) -> str:
    """Снять по краям пробелы, эмодзи и пунктуацию (кроме скобок, `+` и `#`)."""
    start = 0
    end = len(value)
    while start < end and _is_edge_junk(value[start]):
        start += 1
    while end > start and _is_edge_junk(value[end - 1]):
        end -= 1
    return value[start:end]


def remove_emoji(value: str) -> str:
    """Удалить эмодзи и служебные символы эмодзи-последовательностей.

    Категория So удаляется целиком, кроме `№`: в вакансиях он значимый.
    """
    return "".join(
        char
        for char in value
        if char not in _EMOJI_EXTRA and (char == "№" or unicodedata.category(char) != "So")
    )


def city_key_base(city: str) -> str:
    """Базовая форма города для ключа: без регистра, «г.»/«город» и краевого мусора."""
    base = unify_dashes(fold(city)).strip()
    base = _CITY_PREFIX_RE.sub("", base)
    return collapse_spaces(strip_edge_junk(base))
