"""CRUD резюме пользователя (п. 5.2 ТЗ).

Все функции принимают `user_id` явно и никогда не коммитят: границу
транзакции задаёт эндпоинт. Каждая изменяющая функция заканчивается `flush`
и перечитыванием резюме: `updated_at` обновляется через `onupdate=func.now()`
и после flush становится expired, а ленивая догрузка в async даёт
MissingGreenlet.
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    Resume,
    ResumeCourse,
    ResumeEducation,
    ResumeExperience,
    ResumeLanguage,
    ResumeSkill,
    VacancyMatch,
)
from app.enums import ResumeOrigin
from app.schemas.resumes import (
    ResumeCourseCreate,
    ResumeCreate,
    ResumeEducationCreate,
    ResumeExperienceCreate,
    ResumeLanguageCreate,
    ResumeSkillCreate,
    ResumeUpdate,
)
from app.services import resume_scoring
from app.services.normalizer import normalize_skills
from app.utils.errors import ConflictError, NotFoundError
from app.utils.skills_dict import SkillsDictionary

TITLE_MAX_LENGTH = 255
DUPLICATE_SUFFIX = " (копия)"

_SECTIONS = ("experience", "education", "skills", "courses", "languages")

# Поля, изменение которых не влияет на оценку резюме и матчинг.
_NON_DERIVED_FIELDS = frozenset({"title", "is_primary"})

_SCALAR_FIELDS = (
    "title",
    "target_position",
    "desired_salary_min",
    "desired_salary_currency",
    "desired_country",
    "desired_city",
    "desired_work_format",
    "summary",
)

_EXPERIENCE_FIELDS = (
    "company",
    "position",
    "start_date",
    "end_date",
    "is_current",
    "description",
    "achievements",
)
_EDUCATION_FIELDS = ("institution", "degree", "field", "start_year", "end_year")
_COURSE_FIELDS = ("title", "provider", "year", "certificate_url")
_LANGUAGE_FIELDS = ("language", "level")


def _not_found(resume_id: UUID) -> NotFoundError:
    # TODO: чужое резюме неотличимо от несуществующего — 404, а не 403,
    # чтобы не раскрывать существование чужих id.
    return NotFoundError(details={"resource": "resume", "id": str(resume_id)})


def prepare_skills(
    items: Sequence[ResumeSkillCreate], dictionary: SkillsDictionary | None = None
) -> list[tuple[str, int | None]]:
    """Привести навыки к канону, сохранив порядок первого появления.

    Пустые после нормализации навыки выбрасываются; уровень схлопнутого
    навыка — первый ненулевой в порядке входа.
    """
    # TODO: дубликаты канона (`js` и `javascript`) схлопываются молча, без ошибки.
    levels: dict[str, int | None] = {}
    for item in items:
        canon = normalize_skills([item.skill], dictionary)
        if not canon:
            continue
        # Переприсваивание существующего ключа не меняет порядок в dict.
        if levels.get(canon[0]) is None:
            levels[canon[0]] = item.level
    return list(levels.items())


def _experience(items: Sequence[ResumeExperienceCreate]) -> list[ResumeExperience]:
    return [ResumeExperience(**item.model_dump()) for item in items]


def _education(items: Sequence[ResumeEducationCreate]) -> list[ResumeEducation]:
    return [ResumeEducation(**item.model_dump()) for item in items]


def _skills(items: Sequence[ResumeSkillCreate]) -> list[ResumeSkill]:
    return [ResumeSkill(skill=skill, level=level) for skill, level in prepare_skills(items)]


def _courses(items: Sequence[ResumeCourseCreate]) -> list[ResumeCourse]:
    return [ResumeCourse(**item.model_dump()) for item in items]


def _languages(items: Sequence[ResumeLanguageCreate]) -> list[ResumeLanguage]:
    return [ResumeLanguage(**item.model_dump()) for item in items]


def _build_section(data: ResumeCreate | ResumeUpdate, name: str) -> list[Any]:
    """ORM-объекты секции `name` из входной схемы (секция обязана быть задана)."""
    items = getattr(data, name)
    if name == "experience":
        return _experience(items)
    if name == "education":
        return _education(items)
    if name == "skills":
        return _skills(items)
    if name == "courses":
        return _courses(items)
    return _languages(items)


def _copy(source: Any, model: type[Any], fields: Sequence[str]) -> Any:
    return model(**{name: getattr(source, name) for name in fields})


async def _load_resume(session: AsyncSession, user_id: UUID, resume_id: UUID) -> Resume | None:
    stmt = (
        select(Resume)
        .options(
            selectinload(Resume.experience),
            selectinload(Resume.education),
            selectinload(Resume.skills),
            selectinload(Resume.courses),
            selectinload(Resume.languages),
        )
        .where(Resume.id == resume_id, Resume.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _reload(session: AsyncSession, user_id: UUID, resume_id: UUID) -> Resume:
    await session.flush()
    resume = await _load_resume(session, user_id, resume_id)
    if resume is None:
        raise _not_found(resume_id)
    return resume


async def _has_primary(session: AsyncSession, user_id: UUID) -> bool:
    stmt = select(Resume.id).where(Resume.user_id == user_id, Resume.is_primary.is_(True))
    return (await session.execute(stmt.limit(1))).first() is not None


async def _set_primary(session: AsyncSession, user_id: UUID, resume: Resume) -> None:
    """Сделать резюме основным — строго двумя операторами.

    Частичный UNIQUE `uq_resumes_primary_per_user` нельзя объявить DEFERRABLE,
    поэтому сначала снимается флаг с прежнего основного, затем ставится новому.
    Резюме уже должно быть записано flush-ем (иметь id).
    """
    # TODO: снятие флага не меняет `updated_at` соседнего резюме
    # (явный `updated_at=Resume.updated_at` глушит onupdate), чтобы оно
    # не всплывало наверх списка.
    await session.execute(
        update(Resume)
        .where(
            Resume.user_id == user_id,
            Resume.is_primary.is_(True),
            Resume.id != resume.id,
        )
        .values(is_primary=False, updated_at=Resume.updated_at)
        .execution_options(synchronize_session=False)
    )
    await session.flush()
    resume.is_primary = True


async def _promote_next_primary(session: AsyncSession, user_id: UUID) -> None:
    # TODO: при удалении основного основным становится резюме с максимальным
    # `updated_at` (затем `created_at DESC`, `id`); его `updated_at` не меняется.
    stmt = (
        select(Resume.id)
        .where(Resume.user_id == user_id)
        .order_by(Resume.updated_at.desc(), Resume.created_at.desc(), Resume.id)
        .limit(1)
    )
    next_id = (await session.execute(stmt)).scalar_one_or_none()
    if next_id is None:
        return
    await session.execute(
        update(Resume)
        .where(Resume.id == next_id)
        .values(is_primary=True, updated_at=Resume.updated_at)
        .execution_options(synchronize_session=False)
    )


async def _invalidate_derived(session: AsyncSession, resume: Resume, *, today: date) -> None:
    """Пересчитать оценку и сбросить кэш матчинга после содержательного изменения."""
    # TODO: оценка пересчитывается синхронно (решение пользователя), матчи
    # удаляются и перестраиваются лениво при следующем GET /vacancies/recommended.
    await session.execute(delete(VacancyMatch).where(VacancyMatch.resume_id == resume.id))
    await resume_scoring.rescore(session, resume, today=today)


def _today(today: date | None) -> date:
    return today if today is not None else datetime.now(UTC).date()


async def list_resumes(session: AsyncSession, user_id: UUID) -> list[Resume]:
    """Все резюме пользователя: основное первым, затем свежие."""
    stmt = (
        select(Resume)
        .where(Resume.user_id == user_id)
        .order_by(
            Resume.is_primary.desc(),
            Resume.updated_at.desc(),
            Resume.created_at.desc(),
            Resume.id,
        )
        .execution_options(populate_existing=True)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_resume(session: AsyncSession, user_id: UUID, resume_id: UUID) -> Resume:
    """Резюме пользователя со всеми секциями; чужое или отсутствующее — 404."""
    resume = await _load_resume(session, user_id, resume_id)
    if resume is None:
        raise _not_found(resume_id)
    return resume


def build_resume(
    user_id: UUID, data: ResumeCreate, origin: ResumeOrigin = ResumeOrigin.MANUAL
) -> Resume:
    """Transient ORM-резюме с секциями, без сессии; `is_primary` решает вызывающий."""
    resume = Resume(
        user_id=user_id,
        origin=origin,
        is_primary=False,
        contacts=data.contacts.model_dump(),
        **{name: getattr(data, name) for name in _SCALAR_FIELDS},
    )
    for name in _SECTIONS:
        getattr(resume, name).extend(_build_section(data, name))
    return resume


async def create_resume(
    session: AsyncSession,
    user_id: UUID,
    data: ResumeCreate,
    *,
    origin: ResumeOrigin = ResumeOrigin.MANUAL,
    today: date | None = None,
) -> Resume:
    """Создать резюме с секциями и сразу оценить его.

    Инвариант: если у пользователя есть резюме, ровно одно из них основное.
    """
    resume = build_resume(user_id, data, origin)

    # TODO: первое резюме пользователя всегда основное, независимо от тела.
    had_primary = await _has_primary(session, user_id)
    resume.is_primary = not had_primary
    session.add(resume)
    await session.flush()
    if had_primary and data.is_primary:
        await _set_primary(session, user_id, resume)
    loaded = await _reload(session, user_id, resume.id)
    await resume_scoring.rescore(session, loaded, today=_today(today))
    return loaded


async def update_resume(
    session: AsyncSession,
    user_id: UUID,
    resume_id: UUID,
    data: ResumeUpdate,
    *,
    today: date | None = None,
) -> Resume:
    """Частичное обновление; секции из тела заменяются целиком."""
    resume = await get_resume(session, user_id, resume_id)
    payload = data.model_dump(exclude_unset=True)

    for name in _SCALAR_FIELDS:
        if name in payload:
            setattr(resume, name, payload[name])
    if "contacts" in payload:
        # Новый dict: изменения JSONB на месте ORM не отслеживает.
        resume.contacts = dict(payload["contacts"])

    # TODO: PATCH секции заменяет список целиком; пустой список очищает секцию.
    for name in _SECTIONS:
        if name not in payload:
            continue
        collection = getattr(resume, name)
        collection.clear()
        # Без промежуточного flush единица работы выполнит INSERT раньше
        # DELETE, и замена элемента с тем же ключом нарушит UNIQUE.
        await session.flush()
        collection.extend(_build_section(data, name))

    if "is_primary" in payload:
        if payload["is_primary"]:
            if not resume.is_primary:
                await _set_primary(session, user_id, resume)
        elif resume.is_primary:
            # TODO: снять флаг с основного нельзя — только назначить другое.
            raise ConflictError(
                "Cannot unset primary resume; mark another resume as primary instead",
                details={"field": "is_primary"},
            )

    # TODO: любое изменение, кроме `title` и `is_primary`, удаляет
    # vacancy_matches и пересчитывает score / score_details.
    if set(payload) - _NON_DERIVED_FIELDS:
        await _invalidate_derived(session, resume, today=_today(today))

    return await _reload(session, user_id, resume_id)


async def delete_resume(session: AsyncSession, user_id: UUID, resume_id: UUID) -> None:
    """Удалить резюме; vacancy_matches удаляются FK CASCADE."""
    resume = await get_resume(session, user_id, resume_id)
    was_primary = resume.is_primary
    await session.delete(resume)
    await session.flush()
    if was_primary:
        await _promote_next_primary(session, user_id)
        await session.flush()


async def duplicate_resume(session: AsyncSession, user_id: UUID, resume_id: UUID) -> Resume:
    """Копия резюме со всеми секциями; не основная, матчи не копируются."""
    src = await get_resume(session, user_id, resume_id)
    # TODO: копия получает суффикс « (копия)», не основная, `score` копируется,
    # vacancy_matches (кэш) — нет.
    copy = Resume(
        user_id=user_id,
        origin=ResumeOrigin.DUPLICATED,
        is_primary=False,
        contacts=dict(src.contacts),
        score=src.score,
        score_details=dict(src.score_details),
        **{name: getattr(src, name) for name in _SCALAR_FIELDS if name != "title"},
    )
    copy.title = f"{src.title}{DUPLICATE_SUFFIX}"[:TITLE_MAX_LENGTH]
    copy.experience.extend(_copy(e, ResumeExperience, _EXPERIENCE_FIELDS) for e in src.experience)
    copy.education.extend(_copy(e, ResumeEducation, _EDUCATION_FIELDS) for e in src.education)
    copy.skills.extend(ResumeSkill(skill=s.skill, level=s.level) for s in src.skills)
    copy.courses.extend(_copy(c, ResumeCourse, _COURSE_FIELDS) for c in src.courses)
    copy.languages.extend(_copy(lang, ResumeLanguage, _LANGUAGE_FIELDS) for lang in src.languages)
    session.add(copy)
    await session.flush()
    return await _reload(session, user_id, copy.id)
