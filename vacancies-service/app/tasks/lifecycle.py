"""Точка входа RQ: суточное гашение канонов и перепроверка карточек hh.

Импорт модуля не создаёт `HHClient` и не открывает engine. `ParseRun` не пишется.
Коммит — здесь, после гашения и отдельно после перепроверки.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import redis
from redis.exceptions import RedisError

from app.config import Settings, get_settings
from app.db.session import dispose_engine, get_sessionmaker, init_engine
from app.services.vacancy_lifecycle import deactivate_stale_canons, recheck_saved_hh
from app.utils.logging import get_logger

logger = get_logger(__name__)

_CURSOR_PREFIX = "hh:recheck:"


def run_lifecycle() -> None:
    """Sync-обёртка RQ. Без аргументов. При выключенных парсерах сразу выходит."""
    settings = get_settings()
    if not settings.parsers_enabled:
        return
    cursors = _read_cursors(settings)
    updated = asyncio.run(_execute(settings, cursors))
    _write_cursors(settings, updated)


async def _execute(
    settings: Settings,
    cursors: dict[UUID, UUID | None],
) -> dict[UUID, UUID | None]:
    init_engine(settings)
    try:
        session_factory = get_sessionmaker()
        async with session_factory() as session:
            await deactivate_stale_canons(session, datetime.now(UTC))
            await session.commit()
            updated = await recheck_saved_hh(session, settings, cursors=cursors)
            await session.commit()
            return updated
    finally:
        await dispose_engine()


def _read_cursors(settings: Settings) -> dict[UUID, UUID | None]:
    """Курсоры `hh:recheck:{source_id}`. Ошибка Redis — пустой словарь, прогон жив."""
    try:
        connection = redis.Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
        )
    except (RedisError, OSError, ValueError):
        logger.exception("lifecycle_cursor_unavailable")
        return {}
    try:
        return _collect_cursors(connection)
    except (RedisError, OSError):
        logger.exception("lifecycle_cursor_unavailable")
        return {}
    finally:
        connection.close()


def _write_cursors(settings: Settings, cursors: dict[UUID, UUID | None]) -> None:
    """Записать курсор строкой UUID. `None` удаляет ключ. Ошибка Redis не роняет прогон."""
    try:
        connection = redis.Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
        )
    except (RedisError, OSError, ValueError):
        logger.exception("lifecycle_cursor_unavailable")
        return
    try:
        for source_id, cursor in cursors.items():
            key = f"{_CURSOR_PREFIX}{source_id}"
            if cursor is None:
                connection.delete(key)
            else:
                connection.set(key, str(cursor))
    except (RedisError, OSError):
        logger.exception("lifecycle_cursor_unavailable")
    finally:
        connection.close()


def _collect_cursors(connection: redis.Redis) -> dict[UUID, UUID | None]:
    found: dict[UUID, UUID | None] = {}
    prefix = _CURSOR_PREFIX.encode("ascii")
    for key in connection.scan_iter(match=f"{_CURSOR_PREFIX}*"):
        raw_key = key if isinstance(key, bytes) else str(key).encode("ascii")
        if not raw_key.startswith(prefix):
            continue
        source_id = _parse_uuid(raw_key[len(prefix) :])
        if source_id is None:
            continue
        found[source_id] = _parse_uuid(connection.get(key))
    return found


def _parse_uuid(value: object) -> UUID | None:
    if isinstance(value, bytes):
        try:
            text = value.decode("ascii")
        except UnicodeDecodeError:
            return None
    elif isinstance(value, str):
        text = value
    else:
        return None
    try:
        return UUID(text)
    except ValueError:
        return None
