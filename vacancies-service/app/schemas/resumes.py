"""Схемы резюме и вложенных секций (сверка имён с ORM Resume*)."""

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.enums import LanguageLevel, ResumeOrigin, WorkFormat
from app.schemas.common import CurrencyCode


class ResumeContacts(BaseModel):
    """Контакты резюме: фиксированный набор ключей (зеркало JSONB contacts)."""

    model_config = ConfigDict(extra="forbid")

    email: str | None = None
    phone: str | None = None
    telegram: str | None = None
    linkedin: str | None = None
    github: str | None = None
    website: str | None = None


class ResumeExperienceCreate(BaseModel):
    """Позиция в опыте работы (вход)."""

    model_config = ConfigDict(extra="forbid")

    company: str
    position: str
    start_date: date
    end_date: date | None = None
    is_current: bool = False
    description: str | None = None
    achievements: str | None = None

    @model_validator(mode="after")
    def _validate_dates(self) -> "ResumeExperienceCreate":
        # Календарная «сегодня» в UTC (эквивалент date.today() из допущений этапа).
        today = datetime.now(tz=UTC).date()
        if self.start_date > today:
            msg = "start_date must not be in the future"
            raise ValueError(msg)
        if self.end_date is not None:
            if self.end_date > today:
                msg = "end_date must not be in the future"
                raise ValueError(msg)
            if self.end_date <= self.start_date:
                msg = "end_date must be greater than start_date"
                raise ValueError(msg)
        if self.is_current and self.end_date is not None:
            msg = "end_date must be null when is_current is true"
            raise ValueError(msg)
        return self


class ResumeExperienceRead(BaseModel):
    """Позиция в опыте работы (чтение из ORM)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company: str
    position: str
    start_date: date
    end_date: date | None
    is_current: bool
    description: str | None
    achievements: str | None


class ResumeEducationCreate(BaseModel):
    """Образование (вход)."""

    model_config = ConfigDict(extra="forbid")

    institution: str
    degree: str | None = None
    field: str | None = None
    start_year: int | None = Field(default=None, ge=1900, le=2100)
    end_year: int | None = Field(default=None, ge=1900, le=2100)

    @model_validator(mode="after")
    def _validate_years(self) -> "ResumeEducationCreate":
        if (
            self.start_year is not None
            and self.end_year is not None
            and self.end_year < self.start_year
        ):
            msg = "end_year must be greater than or equal to start_year"
            raise ValueError(msg)
        return self


class ResumeEducationRead(BaseModel):
    """Образование (чтение из ORM)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    institution: str
    degree: str | None
    field: str | None
    start_year: int | None
    end_year: int | None


class ResumeSkillCreate(BaseModel):
    """Навык в резюме (вход). skill уже должен быть lowercase — без автоприведения."""

    model_config = ConfigDict(extra="forbid")

    skill: str = Field(min_length=1)
    level: int | None = Field(default=None, ge=1, le=5)

    @field_validator("skill")
    @classmethod
    def skill_must_be_lowercase(cls, value: str) -> str:
        if value != value.lower():
            msg = "skill must be lowercase"
            raise ValueError(msg)
        return value


class ResumeSkillRead(BaseModel):
    """Навык в резюме (чтение из ORM)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    skill: str
    level: int | None


class ResumeCourseCreate(BaseModel):
    """Курс или сертификат (вход)."""

    model_config = ConfigDict(extra="forbid")

    title: str
    provider: str | None = None
    year: int | None = Field(default=None, ge=1900, le=2100)
    certificate_url: str | None = None


class ResumeCourseRead(BaseModel):
    """Курс или сертификат (чтение из ORM)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    provider: str | None
    year: int | None
    certificate_url: str | None


class ResumeLanguageCreate(BaseModel):
    """Владение языком (вход)."""

    model_config = ConfigDict(extra="forbid")

    language: str
    level: LanguageLevel


class ResumeLanguageRead(BaseModel):
    """Владение языком (чтение из ORM)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    language: str
    level: LanguageLevel


class ResumeCreate(BaseModel):
    """Создание резюме. score / score_details на входе не принимаются."""

    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    title: str
    is_primary: bool = False
    origin: ResumeOrigin = ResumeOrigin.MANUAL
    target_position: str | None = None
    desired_salary_min: int | None = Field(default=None, ge=0)
    desired_salary_currency: CurrencyCode | None = None
    desired_country: str | None = None
    desired_city: str | None = None
    desired_work_format: WorkFormat | None = None
    summary: str | None = None
    contacts: ResumeContacts = Field(default_factory=ResumeContacts)
    experience: list[ResumeExperienceCreate] = Field(default_factory=list)
    education: list[ResumeEducationCreate] = Field(default_factory=list)
    skills: list[ResumeSkillCreate] = Field(default_factory=list)
    courses: list[ResumeCourseCreate] = Field(default_factory=list)
    languages: list[ResumeLanguageCreate] = Field(default_factory=list)


class ResumeUpdate(BaseModel):
    """Частичное обновление резюме.

    На этапе 5 вызывать `model_dump(exclude_unset=True)`: отсутствие поля
    в теле запроса ≠ null / пустой список; явный пустой список = очистка
    коллекции. Без обязательного `user_id`.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    is_primary: bool | None = None
    origin: ResumeOrigin | None = None
    target_position: str | None = None
    desired_salary_min: int | None = Field(default=None, ge=0)
    desired_salary_currency: CurrencyCode | None = None
    desired_country: str | None = None
    desired_city: str | None = None
    desired_work_format: WorkFormat | None = None
    summary: str | None = None
    contacts: ResumeContacts | None = None
    experience: list[ResumeExperienceCreate] | None = None
    education: list[ResumeEducationCreate] | None = None
    skills: list[ResumeSkillCreate] | None = None
    courses: list[ResumeCourseCreate] | None = None
    languages: list[ResumeLanguageCreate] | None = None


class ResumeRead(BaseModel):
    """Полное резюме: колонки ORM + вложенные Read-секции."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    title: str
    is_primary: bool
    origin: ResumeOrigin
    target_position: str | None
    desired_salary_min: int | None
    desired_salary_currency: str | None
    desired_country: str | None
    desired_city: str | None
    desired_work_format: WorkFormat | None
    summary: str | None
    contacts: ResumeContacts
    score: float | None = Field(default=None, ge=0, le=10)
    # Зеркало JSONB score_details — не строгий список критериев (см. scoring.py).
    score_details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    experience: list[ResumeExperienceRead] = Field(default_factory=list)
    education: list[ResumeEducationRead] = Field(default_factory=list)
    skills: list[ResumeSkillRead] = Field(default_factory=list)
    courses: list[ResumeCourseRead] = Field(default_factory=list)
    languages: list[ResumeLanguageRead] = Field(default_factory=list)
