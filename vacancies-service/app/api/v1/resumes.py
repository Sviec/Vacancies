"""Роутер резюме (п. 5.2 ТЗ). Эндпоинты тонкие: сервис → commit → схема ответа."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUserDep
from app.db.session import SessionDep
from app.schemas.resumes import (
    ResumeCreate,
    ResumeListItem,
    ResumeListResponse,
    ResumeRead,
    ResumeUpdate,
)
from app.schemas.scoring import ResumeScoreResponse
from app.services import resume_scoring
from app.services import resumes as service

# Генерация и адаптация резюме (п. 5.3) добавляются на этапе 10.
router = APIRouter(prefix="/resumes", tags=["resumes"])


@router.get("", response_model=ResumeListResponse)
async def list_resumes(session: SessionDep, user_id: CurrentUserDep) -> ResumeListResponse:
    items = await service.list_resumes(session, user_id)
    return ResumeListResponse(items=[ResumeListItem.model_validate(item) for item in items])


@router.post("", response_model=ResumeRead, status_code=status.HTTP_201_CREATED)
async def create_resume(
    body: ResumeCreate, session: SessionDep, user_id: CurrentUserDep
) -> ResumeRead:
    resume = await service.create_resume(session, user_id, body)
    await session.commit()
    return ResumeRead.model_validate(resume)


@router.get("/{resume_id}", response_model=ResumeRead)
async def get_resume(resume_id: UUID, session: SessionDep, user_id: CurrentUserDep) -> ResumeRead:
    return ResumeRead.model_validate(await service.get_resume(session, user_id, resume_id))


@router.patch("/{resume_id}", response_model=ResumeRead)
async def update_resume(
    resume_id: UUID, body: ResumeUpdate, session: SessionDep, user_id: CurrentUserDep
) -> ResumeRead:
    resume = await service.update_resume(session, user_id, resume_id, body)
    await session.commit()
    return ResumeRead.model_validate(resume)


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(resume_id: UUID, session: SessionDep, user_id: CurrentUserDep) -> Response:
    await service.delete_resume(session, user_id, resume_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{resume_id}/score", response_model=ResumeScoreResponse)
async def score_resume(
    resume_id: UUID, session: SessionDep, user_id: CurrentUserDep
) -> ResumeScoreResponse:
    result = await resume_scoring.score_resume_by_id(
        session, user_id, resume_id, today=datetime.now(UTC).date()
    )
    await session.commit()
    return ResumeScoreResponse(
        score=result.score,
        recommendations=result.recommendations,
        score_details=result.criteria,
    )


@router.post(
    "/{resume_id}/duplicate", response_model=ResumeRead, status_code=status.HTTP_201_CREATED
)
async def duplicate_resume(
    resume_id: UUID, session: SessionDep, user_id: CurrentUserDep
) -> ResumeRead:
    resume = await service.duplicate_resume(session, user_id, resume_id)
    await session.commit()
    return ResumeRead.model_validate(resume)
