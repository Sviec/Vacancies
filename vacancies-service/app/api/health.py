"""Health-check: доступность Postgres и Redis.

# TODO: допущение — при деградации отдаётся 503 с тем же телом HealthResponse,
# а не error-конверт раздела 6 ТЗ: /health сообщает состояние сервиса,
# а не ошибку обработки запроса.
"""

import asyncio
import time
from collections.abc import Awaitable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import text

from app import __version__
from app.config import Settings, get_settings
from app.db.redis import get_redis
from app.db.session import get_engine

router = APIRouter(tags=["system"])

SettingsDep = Annotated[Settings, Depends(get_settings)]


class CheckResult(BaseModel):
    """Результат одной проверки зависимости."""

    status: Literal["ok", "error"]
    latency_ms: float | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """Сводный статус сервиса."""

    status: Literal["ok", "degraded"]
    version: str
    checks: dict[str, CheckResult]


async def _timed_check(probe: Awaitable[None], timeout_seconds: float) -> CheckResult:
    started = time.perf_counter()
    try:
        await asyncio.wait_for(probe, timeout_seconds)
    except Exception as exc:
        # Только тип исключения: текст может содержать DSN с паролем.
        return CheckResult(status="error", error=type(exc).__name__)
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    return CheckResult(status="ok", latency_ms=latency_ms)


async def _ping_database() -> None:
    engine = get_engine()
    async with engine.connect() as connection:
        # Только SELECT 1: на этапе 1 миграций ещё нет, а /health обязан быть
        # зелёным на пустой базе.
        await connection.execute(text("SELECT 1"))


async def _ping_redis() -> None:
    await get_redis().ping()


async def check_database(settings: SettingsDep) -> CheckResult:
    """Проверить доступность Postgres."""
    return await _timed_check(_ping_database(), settings.health_check_timeout_seconds)


async def check_redis(settings: SettingsDep) -> CheckResult:
    """Проверить доступность Redis."""
    return await _timed_check(_ping_redis(), settings.health_check_timeout_seconds)


DatabaseCheckDep = Annotated[CheckResult, Depends(check_database)]
RedisCheckDep = Annotated[CheckResult, Depends(check_redis)]


@router.get("/health", response_model=HealthResponse)
async def health(
    response: Response,
    database: DatabaseCheckDep,
    redis: RedisCheckDep,
) -> HealthResponse:
    """Вернуть состояние сервиса и его зависимостей.

    Проверки подключены через `Depends`, чтобы тесты могли подменить их через
    `app.dependency_overrides` без реальных Postgres и Redis.
    """
    checks = {"database": database, "redis": redis}
    degraded = any(check.status != "ok" for check in checks.values())
    if degraded:
        response.status_code = 503
    return HealthResponse(
        status="degraded" if degraded else "ok",
        version=__version__,
        checks=checks,
    )
