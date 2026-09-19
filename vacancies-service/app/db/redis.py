"""Подключение к Redis для API.

ВАЖНО: API работает через `redis.asyncio.Redis`, а RQ-воркер
(`app/tasks/worker.py`) — через синхронный `redis.Redis`, потому что RQ не
умеет async. Это два разных подключения; смешивать их нельзя — синхронный
клиент заблокирует event loop, а async-клиент не принимается RQ.
"""

from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis

from app.config import Settings

_redis: Redis | None = None


def init_redis(settings: Settings) -> Redis:
    """Создать async-клиент Redis. Повторный вызов возвращает существующий."""
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def get_redis() -> Redis:
    """Вернуть инициализированный async-клиент Redis."""
    if _redis is None:
        raise RuntimeError(
            "Redis client is not initialized: call init_redis(settings) "
            "from the application lifespan first."
        )
    return _redis


async def close_redis() -> None:
    """Закрыть соединение с Redis и сбросить синглтон."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
    _redis = None


RedisDep = Annotated[Redis, Depends(get_redis)]
