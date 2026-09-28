"""Фабрики тестовых данных: вакансии поверх настоящего нормализатора, резюме."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import SourceType
from app.schemas.normalized import NormalizedVacancy
from app.services.ingest import ingest_batch
from app.services.normalizer import RawVacancy, normalize_vacancy

PARSED_AT = datetime(2026, 9, 1, 12, tzinfo=UTC)

_DEFAULTS: dict[str, Any] = {
    "external_id": "100",
    "source": "tg_python_jobs",
    "source_type": SourceType.TELEGRAM,
    "title": "Senior Python Developer",
    "company": "Яндекс",
    "city": "Москва",
    "description_raw": (
        "Ищем Python-разработчика в команду поиска.\n"
        "Стек: FastAPI, PostgreSQL, Docker.\n"
        "Удалёнка, полная занятость."
    ),
    "parsed_at": PARSED_AT,
    "url": "https://t.me/python_jobs/100",
}


def make_raw(**overrides: Any) -> RawVacancy:
    """Сырая публикация с разумными значениями по умолчанию."""
    return RawVacancy(**{**_DEFAULTS, **overrides})


def make_normalized(**overrides: Any) -> NormalizedVacancy:
    """`NormalizedVacancy`, собранная `normalize_vacancy` из `make_raw`."""
    return normalize_vacancy(make_raw(**overrides))


async def ingest_raws(session: AsyncSession, *raws: RawVacancy) -> list[uuid.UUID]:
    """Записать публикации через ingest и вернуть `vacancy_id` по порядку."""
    result = await ingest_batch(session, [normalize_vacancy(raw) for raw in raws])
    assert result.errors == ()
    await session.flush()
    return [item.vacancy_id for item in result.results]


def make_resume_payload(**overrides: Any) -> dict[str, Any]:
    """Валидное тело `POST /resumes` со всеми секциями (даты в прошлом)."""
    payload: dict[str, Any] = {
        "title": "Backend-разработчик",
        "is_primary": False,
        "target_position": "Senior Python Developer",
        "desired_salary_min": 250_000,
        "desired_salary_currency": "RUB",
        "desired_country": "Россия",
        "desired_city": "Москва",
        "desired_work_format": "remote",
        "summary": "Пишу бэкенд на Python восемь лет.",
        "contacts": {"email": "dev@example.com", "telegram": "@dev"},
        "experience": [
            {
                "company": "Яндекс",
                "position": "Python Developer",
                "start_date": "2019-03-01",
                "end_date": "2022-06-30",
                "description": "Сервисы поиска",
            },
            {
                "company": "Ozon",
                "position": "Senior Python Developer",
                "start_date": "2022-07-01",
                "is_current": True,
            },
        ],
        "education": [
            {"institution": "МГУ", "degree": "Бакалавр", "start_year": 2012, "end_year": 2016},
        ],
        "skills": [
            {"skill": "Python", "level": 5},
            {"skill": "js", "level": None},
            {"skill": "JavaScript", "level": 3},
            {"skill": "Docker", "level": 4},
        ],
        "courses": [{"title": "Kubernetes для разработчиков", "provider": "Slurm", "year": 2023}],
        "languages": [
            {"language": "English", "level": "B2"},
            {"language": "Русский", "level": "native"},
        ],
    }
    payload.update(overrides)
    return payload
