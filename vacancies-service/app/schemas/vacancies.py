"""Схемы API вакансий: карточка, деталь, список, фильтры, действия."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    # Атрибута в ORM нет: from_attributes берёт дефолт, сервис заполняет поле.
    user_actions: list[UserAction] = Field(default_factory=list)


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
    is_active: bool
    postings: list[VacancyPostingBriefRead] = Field(default_factory=list)


MAX_SOURCE_FILTER_VALUES = 20


class VacancyListQuery(BaseModel):
    """Параметры поиска и фильтров ленты (п. 5.5 ТЗ).

    Списки в query-строке передаются повтором ключа
    (`experience_level=junior&experience_level=middle`).
    """

    model_config = ConfigDict(extra="forbid")

    q: str | None = None
    # TODO: отклонение от п. 5.5 и п. 6 ТЗ по решению пользователя — фильтра
    # `skills[]` нет: лента ищет по всем вакансиям, навыки пользователя
    # учитываются через резюме в подборе (матчинг этапа 6). `?skills=` → 422.
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
    # «Сохранённые отдельным списком» (п. 5.7 ТЗ).
    saved_only: bool = False
    sort: VacancySort = VacancySort.RELEVANCE
    page: PageNumber = 1
    page_size: PageSize = 20

    @field_validator("q", "country", "city")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("source")
    @classmethod
    def _clean_sources(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [item.strip() for item in value if item.strip()]
        if len(cleaned) > MAX_SOURCE_FILTER_VALUES:
            msg = f"at most {MAX_SOURCE_FILTER_VALUES} sources are allowed"
            raise ValueError(msg)
        return cleaned or None

    @field_validator("published_after")
    @classmethod
    def _assume_utc(cls, value: datetime | None) -> datetime | None:
        # TODO: время без зоны (в т.ч. голая дата `2026-09-01`) считается UTC.
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            return value.replace(tzinfo=UTC)
        return value


VacancyListResponse = PaginatedResponse[VacancyCardRead]


class VacancyUserState(BaseModel):
    """Текущее множество действий пользователя над вакансией (ответ на action)."""

    vacancy_id: UUID
    actions: list[UserAction]


class VacancyActionRequest(BaseModel):
    """Тело POST /vacancies/{id}/action (п. 5.7 ТЗ)."""

    model_config = ConfigDict(extra="forbid")

    action: UserAction


class VacancyFiltersMeta(BaseModel):
    """Доступные значения фильтров (GET /vacancies/filters/meta)."""

    # TODO: `top_skills` из п. 5.5 ТЗ убран вместе с фильтром по навыкам
    # (решение пользователя); навыки учитываются матчингом этапа 6.
    countries: list[str]
    cities: list[str]
    sources: list[str]
    currencies: list[str]
