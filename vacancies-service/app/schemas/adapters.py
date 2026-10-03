"""Узкие DTO адаптеров LLM и profile (раздел 9 ТЗ).

Не схемы HTTP-эндпоинтов: их потребляют только адаптеры. Вложенные Create
резюме остаются с `extra="forbid"`, как в `resumes.py`.
"""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.enums import EmploymentType, ExperienceLevel, WorkFormat
from app.schemas.common import CurrencyCode, validate_salary_range
from app.schemas.resumes import (
    ResumeContacts,
    ResumeEducationCreate,
    ResumeExperienceCreate,
    ResumeLanguageCreate,
    ResumeSkillCreate,
)
from app.schemas.scoring import ScoreCriterionKey, ScoreIssue


class ProfileSnapshot(BaseModel):
    """Снимок профиля из profile-core для предзаполнения резюме.

    Лишние поля корня игнорируются: контракт внешнего сервиса шире нашего.
    """

    model_config = ConfigDict(extra="ignore")

    skills: list[ResumeSkillCreate]
    experience: list[ResumeExperienceCreate]
    education: list[ResumeEducationCreate]
    languages: list[ResumeLanguageCreate]
    contacts: ResumeContacts
    desired_country: str | None
    desired_city: str | None


class CriterionFailure(BaseModel):
    """Провал критерия скоринга: ключ и уже посчитанные issues.

    Порядок элементов задаёт порядок фраз `phrase_recommendations`.
    """

    model_config = ConfigDict(extra="forbid")

    key: ScoreCriterionKey
    issues: list[ScoreIssue]


class VacancyEnrichmentInput(BaseModel):
    """Вход обогащения вакансии. Не NormalizedVacancy: парсер отдаёт сырой текст."""

    model_config = ConfigDict(extra="forbid")

    title: str
    description_raw: str
    company: str | None = None


class VacancyEnrichment(BaseModel):
    """Поля, которые LLM смогла достать из сырого текста вакансии.

    Все поля опциональны: модель может не заполнить часть вилки или грейд.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    company: str | None = None
    description_clean: str | None = None
    skills: list[str] = Field(default_factory=list)
    city: str | None = None
    country: str | None = None
    work_format: WorkFormat | None = None
    experience_level: ExperienceLevel | None = None
    employment_type: EmploymentType | None = None
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    salary_currency: CurrencyCode | None = None

    @model_validator(mode="after")
    def _salary_bounds(self) -> "VacancyEnrichment":
        validate_salary_range(self.salary_min, self.salary_max)
        return self


class RecommendationPhrases(BaseModel):
    """Обёртка JSON для `phrase_recommendations`. Не часть Protocol.

    Наружу адаптер отдаёт `list[str]`, длина которого обязана совпасть
    с длиной входных провалов — это проверяет адаптер, не схема.
    """

    model_config = ConfigDict(extra="forbid")

    items: list[str]
