"""Реестр парсеров по `SourceType`.

# TODO: новый HTML-сайт — это строка `sources.config`. Новый тип источника —
# класс и `register`. Формулировка ТЗ «новый источник = новый класс» для сайтов
# не применяется (критерий приёмки 6).
"""

from typing import Any

from app.config import Settings
from app.db.models import Source
from app.enums import SourceType
from app.parsers.base import BaseParser
from app.utils.errors import SourceNotRunnableError

_REGISTRY: dict[SourceType, type[BaseParser]] = {}


def register(cls: type[BaseParser]) -> type[BaseParser]:
    """Зарегистрировать класс парсера на его `source_type`."""
    _REGISTRY[cls.source_type] = cls
    return cls


def unregister(source_type: SourceType) -> None:
    """Снять регистрацию. Нужно тестам, чтобы класс на `SourceType.API` не тёк."""
    _REGISTRY.pop(source_type, None)


def get_parser_class(source_type: SourceType) -> type[BaseParser]:
    """Класс парсера или `SourceNotRunnableError`, если тип не зарегистрирован."""
    cls = _REGISTRY.get(source_type)
    if cls is None:
        raise SourceNotRunnableError(details={"source_type": source_type.value})
    return cls


def build_parser(source: Source, settings: Settings) -> BaseParser:
    """Собрать парсер источника. Тип вне реестра — `SourceNotRunnableError`."""
    cls = get_parser_class(source.source_type)
    config: dict[str, Any] = dict(source.config)
    return cls(slug=source.slug, config=config, settings=settings)
