"""Настройка structlog: единый JSON-поток в stdout для своих и stdlib-логгеров."""

import logging
import sys
from typing import Any

import structlog

from app.config import Settings

# Логгеры stdlib, которые перенаправляются в structlog-форматтер.
# uvicorn.access сюда не входит: access-лог пишет RequestContextMiddleware.
_STDLIB_LOGGERS = ("uvicorn", "uvicorn.error", "sqlalchemy.engine")

_configured = False


def configure_logging(settings: Settings) -> None:
    """Настроить structlog и stdlib-логирование. Повторный вызов — no-op."""
    global _configured
    if _configured:
        return

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer: Any = (
        structlog.processors.JSONRenderer()
        if settings.log_format == "json"
        else structlog.dev.ConsoleRenderer()
    )
    level = logging.getLevelNamesMapping()[settings.log_level]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )

    # Один handler на всё приложение: stdlib-записи проходят те же процессоры,
    # поэтому в stdout нет смеси форматов.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    for name in _STDLIB_LOGGERS:
        stdlib_logger = logging.getLogger(name)
        stdlib_logger.handlers = []
        stdlib_logger.propagate = True

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers = []
    access_logger.propagate = False

    _configured = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Вернуть именованный structlog-логгер."""
    logger: structlog.stdlib.BoundLogger = structlog.stdlib.get_logger(name)
    return logger
