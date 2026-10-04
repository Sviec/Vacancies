"""Точка входа RQ: один источник, один процесс после fork.

Engine создаётся здесь и закрывается в finally. В родителе воркера его не
поднимать: fork рвёт соединения asyncpg.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from uuid import UUID

import redis

from app.config import Settings, get_settings
from app.db.session import dispose_engine, get_sessionmaker, init_engine
from app.services.parsing import perform_run
from app.tasks.queue import lock_key, release_lock
from app.utils.logging import get_logger

logger = get_logger(__name__)


def run_source(source_id: str, lock_token: str | None = None) -> None:
    """Sync-обёртка RQ. `lock_token` передаёт ручной POST; планировщик приходит без него."""
    settings = get_settings()
    connection = redis.Redis.from_url(settings.redis_url)
    if lock_token is None:
        token_bytes = uuid.uuid4().hex.encode("ascii")
        acquired = connection.set(
            lock_key(source_id),
            token_bytes,
            nx=True,
            ex=settings.rq_default_timeout,
        )
        if not acquired:
            logger.info("parse_skipped_locked", source_id=source_id)
            connection.close()
            return
    else:
        token_bytes = lock_token.encode("ascii")
    try:
        asyncio.run(_execute(source_id, settings))
    finally:
        try:
            release_lock(connection, source_id, token_bytes)
        except Exception:
            logger.warning("parse_lock_release_failed", source_id=source_id)
        connection.close()


async def _execute(source_id: str, settings: Settings) -> None:
    init_engine(settings)
    try:
        session_factory = get_sessionmaker()
        async with session_factory() as session:
            await perform_run(
                session,
                UUID(source_id),
                settings,
                now=datetime.now(UTC),
            )
    finally:
        await dispose_engine()
