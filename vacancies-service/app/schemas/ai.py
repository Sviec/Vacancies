"""Схемы ИИ-функций: генерация и tailor резюме (п. 5.3 ТЗ)."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.enums import WorkFormat
from app.schemas.common import CurrencyCode
from app.schemas.resumes import (
    ResumeContacts,
    ResumeCourseCreate,
    ResumeEducationCreate,
    ResumeExperienceCreate,
    ResumeLanguageCreate,
    ResumeSkillCreate,
)


class ResumeGenerateRequest(BaseModel):
    """Тело POST /resumes/generate."""

    model_config = ConfigDict(extra="forbid")

    raw_text: str = Field(min_length=1)
    target_position: str | None = None


class ResumeTailorRequest(BaseModel):
    """Тело POST /resumes/{id}/tailor."""

    model_config = ConfigDict(extra="forbid")

    vacancy_id: UUID


class ResumeDraft(BaseModel):
    """Черновик резюме от LLM: секции ResumeCreate без user_id / id / score / origin.

    Строго JSON без markdown-обёртки. Вложенные Create переиспользуются.
    """

    model_config = ConfigDict(extra="forbid")

    title: str
    is_primary: bool = False
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
