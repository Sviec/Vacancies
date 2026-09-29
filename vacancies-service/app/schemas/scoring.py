"""Схемы оценки резюме и разбивки матчинга (п. 5.4, 5.6 ТЗ)."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class ScoreIssue(BaseModel):
    """Машиночитаемая проблема критерия: основа шаблонной (и будущей LLM) рекомендации."""

    model_config = ConfigDict(extra="forbid")

    code: str
    context: dict[str, str | int | bool] = Field(default_factory=dict)


class ScoreCriterionDetail(BaseModel):
    """Одна составляющая оценки резюме. Сумму весов 10.0 здесь не валидируем."""

    model_config = ConfigDict(extra="forbid")

    key: ScoreCriterionKey
    name: str
    weight: float = Field(gt=0)
    points: float = Field(ge=0)
    issues: list[ScoreIssue] = Field(default_factory=list)
    recommendation: str | None = None


class MarketSkillsInfo(BaseModel):
    """На каком срезе вакансий посчитаны частотные навыки рынка."""

    model_config = ConfigDict(extra="forbid")

    basis: Literal["target_position", "all_vacancies", "none"]
    sample_size: int = Field(ge=0)
    top_skills: list[str]


class ResumeScoreDetails(BaseModel):
    """Форма JSONB `resumes.score_details`."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    score: float = Field(ge=0, le=10)
    criteria: list[ScoreCriterionDetail]
    recommendations: list[str]
    market: MarketSkillsInfo

    @field_validator("criteria")
    @classmethod
    def _all_criteria_in_order(
        cls, value: list[ScoreCriterionDetail]
    ) -> list[ScoreCriterionDetail]:
        if [item.key for item in value] != list(ScoreCriterionKey):
            msg = "criteria must contain every ScoreCriterionKey exactly once, in enum order"
            raise ValueError(msg)
        return value


class ResumeScoreResponse(BaseModel):
    """Ответ POST /resumes/{id}/score."""

    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0, le=10)
    recommendations: list[str]
    score_details: list[ScoreCriterionDetail]


MatchContextValue = str | int | float | bool | None


class MatchSkillsBreakdown(BaseModel):
    """Разбивка по навыкам (до 45 баллов п. 5.6)."""

    model_config = ConfigDict(extra="forbid")

    matched: list[str]
    missing: list[str]
    points: float = Field(ge=0, le=45)
    max_points: float = 45
    reason: str
    context: dict[str, MatchContextValue] = Field(default_factory=dict)


class MatchCriterionBreakdown(BaseModel):
    """Разбивка по одному критерию матчинга (level / salary / location / freshness)."""

    model_config = ConfigDict(extra="forbid")

    points: float = Field(ge=0)
    max_points: float = Field(gt=0)
    reason: str
    context: dict[str, MatchContextValue] = Field(default_factory=dict)


class MatchDetails(BaseModel):
    """Разбивка score соответствия резюме и вакансии (заполняет `matching.py`)."""

    model_config = ConfigDict(extra="forbid")

    skills: MatchSkillsBreakdown
    level: MatchCriterionBreakdown
    salary: MatchCriterionBreakdown
    location: MatchCriterionBreakdown
    freshness: MatchCriterionBreakdown
