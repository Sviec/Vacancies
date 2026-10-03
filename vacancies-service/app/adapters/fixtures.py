"""Константные фикстуры mock-адаптеров (раздел 9 ТЗ).

Ни часов, ни случайности, ни файлов: каждый вызов собирает новые модели
из одних и тех же литералов, чтобы вызывающий код не делил состояние.
"""

from datetime import date

from app.enums import EmploymentType, ExperienceLevel, LanguageLevel, WorkFormat
from app.schemas.adapters import ProfileSnapshot, VacancyEnrichment
from app.schemas.ai import ResumeDraft
from app.schemas.resumes import (
    ResumeContacts,
    ResumeEducationCreate,
    ResumeExperienceCreate,
    ResumeLanguageCreate,
    ResumeSkillCreate,
)

# TODO: mock не разбирает raw_text и description_raw; фикстуры — константы Python.

MOCK_FALLBACK_TITLE = "Data Scientist"
MOCK_FALLBACK_COMPANY = "Mock Company"
MOCK_SUMMARY = "Черновик резюме из mock-адаптера."
MOCK_CLEAN_DESCRIPTION = "Очищенное описание из mock-адаптера."
MOCK_COUNTRY = "Россия"
MOCK_CITY = "Москва"
MOCK_EXPERIENCE_DESCRIPTION = "Анализ данных и автоматизация отчётности."
MOCK_ACHIEVEMENT = "Сократил время отчёта на 30%."
# Фиксированная дата в прошлом: ResumeExperienceCreate отвергает start_date из будущего.
MOCK_EXPERIENCE_START = date(2022, 7, 1)


def mock_skills() -> list[ResumeSkillCreate]:
    """Навыки фикстуры: python 4, sql 3."""
    return [
        ResumeSkillCreate(skill="python", level=4),
        ResumeSkillCreate(skill="sql", level=3),
    ]


def mock_experience() -> list[ResumeExperienceCreate]:
    """Одна текущая позиция. end_date пустой, пока is_current."""
    return [
        ResumeExperienceCreate(
            company="Mock Lab",
            position="Data Scientist",
            start_date=MOCK_EXPERIENCE_START,
            end_date=None,
            is_current=True,
            description=MOCK_EXPERIENCE_DESCRIPTION,
            achievements=MOCK_ACHIEVEMENT,
        )
    ]


def mock_education() -> list[ResumeEducationCreate]:
    """Магистратура МГУ, 2016–2018."""
    return [
        ResumeEducationCreate(
            institution="МГУ",
            degree="магистр",
            field="прикладная математика",
            start_year=2016,
            end_year=2018,
        )
    ]


def mock_languages() -> list[ResumeLanguageCreate]:
    """English B2."""
    return [ResumeLanguageCreate(language="English", level=LanguageLevel.B2)]


def mock_contacts() -> ResumeContacts:
    """Почта и telegram демо-профиля."""
    return ResumeContacts(email="demo@example.com", telegram="@demo")


def mock_profile_snapshot() -> ProfileSnapshot:
    """Один и тот же снимок профиля на любой user_id."""
    return ProfileSnapshot(
        skills=mock_skills(),
        experience=mock_experience(),
        education=mock_education(),
        languages=mock_languages(),
        contacts=mock_contacts(),
        desired_country=MOCK_COUNTRY,
        desired_city=MOCK_CITY,
    )


def resolved_draft_title(target_position: str | None) -> str:
    """Заголовок черновика: непустой target_position после strip, иначе константа."""
    if target_position is not None:
        stripped = target_position.strip()
        if stripped:
            return stripped
    return MOCK_FALLBACK_TITLE


def mock_resume_draft(title: str) -> ResumeDraft:
    """Черновик с теми же секциями, что и снимок профиля."""
    return ResumeDraft(
        title=title,
        is_primary=False,
        target_position=title,
        desired_salary_min=200_000,
        desired_salary_currency="RUB",
        desired_country=MOCK_COUNTRY,
        desired_city=MOCK_CITY,
        desired_work_format=WorkFormat.REMOTE,
        summary=MOCK_SUMMARY,
        experience=mock_experience(),
        education=mock_education(),
        skills=mock_skills(),
        languages=mock_languages(),
    )


def mock_vacancy_enrichment(*, title: str, company: str) -> VacancyEnrichment:
    """Стабильное обогащение: меняются только title и company."""
    return VacancyEnrichment(
        title=title,
        company=company,
        description_clean=MOCK_CLEAN_DESCRIPTION,
        skills=["python", "sql"],
        city=MOCK_CITY,
        country=MOCK_COUNTRY,
        work_format=WorkFormat.REMOTE,
        experience_level=ExperienceLevel.MIDDLE,
        employment_type=EmploymentType.FULL_TIME,
        salary_min=200_000,
        salary_max=300_000,
        salary_currency="RUB",
    )
