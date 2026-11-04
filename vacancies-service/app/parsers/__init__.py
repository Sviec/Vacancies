"""Парсеры источников. Импорт пакета регистрирует HTML, Telegram и API hh."""

from app.parsers.hh_api import HHApiParser
from app.parsers.html_parser import HtmlParser
from app.parsers.registry import build_parser, get_parser_class, register, unregister
from app.parsers.telegram_parser import TelegramParser

__all__ = [
    "HHApiParser",
    "HtmlParser",
    "TelegramParser",
    "build_parser",
    "get_parser_class",
    "register",
    "unregister",
]
