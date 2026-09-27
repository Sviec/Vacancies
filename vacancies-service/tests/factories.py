"""Фабрики тестовых вакансий поверх настоящего нормализатора."""

from datetime import UTC, datetime
from typing import Any

from app.enums import SourceType
from app.schemas.normalized import NormalizedVacancy
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
