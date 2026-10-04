"""Синхронный Redis для RQ: блокировка источника и постановка ручного прогона.

# TODO: lock живёт до rq_default_timeout, если воркер умер. Отдельной уборки нет.
Клиент без decode_responses: значение lock — bytes, как его читает сравнение в Redis.
"""

import uuid

import redis
from redis import Redis
from rq import Queue

from app.config import Settings
from app.db.models import Source
from app.utils.errors import SourceAlreadyRunningError

_LOCK_PREFIX = "parse-active:"
_RELEASE_LOCK = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


def lock_key(source_id: str) -> str:
    return f"{_LOCK_PREFIX}{source_id}"


def release_lock(connection: Redis, source_id: str, token: bytes) -> None:
    """Снять ключ, только если значение совпало с token."""
    connection.eval(_RELEASE_LOCK, 1, lock_key(source_id), token)


def enqueue_manual_run(source: Source, settings: Settings, connection: Redis) -> str:
    """Поставить `run_source` и вернуть id задачи.

    Занятый lock — `SourceAlreadyRunningError`. Если enqueue упал, lock снимается.
    """
    token = uuid.uuid4().hex
    token_bytes = token.encode("ascii")
    acquired = connection.set(
        lock_key(str(source.id)),
        token_bytes,
        nx=True,
        ex=settings.rq_default_timeout,
    )
    if not acquired:
        raise SourceAlreadyRunningError(
            details={"source_id": str(source.id), "slug": source.slug},
        )
    try:
        # Импорт здесь: parse_source тянет queue за lock-хелперами.
        from app.tasks.parse_source import run_source

        queue = Queue(
            settings.rq_queue_name,
            connection=connection,
            default_timeout=settings.rq_default_timeout,
        )
        job = queue.enqueue(
            run_source,
            str(source.id),
            token,
            job_timeout=settings.rq_default_timeout,
        )
    except Exception:
        release_lock(connection, str(source.id), token_bytes)
        raise
    job_id = job.id
    if not isinstance(job_id, str) or not job_id:
        release_lock(connection, str(source.id), token_bytes)
        msg = "RQ did not return a job id"
        raise RuntimeError(msg)
    return job_id


def redis_connection(settings: Settings) -> Redis:
    """Sync-клиент того же URL, что у RQ. decode_responses не включаем."""
    return redis.Redis.from_url(settings.redis_url)
