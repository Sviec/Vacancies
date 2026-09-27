"""Разбор зарплаты: `parse_salary` и `extract_salary_from_text` (п. 5.3 плана этапа 4)."""

import pytest

from app.enums import SalaryPeriod
from app.services.normalizer import (
    EMPTY_SALARY,
    SalaryParseResult,
    extract_salary_from_text,
    parse_salary,
)

MONTH = SalaryPeriod.MONTH
YEAR = SalaryPeriod.YEAR
HOUR = SalaryPeriod.HOUR


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("от 150 000 руб.", (150000, None, "RUB", MONTH, None)),
        ("150-200к", (150000, 200000, None, MONTH, None)),
        ("$3000-4000", (3000, 4000, "USD", MONTH, None)),
        ("до 250т.р.", (None, 250000, "RUB", MONTH, None)),
        ("з/п по договорённости", EMPTY_SALARY),
        ("150\u00a0000 – 200\u00a0000 ₽", (150000, 200000, "RUB", MONTH, None)),
        ("150\u202f000—200\u202f000 руб", (150000, 200000, "RUB", MONTH, None)),
        ("от 150 до 200 тыс. руб. на руки", (150000, 200000, "RUB", MONTH, False)),
        ("3k-4k USD", (3000, 4000, "USD", MONTH, None)),
        ("€5000", (5000, 5000, "EUR", MONTH, None)),
        ("от 1,5 млн руб. в год", (1500000, None, "RUB", YEAR, None)),
        ("2000–2500 $ gross", (2000, 2500, "USD", MONTH, True)),
        ("до 300 000 ₽ до вычета НДФЛ", (None, 300000, "RUB", MONTH, True)),
        ("25 $/h", (25, 25, "USD", HOUR, None)),
        ("1500 руб в час", (1500, 1500, "RUB", HOUR, None)),
        ("120 000 — 180 000 рублей net", (120000, 180000, "RUB", MONTH, False)),
        ("от 200к", (200000, None, None, MONTH, None)),
        ("250 т.р.", (250000, 250000, "RUB", MONTH, None)),
        ("4 000 - 5 000 EUR в месяц", (4000, 5000, "EUR", MONTH, None)),
        ("200-150к", (150000, 200000, None, MONTH, None)),
        ("100 000 руб. + бонус 20%", (100000, 100000, "RUB", MONTH, None)),
        ("$120,000 per year", (120000, 120000, "USD", YEAR, None)),
        ("1.5kk", (1500000, 1500000, None, MONTH, None)),
        ("от 99 999 999 999 руб", EMPTY_SALARY),
        ("", EMPTY_SALARY),
        (None, EMPTY_SALARY),
        ("   ", EMPTY_SALARY),
        ("competitive", EMPTY_SALARY),
        ("по результатам собеседования", EMPTY_SALARY),
    ],
)
def test_parse_salary(text: str | None, expected: tuple[object, ...]) -> None:
    assert parse_salary(text) == SalaryParseResult(*expected)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Опыт от 3 лет\nЗарплата: от 200 000 ₽ на руки", (200000, None, "RUB", MONTH, False)),
        ("Опыт 3+ лет, компания основана в 2010 году, бонус 15%", EMPTY_SALARY),
        ("Предлагаем: 💰 3000-4000$", (3000, 4000, "USD", MONTH, None)),
        ("Ждём тебя в 2026 году", EMPTY_SALARY),
        ("Зарплата по договорённости\nВилка: 200-300к", (200000, 300000, None, MONTH, None)),
    ],
)
def test_extract_salary_from_text(text: str, expected: tuple[object, ...]) -> None:
    assert extract_salary_from_text(text) == SalaryParseResult(*expected)


def test_range_word_between_numbers_not_a_separator() -> None:
    """Два числа без «-»/«до» между ними — берётся только первое."""
    assert parse_salary("200 000 руб, премия 50 000") == SalaryParseResult(
        200000, 200000, "RUB", MONTH, None
    )
