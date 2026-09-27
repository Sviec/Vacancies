"""Схемы API вакансий: карточка, деталь, список, фильтры, действия."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.enums import (
    EmploymentType,
    ExperienceLevel,
    ParseQuality,
    SalaryPeriod,
    SourceType,
    UserAction,
    WorkFormat,
)
from app.schemas.common import (
    CurrencyCode,
    PageNumber,
    PageSize,
    PaginatedResponse,
    VacancySort,
)


class VacancyCardRead(BaseModel):
    """Карточка вакансии в ленте (проекция канонической ORM Vacancy)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    company: str | None
    city: str | None
    country: str | None
    work_format: WorkFormat
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    salary_period: SalaryPeriod | None
    salary_is_gross: bool | None
    skills: list[str]
    published_at: datetime | None
    source: str
    postings_count: int
    parse_quality: ParseQuality


class VacancyPostingBriefRead(BaseModel):
    """Краткая публикация для блока «Источники» на карточке."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: str
    source_type: SourceType
    url: str | None
    external_id: str
    published_at: datetime | None
    parse_quality: ParseQuality


class VacancyDetailRead(VacancyCardRead):
    """Полная карточка: поля ленты + описание, требования и публикации."""

    description_clean: str
    url: str | None
    relocation_support: bool | None
    experience_min_years: int | None
    experience_level: ExperienceLevel
    employment_type: EmploymentType
    education_required: str | None
    languages: list[str]
    last_seen_at: datetime
    source_type: SourceType
    postings: list[VacancyPostingBriefRead] = Field(default_factory=list)


class VacancyListQuery(BaseModel):
    """Параметры поиска и фильтров ленты (п. 5.5 ТЗ)."""

    model_config = ConfigDict(extra="forbid")

    q: str | None = None
    skills: list[str] | None = None
    experience_level: list[ExperienceLevel] | None = None
    employment_type: list[EmploymentType] | None = None
    work_format: list[WorkFormat] | None = None
    country: str | None = None
    city: str | None = None
    salary_min: int | None = Field(default=None, ge=0)
    salary_currency: CurrencyCode | None = None
    source: list[str] | None = None
    published_after: datetime | None = None
    has_salary: bool | None = None
    relocation_support: bool | None = None
    exclude_hidden: bool = True
    sort: VacancySort = VacancySort.RELEVANCE
    page: PageNumber = 1
    page_size: PageSize = 20


VacancyListResponse = PaginatedResponse[VacancyCardRead]


class VacancyActionRequest(BaseModel):
    """Тело POST /vacancies/{id}/action (п. 5.7 ТЗ)."""

    model_config = ConfigDict(extra="forbid")

    action: UserAction


class VacancyFiltersMeta(BaseModel):
    """Доступные значения фильтров (GET /vacancies/filters/meta)."""

    countries: list[str]
    cities: list[str]
    sources: list[str]
    top_skills: list[str]
