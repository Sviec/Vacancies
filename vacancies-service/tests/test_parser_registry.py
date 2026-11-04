"""Реестр парсеров: встроенные типы на месте, тестовый класс снимается в finally."""

from collections.abc import Mapping
from typing import Any

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


def test_html_and_telegram_are_registered() -> None:
    assert get_parser_class(SourceType.HTML) is HtmlParser
    assert get_parser_class(SourceType.TELEGRAM) is TelegramParser


def test_api_parser_is_hh() -> None:
    from app.parsers.hh_api import HHApiParser

    assert get_parser_class(SourceType.API) is HHApiParser


def test_register_api_then_unregister() -> None:
    from app.parsers.hh_api import HHApiParser

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
        register(HHApiParser)
    assert get_parser_class(SourceType.API) is HHApiParser
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
