"""Интерфейс парсера источника.

Парсер отдаёт сырые dict и `RawVacancy`. Числа и `parse_quality` считает
нормализатор, LLM отсюда не вызывается.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from datetime import datetime
from typing import Any, ClassVar

from app.config import Settings
from app.enums import SourceType
from app.services.normalizer import RawVacancy


class BaseParser(ABC):
    """Обход одного источника: сеть в `fetch_raw`, поля — в `to_normalized`."""

    source_type: ClassVar[SourceType]

    def __init__(self, *, slug: str, config: Mapping[str, Any], settings: Settings) -> None:
        self.slug = slug
        self.config = config
        self.settings = settings

    @abstractmethod
    async def fetch_raw(self) -> list[dict[str, Any]]:
        """Сырые публикации без `parsed_at`: его проставляет оркестратор прогона."""

    @abstractmethod
    def to_normalized(self, raw: dict[str, Any]) -> RawVacancy:
        """Собрать вход нормализатора.

        # TODO: ТЗ 5.1 пишет NormalizedVacancy. Возвращаем RawVacancy.
        Дальше `normalize_vacancy` и `ingest_batch`. Slug и тип берутся из
        парсера, не из сырого dict.
        """


def json_payload(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Копия сырого dict для JSONB: без `parsed_at`, datetime — строкой ISO."""
    payload: dict[str, Any] = {}
    for key, value in raw.items():
        if key == "parsed_at":
            continue
        payload[key] = _json_value(value)
    return payload


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def raw_vacancy(parser: BaseParser, raw: Mapping[str, Any]) -> RawVacancy:
    """`RawVacancy` из dict прогона. Пустой title — пустая строка, компания без текста — None."""
    parsed_at = raw.get("parsed_at")
    if not isinstance(parsed_at, datetime):
        msg = "parsed_at must be a timezone-aware datetime"
        raise TypeError(msg)
    published = raw.get("published_at")
    published_at = published if isinstance(published, datetime) else None
    description = raw.get("description_raw")
    skills = _skills_hint(raw)
    return RawVacancy(
        external_id=str(raw.get("external_id") or ""),
        source=parser.slug,
        source_type=parser.source_type,
        title=_text(raw.get("title")) or "",
        description_raw=description if isinstance(description, str) else "",
        parsed_at=parsed_at,
        url=_text(raw.get("url")),
        company=_text(raw.get("company")),
        city=_text(raw.get("city")),
        salary_text=_text(raw.get("salary_text")),
        skills_hint=skills,
        published_at=published_at,
        raw_payload=json_payload(raw),
    )


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _skills_hint(raw: Mapping[str, Any]) -> tuple[str, ...] | None:
    """Нет ключа — источник список навыков не отдавал. Пустой список — отдал пустой."""
    if "skills_hint" not in raw:
        return None
    value = raw["skills_hint"]
    if value is None:
        return None
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, list | tuple):
        return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    return ()
