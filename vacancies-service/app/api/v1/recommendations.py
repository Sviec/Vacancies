"""Роутер рекомендаций вакансий под резюме (п. 5.6 ТЗ).

Подключён в `api_router` раньше `vacancies.router`, иначе `/vacancies/recommended`
перехватил бы маршрут `/vacancies/{vacancy_id}`.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUserDep
from app.db.session import SessionDep
from app.schemas.recommendations import (
    RecommendationsQuery,
    RecommendedVacancyItem,
    RecommendedVacancyListResponse,
)
from app.schemas.vacancies import VacancyCardRead
from app.services import recommendations

router = APIRouter(prefix="/vacancies", tags=["recommendations"])


# TODO: GET пишет в БД — пересчитанный кэш `vacancy_matches` коммитится здесь.
@router.get("/recommended", response_model=RecommendedVacancyListResponse)
async def get_recommended(
    query: Annotated[RecommendationsQuery, Query()],
    session: SessionDep,
    user_id: CurrentUserDep,
) -> RecommendedVacancyListResponse:
    result = await recommendations.get_recommendations(
        session, user_id, query, now=datetime.now(UTC)
    )
    await session.commit()
    items = [
        RecommendedVacancyItem.model_validate(
            {
                **VacancyCardRead.model_validate(item.vacancy).model_dump(),
                "user_actions": result.actions.get(item.vacancy.id, []),
                "score": item.result.score,
                "match_details": item.result.details,
            }
        )
        for item in result.items
    ]
    return RecommendedVacancyListResponse(resume_id=result.resume_id, items=items)
