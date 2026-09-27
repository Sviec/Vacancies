"""Схемы оценки резюме и разбивки матчинга (п. 5.4, 5.6 ТЗ)."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ScoreCriterionKey(StrEnum):
    """Ключи критериев оценки резюме (п. 5.4 ТЗ)."""

    COMPLETENESS = "completeness"
    EXPERIENCE_QUALITY = "experience_quality"
    MEASURABLE_ACHIEVEMENTS = "measurable_achievements"
    SKILLS_RELEVANCE = "skills_relevance"
    CHRONOLOGY = "chronology"
    EDUCATION_COURSES = "education_courses"
    LANGUAGES = "languages"
    GOALS_SPECIFICITY = "goals_specificity"


class ScoreCriterionDetail(BaseModel):
    """Одна составляющая оценки резюме. Сумму весов 10.0 здесь не валидируем."""

    model_config = ConfigDict(extra="forbid")

    key: ScoreCriterionKey
    name: str
    weight: float = Field(gt=0)
    points: float = Field(ge=0)


class ResumeScoreResponse(BaseModel):
    """Ответ POST /resumes/{id}/score."""

    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0, le=10)
    recommendations: list[str]
    score_details: list[ScoreCriterionDetail]


class MatchSkillsBreakdown(BaseModel):
    """Разбивка по навыкам (до 45 баллов п. 5.6)."""

    model_config = ConfigDict(extra="forbid")

    matched: list[str]
    missing: list[str]
    points: float = Field(ge=0, le=45)
    max_points: float = 45


class MatchCriterionBreakdown(BaseModel):
    """Разбивка по одному критерию матчинга (level / salary / location / freshness)."""

    model_config = ConfigDict(extra="forbid")

    points: float = Field(ge=0)
    max_points: float = Field(gt=0)


class MatchDetails(BaseModel):
    """Разбивка score соответствия резюме и вакансии.

    Числа заполняет этап 6 (`matching.py`); схема только описывает форму.
    """

    model_config = ConfigDict(extra="forbid")

    skills: MatchSkillsBreakdown
    level: MatchCriterionBreakdown
    salary: MatchCriterionBreakdown
    location: MatchCriterionBreakdown
    freshness: MatchCriterionBreakdown
