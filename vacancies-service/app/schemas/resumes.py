"""Схемы резюме и вложенных секций (сверка имён с ORM Resume*)."""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.enums import LanguageLevel, ResumeOrigin, WorkFormat
from app.schemas.common import CurrencyCode

# Длины повторяют колонки БД: без них слишком длинная строка проходила бы
# схему и падала бы в PostgreSQL с 500 вместо 422.
RequiredStr255 = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]
Str255 = Annotated[str, StringConstraints(max_length=255)]
Str100 = Annotated[str, StringConstraints(max_length=100)]
SkillName = Annotated[str, StringConstraints(min_length=1, max_length=100)]
LanguageName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
SalaryInt = Annotated[int, Field(ge=0, le=2_147_483_647)]


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

    company: RequiredStr255
    position: RequiredStr255
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

    institution: RequiredStr255
    degree: Str255 | None = None
    field: Str255 | None = None
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
    """Навык в резюме (вход) в любом написании.

    К канону (`normalize_skills`: регистр, алиасы) навык приводит сервисный
    слой при записи, поэтому `Python` и `JS` здесь допустимы.
    """

    model_config = ConfigDict(extra="forbid")

    skill: SkillName
    level: int | None = Field(default=None, ge=1, le=5)


class ResumeSkillRead(BaseModel):
    """Навык в резюме (чтение из ORM)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    skill: str
    level: int | None


class ResumeCourseCreate(BaseModel):
    """Курс или сертификат (вход)."""

    model_config = ConfigDict(extra="forbid")

    title: RequiredStr255
    provider: Str255 | None = None
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

    language: LanguageName
    level: LanguageLevel


class ResumeLanguageRead(BaseModel):
    """Владение языком (чтение из ORM)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    language: str
    level: LanguageLevel


def _ensure_unique_languages(items: Sequence[ResumeLanguageCreate] | None) -> None:
    """Повтор языка (без учёта регистра и пробелов) нарушил бы UNIQUE в БД."""
    seen: set[str] = set()
    for item in items or ():
        key = item.language.strip().casefold()
        if key in seen:
            msg = f"duplicate language: {item.language}"
            raise ValueError(msg)
        seen.add(key)


class ResumeCreate(BaseModel):
    """Создание резюме.

    `user_id` приходит из зависимости `get_current_user_id`, `origin` ставит
    сервер; score / score_details на входе не принимаются.
    """

    model_config = ConfigDict(extra="forbid")

    title: RequiredStr255
    is_primary: bool = False
    target_position: Str255 | None = None
    desired_salary_min: SalaryInt | None = None
    desired_salary_currency: CurrencyCode | None = None
    desired_country: Str100 | None = None
    desired_city: Str100 | None = None
    desired_work_format: WorkFormat | None = None
    summary: str | None = None
    contacts: ResumeContacts = Field(default_factory=ResumeContacts)
    experience: list[ResumeExperienceCreate] = Field(default_factory=list)
    education: list[ResumeEducationCreate] = Field(default_factory=list)
    skills: list[ResumeSkillCreate] = Field(default_factory=list)
    courses: list[ResumeCourseCreate] = Field(default_factory=list)
    languages: list[ResumeLanguageCreate] = Field(default_factory=list)

    @field_validator("languages")
    @classmethod
    def _unique_languages(cls, value: list[ResumeLanguageCreate]) -> list[ResumeLanguageCreate]:
        _ensure_unique_languages(value)
        return value


# Поля, для которых явный `null` в PATCH бессмыслен: NOT NULL в БД или коллекция.
_NON_NULLABLE_UPDATE_FIELDS = (
    "title",
    "is_primary",
    "contacts",
    "experience",
    "education",
    "skills",
    "courses",
    "languages",
)


class ResumeUpdate(BaseModel):
    """Частичное обновление резюме.

    Сервис вызывает `model_dump(exclude_unset=True)`: отсутствие поля
    в теле запроса ≠ null / пустой список; явный пустой список = очистка
    коллекции. Явный `null` допустим только у nullable-полей (очистка).
    """

    model_config = ConfigDict(extra="forbid")

    title: RequiredStr255 | None = None
    is_primary: bool | None = None
    target_position: Str255 | None = None
    desired_salary_min: SalaryInt | None = None
    desired_salary_currency: CurrencyCode | None = None
    desired_country: Str100 | None = None
    desired_city: Str100 | None = None
    desired_work_format: WorkFormat | None = None
    summary: str | None = None
    contacts: ResumeContacts | None = None
    experience: list[ResumeExperienceCreate] | None = None
    education: list[ResumeEducationCreate] | None = None
    skills: list[ResumeSkillCreate] | None = None
    courses: list[ResumeCourseCreate] | None = None
    languages: list[ResumeLanguageCreate] | None = None

    @field_validator("languages")
    @classmethod
    def _unique_languages(
        cls, value: list[ResumeLanguageCreate] | None
    ) -> list[ResumeLanguageCreate] | None:
        _ensure_unique_languages(value)
        return value

    @model_validator(mode="after")
    def _reject_explicit_nulls(self) -> "ResumeUpdate":
        for name in _NON_NULLABLE_UPDATE_FIELDS:
            if name in self.model_fields_set and getattr(self, name) is None:
                msg = f"{name} must not be null"
                raise ValueError(msg)
        return self


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


class ResumeListItem(BaseModel):
    """Строка списка резюме пользователя (без секций)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    target_position: str | None
    is_primary: bool
    origin: ResumeOrigin
    score: float | None
    created_at: datetime
    updated_at: datetime


class ResumeListResponse(BaseModel):
    """Все резюме пользователя; без пагинации — их единицы."""

    items: list[ResumeListItem]
