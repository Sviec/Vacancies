"""Схемы источников и запусков парсера."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.enums import RunStatus, SourceType


class SourceListItem(BaseModel):
    """Источник в списке. Без config (секреты/селекторы наружу не отдаём)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    source_type: SourceType
    is_enabled: bool
    last_run_at: datetime | None
    last_run_status: RunStatus | None
    last_error: str | None


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
