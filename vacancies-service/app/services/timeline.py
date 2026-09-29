"""Хронология опыта работы: интервалы, пробелы и суммарный стаж (п. 5.4 ТЗ).

Чистый модуль: ни БД, ни часов. «Сегодня» — обязательный параметр, поэтому
один и тот же вход всегда даёт один и тот же результат. Общий для
`resume_scorer.py` (критерий «Хронология») и `matching.py` (уровень по стажу).
"""

import calendar
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from typing import Protocol

GAP_THRESHOLD_MONTHS = 6


class ExperienceLike(Protocol):
    """Позиция опыта: подходят ORM `ResumeExperience` и `ResumeExperienceCreate`."""

    @property
    def company(self) -> str: ...
    @property
    def position(self) -> str: ...
    @property
    def start_date(self) -> date: ...
    @property
    def end_date(self) -> date | None: ...
    @property
    def is_current(self) -> bool: ...
    @property
    def description(self) -> str | None: ...
    @property
    def achievements(self) -> str | None: ...


@dataclass(frozen=True, slots=True)
class PositionSpan:
    """Позиция как закрытый интервал дат."""

    company: str
    position: str
    start: date
    end: date
    is_current: bool
    missing_end: bool


@dataclass(frozen=True, slots=True)
class Gap:
    """Пробел в опыте длиннее порога."""

    start: date
    end: date
    months: int
    trailing: bool


def add_months(d: date, n: int) -> date:
    """Сдвиг на `n` месяцев; день обрезается до конца месяца (31.01 + 1 → 28/29.02)."""
    index = d.year * 12 + (d.month - 1) + n
    year, month0 = divmod(index, 12)
    month = month0 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def full_months_between(a: date, b: date) -> int:
    """Число полных месяцев от `a` до `b`, не меньше 0."""
    months = (b.year - a.year) * 12 + (b.month - a.month) - (1 if b.day < a.day else 0)
    return max(months, 0)


def position_spans(experience: Sequence[ExperienceLike], today: date) -> list[PositionSpan]:
    """Интервалы позиций, отсортированные независимо от порядка входа."""
    # TODO: позиция без `end_date` и без `is_current` — нарушение
    # последовательности; её интервал имеет нулевую длину (end = start).
    spans: list[PositionSpan] = []
    for item in experience:
        missing_end = item.end_date is None and not item.is_current
        if item.is_current:
            end = max(today, item.start_date)
        elif item.end_date is not None:
            end = item.end_date
        else:
            end = item.start_date
        spans.append(
            PositionSpan(
                company=item.company,
                position=item.position,
                start=item.start_date,
                end=end,
                is_current=item.is_current,
                missing_end=missing_end,
            )
        )
    spans.sort(key=lambda s: (s.start, s.end, s.company, s.position, s.is_current))
    return spans


def merge_spans(spans: Sequence[PositionSpan]) -> list[tuple[date, date]]:
    """Объединить перекрывающиеся и параллельные интервалы (стаж не удваивается)."""
    merged: list[tuple[date, date]] = []
    for span in sorted(spans, key=lambda s: (s.start, s.end)):
        if merged and span.start <= merged[-1][1]:
            start, end = merged[-1]
            merged[-1] = (start, max(end, span.end))
        else:
            merged.append((span.start, span.end))
    return merged


def find_gaps(
    spans: Sequence[PositionSpan],
    today: date,
    *,
    threshold_months: int = GAP_THRESHOLD_MONTHS,
) -> list[Gap]:
    """Пробелы длиннее порога; ровно `threshold_months` месяцев — не пробел."""
    # TODO: все пробелы считаются необъяснёнными (поля пояснения нет);
    # хвостовой пробел до «сегодня» учитывается — без текущей работы оценка
    # со временем может снижаться.
    merged = merge_spans(spans)
    gaps: list[Gap] = []
    for (_, prev_end), (next_start, _) in pairwise(merged):
        if next_start > add_months(prev_end, threshold_months):
            gaps.append(
                Gap(
                    start=prev_end,
                    end=next_start,
                    months=full_months_between(prev_end, next_start),
                    trailing=False,
                )
            )
    if merged and not any(span.is_current for span in spans):
        last_end = merged[-1][1]
        if today > add_months(last_end, threshold_months):
            gaps.append(
                Gap(
                    start=last_end,
                    end=today,
                    months=full_months_between(last_end, today),
                    trailing=True,
                )
            )
    return gaps


def total_experience_months(spans: Sequence[PositionSpan]) -> int:
    """Суммарный стаж в полных месяцах по объединённым интервалам."""
    return sum(full_months_between(start, end) for start, end in merge_spans(spans))
