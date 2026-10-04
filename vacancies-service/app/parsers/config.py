"""Разбор `sources.config`: селекторы, пауза между страницами, расписание."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.config import Settings
from app.db.models import Source
from app.parsers.registry import get_parser_class
from app.utils.errors import SourceNotRunnableError

# Хвост после последнего @ — имя атрибута, а не часть CSS.
_ATTR_NAME = re.compile(r"^[A-Za-z_:][\w:.-]*$")

_MIN_PAGE_DELAY_SECONDS = 1.0


def split_selector(spec: str) -> tuple[str, str | None]:
    """`'a.link@href'` → `('a.link', 'href')`. Без `@` — `(spec, None)`.

    Режется по последнему `@`, если хвост — имя атрибута
    `^[A-Za-z_:][\\w:.-]*$`.
    """
    if "@" not in spec:
        return spec, None
    selector, _, attr = spec.rpartition("@")
    if selector and _ATTR_NAME.fullmatch(attr):
        return selector, attr
    return spec, None


def page_delay_seconds(config_delay: float | None, settings: Settings) -> float:
    """Не меньше секунды: явная пауза источника, иначе `http_request_delay_seconds`."""
    chosen = settings.http_request_delay_seconds if config_delay is None else config_delay
    return max(_MIN_PAGE_DELAY_SECONDS, float(chosen))


@dataclass(frozen=True, slots=True)
class ScheduleSpec:
    """Один источник в расписании планировщика."""

    source_id: UUID
    interval_seconds: int


def schedules_for(sources: Sequence[Source], settings: Settings) -> list[ScheduleSpec]:
    """Расписание обхода.

    Пусто, если парсеры выключены. Иначе только включённые, не демо, с типом
    в реестре. `interval_hours` короче часа заменяется дефолтом из настроек.
    """
    if not settings.parsers_enabled:
        return []
    specs: list[ScheduleSpec] = []
    for source in sources:
        if not source.is_enabled or source.config.get("demo") is True:
            continue
        try:
            get_parser_class(source.source_type)
        except SourceNotRunnableError:
            continue
        specs.append(
            ScheduleSpec(
                source_id=source.id,
                interval_seconds=_interval_seconds(source.config, settings),
            )
        )
    return specs


def _interval_seconds(config: Mapping[str, Any], settings: Settings) -> int:
    raw = config.get("interval_hours")
    if isinstance(raw, bool) or not isinstance(raw, int | float) or raw < 1:
        hours: int | float = settings.parser_default_interval_hours
    else:
        hours = raw
    return int(hours * 3600)
