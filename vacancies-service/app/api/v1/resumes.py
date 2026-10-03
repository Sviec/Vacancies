"""Роутер резюме (п. 5.2 ТЗ). Эндпоинты тонкие: сервис → commit → схема ответа."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUserDep, LLMAdapterDep
from app.db.session import SessionDep
from app.schemas.ai import ResumeGenerateRequest, ResumeTailorRequest
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
from app.services.resume_ai import generate_saved_resume, tailor_saved_resume

router = APIRouter(prefix="/resumes", tags=["resumes"])


@router.get("", response_model=ResumeListResponse)
async def list_resumes(session: SessionDep, user_id: CurrentUserDep) -> ResumeListResponse:
    items = await service.list_resumes(session, user_id)
    return ResumeListResponse(items=[ResumeListItem.model_validate(item) for item in items])


@router.post("", response_model=ResumeRead, status_code=status.HTTP_201_CREATED)
async def create_resume(
    body: ResumeCreate,
    session: SessionDep,
    user_id: CurrentUserDep,
    llm: LLMAdapterDep,
) -> ResumeRead:
    resume = await service.create_resume(session, user_id, body, llm=llm)
    await session.commit()
    return ResumeRead.model_validate(resume)


@router.post("/generate", response_model=ResumeRead, status_code=status.HTTP_201_CREATED)
async def generate_resume(
    body: ResumeGenerateRequest,
    session: SessionDep,
    user_id: CurrentUserDep,
    llm: LLMAdapterDep,
) -> ResumeRead:
    """Черновик LLM сохраняется со статусом generated. Ошибки адаптера не ловятся."""
    # TODO: лимит raw_text 10 000 символов проверяет только фронтенд.
    resume = await generate_saved_resume(session, user_id, body, llm=llm)
    await session.commit()
    return ResumeRead.model_validate(resume)


@router.get("/{resume_id}", response_model=ResumeRead)
async def get_resume(resume_id: UUID, session: SessionDep, user_id: CurrentUserDep) -> ResumeRead:
    return ResumeRead.model_validate(await service.get_resume(session, user_id, resume_id))


@router.patch("/{resume_id}", response_model=ResumeRead)
async def update_resume(
    resume_id: UUID,
    body: ResumeUpdate,
    session: SessionDep,
    user_id: CurrentUserDep,
    llm: LLMAdapterDep,
) -> ResumeRead:
    resume = await service.update_resume(session, user_id, resume_id, body, llm=llm)
    await session.commit()
    return ResumeRead.model_validate(resume)


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(resume_id: UUID, session: SessionDep, user_id: CurrentUserDep) -> Response:
    await service.delete_resume(session, user_id, resume_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{resume_id}/score", response_model=ResumeScoreResponse)
async def score_resume(
    resume_id: UUID,
    session: SessionDep,
    user_id: CurrentUserDep,
    llm: LLMAdapterDep,
) -> ResumeScoreResponse:
    result = await resume_scoring.score_resume_by_id(
        session,
        user_id,
        resume_id,
        today=datetime.now(UTC).date(),
        llm=llm,
    )
    await session.commit()
    return ResumeScoreResponse(
        score=result.score,
        recommendations=result.recommendations,
        score_details=result.criteria,
    )


@router.post("/{resume_id}/tailor", response_model=ResumeRead)
async def tailor_resume(
    resume_id: UUID,
    body: ResumeTailorRequest,
    session: SessionDep,
    user_id: CurrentUserDep,
    llm: LLMAdapterDep,
) -> ResumeRead:
    """Подстроить резюме под вакансию. Ошибки адаптера не ловятся."""
    resume = await tailor_saved_resume(session, user_id, resume_id, body, llm=llm)
    await session.commit()
    return ResumeRead.model_validate(resume)


@router.post(
    "/{resume_id}/duplicate", response_model=ResumeRead, status_code=status.HTTP_201_CREATED
)
async def duplicate_resume(
    resume_id: UUID, session: SessionDep, user_id: CurrentUserDep
) -> ResumeRead:
    resume = await service.duplicate_resume(session, user_id, resume_id)
    await session.commit()
    return ResumeRead.model_validate(resume)
