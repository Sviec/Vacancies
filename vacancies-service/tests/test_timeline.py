"""Хронология опыта: сдвиг месяцев, слияние интервалов, пробелы, стаж."""

from dataclasses import dataclass
from datetime import date

import pytest

from app.services.timeline import (
    Gap,
    add_months,
    find_gaps,
    full_months_between,
    merge_spans,
    position_spans,
    total_experience_months,
)

TODAY = date(2026, 9, 28)


@dataclass(frozen=True)
class Exp:
    company: str
    position: str
    start_date: date
    end_date: date | None = None
    is_current: bool = False
    description: str | None = None
    achievements: str | None = None


@pytest.mark.parametrize(
    ("start", "n", "expected"),
    [
        (date(2021, 1, 31), 1, date(2021, 2, 28)),
        (date(2024, 1, 31), 1, date(2024, 2, 29)),
        (date(2024, 2, 29), 12, date(2025, 2, 28)),
        (date(2020, 11, 15), 3, date(2021, 2, 15)),
        (date(2020, 3, 31), -1, date(2020, 2, 29)),
        (date(2020, 1, 1), 0, date(2020, 1, 1)),
    ],
)
def test_add_months(start: date, n: int, expected: date) -> None:
    assert add_months(start, n) == expected


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (date(2020, 1, 1), date(2020, 7, 1), 6),
        (date(2020, 1, 15), date(2020, 7, 14), 5),
        (date(2020, 1, 15), date(2020, 7, 15), 6),
        (date(2021, 3, 1), date(2022, 1, 1), 10),
        (date(2022, 1, 1), date(2021, 1, 1), 0),
        (date(2020, 1, 1), date(2020, 1, 1), 0),
    ],
)
def test_full_months_between(a: date, b: date, expected: int) -> None:
    assert full_months_between(a, b) == expected


def test_merge_overlapping_and_parallel() -> None:
    spans = position_spans(
        [
            Exp("A", "Dev", date(2018, 1, 1), date(2020, 1, 1)),
            Exp("B", "Dev", date(2019, 6, 1), date(2021, 1, 1)),
            Exp("C", "Mentor", date(2019, 7, 1), date(2019, 9, 1)),
            Exp("D", "Dev", date(2021, 1, 1), date(2022, 1, 1)),
        ],
        TODAY,
    )
    assert merge_spans(spans) == [(date(2018, 1, 1), date(2022, 1, 1))]
    assert total_experience_months(spans) == 48


def test_gap_exactly_six_months_is_not_gap() -> None:
    spans = position_spans(
        [
            Exp("A", "Dev", date(2019, 1, 1), date(2020, 1, 1)),
            Exp("B", "Dev", date(2020, 7, 1), is_current=True),
        ],
        TODAY,
    )
    assert find_gaps(spans, TODAY) == []


def test_gap_six_months_and_one_day_is_gap() -> None:
    spans = position_spans(
        [
            Exp("A", "Dev", date(2019, 1, 1), date(2020, 1, 1)),
            Exp("B", "Dev", date(2020, 7, 2), is_current=True),
        ],
        TODAY,
    )
    assert find_gaps(spans, TODAY) == [
        Gap(start=date(2020, 1, 1), end=date(2020, 7, 2), months=6, trailing=False)
    ]


def test_trailing_gap_only_without_current() -> None:
    finished = [Exp("A", "Dev", date(2019, 1, 1), date(2025, 1, 1))]
    gaps = find_gaps(position_spans(finished, TODAY), TODAY)
    assert gaps == [Gap(start=date(2025, 1, 1), end=TODAY, months=20, trailing=True)]

    recent = [Exp("A", "Dev", date(2019, 1, 1), date(2026, 3, 28))]
    assert find_gaps(position_spans(recent, TODAY), TODAY) == []

    with_current = [*finished, Exp("B", "Dev", date(2015, 1, 1), is_current=True)]
    assert find_gaps(position_spans(with_current, TODAY), TODAY) == []


def test_missing_end_has_zero_length() -> None:
    spans = position_spans([Exp("A", "Dev", date(2020, 5, 1))], TODAY)
    assert spans[0].missing_end is True
    assert spans[0].end == spans[0].start
    assert total_experience_months(spans) == 0


def test_current_position_ends_today() -> None:
    (span,) = position_spans([Exp("A", "Dev", date(2024, 9, 28), is_current=True)], TODAY)
    assert span.end == TODAY
    assert span.missing_end is False
    assert total_experience_months([span]) == 24


def test_empty_experience() -> None:
    assert position_spans([], TODAY) == []
    assert find_gaps([], TODAY) == []
    assert total_experience_months([]) == 0


def test_permutation_does_not_change_result() -> None:
    items = [
        Exp("A", "Dev", date(2015, 1, 1), date(2016, 1, 1)),
        Exp("B", "Dev", date(2017, 3, 1), date(2019, 1, 1)),
        Exp("C", "Dev", date(2020, 1, 1), date(2021, 1, 1)),
        Exp("D", "Dev", date(2020, 1, 1), date(2020, 6, 1)),
    ]
    reference = position_spans(items, TODAY)
    for order in (items[::-1], [items[2], items[0], items[3], items[1]]):
        spans = position_spans(order, TODAY)
        assert spans == reference
        assert find_gaps(spans, TODAY) == find_gaps(reference, TODAY)
    assert len(find_gaps(reference, TODAY)) == 3
