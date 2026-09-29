"""Схемы рекомендаций вакансий под резюме (п. 5.6 ТЗ)."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.scoring import MatchDetails
from app.schemas.vacancies import VacancyCardRead

MAX_RECOMMENDATIONS = 200


class RecommendationsQuery(BaseModel):
    """Параметры GET /vacancies/recommended. Без пагинации."""

    model_config = ConfigDict(extra="forbid")

    # Без `resume_id` берётся основное резюме пользователя.
    resume_id: UUID | None = None
    exclude_hidden: bool = True
    # TODO: рекомендации без пагинации; `limit` по умолчанию 50, максимум 200.
    limit: int = Field(50, ge=1, le=MAX_RECOMMENDATIONS)


class RecommendedVacancyItem(VacancyCardRead):
    """Плоская карточка вакансии + score и match_details (не вложенный {vacancy: ...})."""

    score: float = Field(ge=0, le=100)
    match_details: MatchDetails


class RecommendedVacancyListResponse(BaseModel):
    """Список рекомендаций без page / page_size."""

    model_config = ConfigDict(extra="forbid")

    # `null`, если у пользователя нет ни одного резюме.
    resume_id: UUID | None
    items: list[RecommendedVacancyItem]
