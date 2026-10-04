"""Схемы источников и запусков парсера."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.enums import RunStatus, SourceType

# TODO: из `config` наружу отдаётся только один ключ по белому списку —
# `channel` для Telegram и `url` для HTML; селекторы, пагинация, фильтры и
# флаг `demo` остаются внутри.
_LOCATION_KEYS: dict[SourceType, str] = {
    SourceType.TELEGRAM: "channel",
    SourceType.HTML: "url",
}


def source_location(source_type: SourceType, config: dict[str, Any]) -> str | None:
    """Канал или адрес источника из `config`; не строка или нет ключа — `None`."""
    key = _LOCATION_KEYS.get(source_type)
    if key is None:
        return None
    value = config.get(key)
    return value if isinstance(value, str) and value else None


class SourceListItem(BaseModel):
    """Источник в списке. Без config (секреты/селекторы наружу не отдаём)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    source_type: SourceType
    is_enabled: bool
    location: str | None = None
    last_run_at: datetime | None
    last_run_status: RunStatus | None
    last_error: str | None
    # Счётчики последнего запуска из `parse_runs`; запусков не было — `None`.
    last_run_items_found: int | None = None
    last_run_items_new: int | None = None


class SourceListResponse(BaseModel):
    """Ответ GET /sources."""

    items: list[SourceListItem]


class ParseRunRead(BaseModel):
    """Один запуск парсера (чтение из ORM ParseRun)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    started_at: datetime
    finished_at: datetime | None
    status: RunStatus
    items_found: int
    items_new: int
    error_text: str | None


MAX_RUNS = 200


class ParseRunListQuery(BaseModel):
    """Параметры GET /sources/runs."""

    model_config = ConfigDict(extra="forbid")

    source_id: UUID | None = None
    status: RunStatus | None = None
    # TODO: история без пагинации; `limit` по умолчанию 50, максимум 200.
    limit: int = Field(50, ge=1, le=MAX_RUNS)


class ParseRunListResponse(BaseModel):
    """Ответ GET /sources/runs: свежие запуски сверху."""

    items: list[ParseRunRead]


class SourceRunAccepted(BaseModel):
    """Ответ POST /sources/{id}/run: задача поставлена в очередь, обход ещё не начался."""

    source_id: UUID
    job_id: str
