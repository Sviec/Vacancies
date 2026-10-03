"""Генерация и tailor резюме через LLM-адаптер (п. 5.3 ТЗ).

Функции только flush-ят через `create_resume` / `update_resume` и не коммитят.
Ошибки адаптера не глотаются: эндпоинт отдаёт их как 502 до записи.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.llm import LLMAdapter
from app.db.models import (
    Resume,
    ResumeCourse,
    ResumeEducation,
    ResumeExperience,
    ResumeLanguage,
    ResumeSkill,
)
from app.enums import ResumeOrigin
from app.schemas.ai import ResumeDraft, ResumeGenerateRequest, ResumeTailorRequest
from app.schemas.resumes import ResumeCreate, ResumeUpdate
from app.services.resumes import create_resume, get_resume, update_resume
from app.services.vacancies import get_vacancy
from app.utils.errors import LLMResponseInvalidError


def _experience_payload(item: ResumeExperience) -> dict[str, Any]:
    return {
        "company": item.company,
        "position": item.position,
        "start_date": item.start_date,
        "end_date": item.end_date,
        "is_current": item.is_current,
        "description": item.description,
        "achievements": item.achievements,
    }


def _education_payload(item: ResumeEducation) -> dict[str, Any]:
    return {
        "institution": item.institution,
        "degree": item.degree,
        "field": item.field,
        "start_year": item.start_year,
        "end_year": item.end_year,
    }


def _skill_payload(item: ResumeSkill) -> dict[str, Any]:
    return {"skill": item.skill, "level": item.level}


def _course_payload(item: ResumeCourse) -> dict[str, Any]:
    return {
        "title": item.title,
        "provider": item.provider,
        "year": item.year,
        "certificate_url": item.certificate_url,
    }


def _language_payload(item: ResumeLanguage) -> dict[str, Any]:
    return {"language": item.language, "level": item.level}


def _draft_from_resume(resume: Resume) -> ResumeDraft:
    """Черновик для LLM без id секций: их нет в схеме ResumeDraft."""
    return ResumeDraft.model_validate(
        {
            "title": resume.title,
            "is_primary": resume.is_primary,
            "target_position": resume.target_position,
            "desired_salary_min": resume.desired_salary_min,
            "desired_salary_currency": resume.desired_salary_currency,
            "desired_country": resume.desired_country,
            "desired_city": resume.desired_city,
            "desired_work_format": resume.desired_work_format,
            "summary": resume.summary,
            "contacts": resume.contacts,
            "experience": [_experience_payload(item) for item in resume.experience],
            "education": [_education_payload(item) for item in resume.education],
            "skills": [_skill_payload(item) for item in resume.skills],
            "courses": [_course_payload(item) for item in resume.courses],
            "languages": [_language_payload(item) for item in resume.languages],
        }
    )


def _invalid_draft(reason: str) -> LLMResponseInvalidError:
    return LLMResponseInvalidError(details={"reason": reason})


def _create_from_draft(draft: ResumeDraft) -> ResumeCreate:
    # TODO: черновик, не влезший в ResumeCreate, — 502 LLM_RESPONSE_INVALID.
    try:
        return ResumeCreate.model_validate(draft.model_dump())
    except ValidationError:
        raise _invalid_draft("draft_does_not_match_resume_create") from None


def _update_from_draft(draft: ResumeDraft) -> ResumeUpdate:
    # TODO: tailor не меняет is_primary и origin. Mock переписывает только summary.
    # Черновик, не влезший в ResumeUpdate, — тот же 502, что и у ResumeCreate.
    try:
        return ResumeUpdate.model_validate(draft.model_dump(exclude={"is_primary"}))
    except ValidationError:
        raise _invalid_draft("draft_does_not_match_resume_update") from None


async def generate_saved_resume(
    session: AsyncSession,
    user_id: UUID,
    body: ResumeGenerateRequest,
    *,
    llm: LLMAdapter,
) -> Resume:
    """Сохранить черновик LLM. Ошибка адаптера возникает до записи в БД."""
    draft = await llm.generate_resume(body)
    data = _create_from_draft(draft)
    # TODO: первое сгенерированное резюме становится основным по правилу create_resume.
    return await create_resume(
        session,
        user_id,
        data,
        origin=ResumeOrigin.GENERATED,
        llm=llm,
    )


async def tailor_saved_resume(
    session: AsyncSession,
    user_id: UUID,
    resume_id: UUID,
    body: ResumeTailorRequest,
    *,
    llm: LLMAdapter,
) -> Resume:
    """Подстроить сохранённое резюме под вакансию. Ошибка адаптера — до записи."""
    resume = await get_resume(session, user_id, resume_id)
    # TODO: вакансии общие — 404 только если id нет; resume_id в get_vacancy не передаём.
    vacancy, _actions, _match = await get_vacancy(
        session,
        user_id,
        body.vacancy_id,
        now=datetime.now(UTC),
    )
    tailored = await llm.tailor_resume(
        _draft_from_resume(resume),
        vacancy.title,
        list(vacancy.skills),
    )
    return await update_resume(
        session,
        user_id,
        resume_id,
        _update_from_draft(tailored),
        llm=llm,
    )
