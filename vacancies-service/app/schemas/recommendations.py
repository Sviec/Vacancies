"""Схемы рекомендаций вакансий под резюме (п. 5.6 ТЗ)."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.scoring import MatchDetails
from app.schemas.vacancies import VacancyCardRead


class RecommendationsQuery(BaseModel):
    """Параметры GET /vacancies/recommended. Без пагинации."""

    model_config = ConfigDict(extra="forbid")

    resume_id: UUID


class RecommendedVacancyItem(VacancyCardRead):
    """Плоская карточка вакансии + score и match_details (не вложенный {vacancy: ...})."""

    score: float = Field(ge=0, le=100)
    match_details: MatchDetails


class RecommendedVacancyListResponse(BaseModel):
    """Список рекомендаций без page / page_size."""

    model_config = ConfigDict(extra="forbid")

    items: list[RecommendedVacancyItem]
