"""Провайдеры `SourceType.API`.

Новый запрос к уже известному провайдеру — новая строка `sources` с тем же
`provider`, без веток по `text`, `area` или `professional_role`. Незнакомое имя
не обходится: для него нет класса.
"""

from collections.abc import Mapping
from typing import Any

from app.db.models import Source
from app.enums import SourceType
from app.parsers.base import BaseParser
from app.parsers.registry import get_parser_class
from app.utils.errors import SourceNotRunnableError

_PROVIDERS: dict[str, type[BaseParser]] = {}


def register_provider(name: str, cls: type[BaseParser]) -> None:
    """Зарегистрировать класс API-провайдера. Пустое имя — ошибка программы."""
    if not isinstance(name, str) or not name:
        msg = "provider name must be a non-empty string"
        raise ValueError(msg)
    _PROVIDERS[name] = cls


def require_api_provider(config: Mapping[str, Any]) -> type[BaseParser]:
    """Класс провайдера или `SourceNotRunnableError`.

    Имя — непустая строка `config["provider"]`. Иначе в `details["provider"]`
    попадает сама строка, а для не-строки и отсутствующего ключа — `None`.
    """
    if "provider" not in config:
        raise SourceNotRunnableError(details={"provider": None})
    raw = config["provider"]
    if not isinstance(raw, str):
        raise SourceNotRunnableError(details={"provider": None})
    cls = _PROVIDERS.get(raw) if raw else None
    if cls is None:
        raise SourceNotRunnableError(details={"provider": raw})
    return cls


def ensure_source_runnable(source: Source) -> type[BaseParser]:
    """Тип есть в реестре; для API ещё и зарегистрированный `provider`."""
    cls = get_parser_class(source.source_type)
    if source.source_type == SourceType.API:
        return require_api_provider(source.config)
    return cls
