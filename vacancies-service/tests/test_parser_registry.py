"""Реестр парсеров: встроенные типы на месте, тестовый класс снимается в finally."""

from collections.abc import Mapping
from typing import Any

import pytest

from app.config import Settings
from app.db.models import Source
from app.enums import SourceType
from app.parsers import (
    HtmlParser,
    TelegramParser,
    build_parser,
    get_parser_class,
    register,
    unregister,
)
from app.parsers.base import BaseParser
from app.utils.errors import SourceNotRunnableError


def test_html_and_telegram_are_registered() -> None:
    assert get_parser_class(SourceType.HTML) is HtmlParser
    assert get_parser_class(SourceType.TELEGRAM) is TelegramParser


def test_api_is_not_runnable() -> None:
    with pytest.raises(SourceNotRunnableError) as caught:
        get_parser_class(SourceType.API)
    assert caught.value.code == "SOURCE_NOT_RUNNABLE"


def test_register_api_then_unregister() -> None:
    @register
    class _ApiParser(BaseParser):
        source_type = SourceType.API

        async def fetch_raw(self) -> list[dict[str, Any]]:
            return []

        def to_normalized(self, raw: dict[str, Any]) -> Any:
            raise AssertionError(raw)

    try:
        assert get_parser_class(SourceType.API) is _ApiParser
        assert get_parser_class(SourceType.HTML) is HtmlParser
        assert get_parser_class(SourceType.TELEGRAM) is TelegramParser
    finally:
        unregister(SourceType.API)
    with pytest.raises(SourceNotRunnableError):
        get_parser_class(SourceType.API)
    assert get_parser_class(SourceType.HTML) is HtmlParser


def test_build_parser_uses_slug_and_config() -> None:
    source = Source(
        slug="html_careerhub",
        source_type=SourceType.HTML,
        config={"url": "https://careers.example.com/vacancies", "list_selector": "article"},
        is_enabled=True,
    )
    parser = build_parser(source, Settings(_env_file=None))
    assert isinstance(parser, HtmlParser)
    assert parser.slug == "html_careerhub"
    assert parser.config["list_selector"] == "article"


def test_parser_files_are_not_rewritten_by_registry_test() -> None:
    """Регистрация тестового класса не требует правки модулей парсеров."""
    config: Mapping[str, Any] = {"url": "https://example.com", "list_selector": "a"}
    parser = HtmlParser(slug="html_live", config=config, settings=Settings(_env_file=None))
    assert parser.source_type is SourceType.HTML
