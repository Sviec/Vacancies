"""Роутер вакансий (п. 5.5, 5.7 ТЗ). Эндпоинты тонкие: сервис → commit → схема.

Порядок объявления важен: `/filters/meta` — раньше `/{vacancy_id}`.
`/recommended` (этап 6) живёт в `recommendations.router`, который подключён
в `api_router` раньше этого роутера.
"""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CurrentUserDep
from app.db.session import SessionDep
from app.enums import UserAction
from app.schemas.vacancies import (
    VacancyActionRequest,
    VacancyCardRead,
    VacancyDetailRead,
    VacancyFiltersMeta,
    VacancyListItem,
    VacancyListQuery,
    VacancyListResponse,
    VacancyUserState,
)
from app.services import user_actions, vacancies

router = APIRouter(prefix="/vacancies", tags=["vacancies"])


# TODO: списочные query-параметры передаются повтором ключа
# (`work_format=remote&work_format=hybrid`), без синтаксиса `param[]`.
# TODO: GET с `resume_id` пишет в БД — пересчитанный кэш `vacancy_matches`
# коммитится здесь, как в `/recommended`.
@router.get("", response_model=VacancyListResponse)
async def list_vacancies(
    query: Annotated[VacancyListQuery, Query()],
    session: SessionDep,
    user_id: CurrentUserDep,
) -> VacancyListResponse:
    page = await vacancies.list_vacancies(session, user_id, query, now=datetime.now(UTC))
    if query.resume_id is not None:
        await session.commit()
    items = []
    for vacancy in page.items:
        match_result = page.matches.get(vacancy.id)
        items.append(
            VacancyListItem.model_validate(
                {
                    **VacancyCardRead.model_validate(vacancy).model_dump(),
                    "sources": page.sources.get(vacancy.id, []),
                    "user_actions": page.actions.get(vacancy.id, []),
                    "match_score": match_result.score if match_result is not None else None,
                    "match_details": match_result.details if match_result is not None else None,
                }
            )
        )
    return VacancyListResponse(
        items=items, total=page.total, page=query.page, page_size=query.page_size
    )


@router.get("/filters/meta", response_model=VacancyFiltersMeta)
async def get_filters_meta(session: SessionDep) -> VacancyFiltersMeta:
    return await vacancies.get_filters_meta(session)


@router.get("/{vacancy_id}", response_model=VacancyDetailRead)
async def get_vacancy(
    vacancy_id: UUID,
    session: SessionDep,
    user_id: CurrentUserDep,
    resume_id: UUID | None = None,
) -> VacancyDetailRead:
    vacancy, actions, match_result = await vacancies.get_vacancy(
        session, user_id, vacancy_id, resume_id=resume_id, now=datetime.now(UTC)
    )
    if resume_id is not None:
        await session.commit()
    return VacancyDetailRead.model_validate(vacancy).model_copy(
        update={
            "user_actions": actions,
            "match_score": match_result.score if match_result is not None else None,
            "match_details": match_result.details if match_result is not None else None,
        }
    )


# TODO: ответ на действие — 200 с полным множеством действий по вакансии.
@router.post("/{vacancy_id}/action", response_model=VacancyUserState)
async def add_action(
    vacancy_id: UUID,
    body: VacancyActionRequest,
    session: SessionDep,
    user_id: CurrentUserDep,
) -> VacancyUserState:
    actions = await user_actions.add_action(session, user_id, vacancy_id, body.action)
    await session.commit()
    return VacancyUserState(vacancy_id=vacancy_id, actions=actions)


@router.delete("/{vacancy_id}/action/{action}", response_model=VacancyUserState)
async def remove_action(
    vacancy_id: UUID,
    action: UserAction,
    session: SessionDep,
    user_id: CurrentUserDep,
) -> VacancyUserState:
    actions = await user_actions.remove_action(session, user_id, vacancy_id, action)
    await session.commit()
    return VacancyUserState(vacancy_id=vacancy_id, actions=actions)
