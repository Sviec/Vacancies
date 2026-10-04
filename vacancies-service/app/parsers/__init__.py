"""Парсеры источников. Импорт пакета регистрирует HTML и Telegram.

`SourceType.API` намеренно не регистрируется: для него нет обхода.
"""

from app.parsers.html_parser import HtmlParser
from app.parsers.registry import build_parser, get_parser_class, register, unregister
from app.parsers.telegram_parser import TelegramParser

__all__ = [
    "HtmlParser",
    "TelegramParser",
    "build_parser",
    "get_parser_class",
    "register",
    "unregister",
]
