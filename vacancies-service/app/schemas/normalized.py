"""Контракт парсера: NormalizedVacancy (раздел 3 ТЗ)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.enums import (
    EmploymentType,
    ExperienceLevel,
    ParseQuality,
    SalaryPeriod,
    SourceType,
    WorkFormat,
)
from app.schemas.common import ContentHashHex, CurrencyCode, validate_salary_range


class NormalizedVacancy(BaseModel):
    """Контракт парсера / одной публикации в источнике.

    `content_hash` — идентичность текста в источнике (формат: 64 hex lowercase),
    НЕ ключ склейки канонической вакансии. `dedup_key` считает этап 4
    (нормализатор) и в эту схему не входит.
    """

    model_config = ConfigDict(extra="forbid")

    # --- Идентификация ---
    external_id: str
    source: str
    source_type: SourceType
    url: str | None = None

    # --- Основное ---
    title: str
    company: str | None = None
    description_raw: str
    description_clean: str

    # --- Локация ---
    country: str | None = None
    city: str | None = None
    work_format: WorkFormat = WorkFormat.UNKNOWN
    relocation_support: bool | None = None

    # --- Деньги ---
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    salary_currency: CurrencyCode | None = None
    salary_period: SalaryPeriod | None = None
    salary_is_gross: bool | None = None

    # --- Требования ---
    skills: list[str] = Field(default_factory=list)
    experience_min_years: int | None = Field(default=None, ge=0, le=60)
    experience_level: ExperienceLevel = ExperienceLevel.UNKNOWN
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    education_required: str | None = None
    languages: list[str] = Field(default_factory=list)

    # --- Мета ---
    published_at: datetime | None = None
    parsed_at: datetime
    parse_quality: ParseQuality = ParseQuality.FULL
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    content_hash: ContentHashHex

    @model_validator(mode="after")
    def _check_salary_range(self) -> "NormalizedVacancy":
        validate_salary_range(self.salary_min, self.salary_max)
        return self
