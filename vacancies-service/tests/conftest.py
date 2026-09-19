"""Общие фикстуры тестов.

Почему тесты работают без Postgres и Redis:
`ASGITransport` не выполняет lifespan-события приложения, поэтому ни engine,
ни redis-клиент не создаются вовсе. А единственные два места, которые к ним
обращаются (`check_database` и `check_redis` из `/health`), подменены через
`app.dependency_overrides`. Набор полностью офлайновый.
Интеграционные тесты с реальной БД появятся на этапе 5.
"""

from collections.abc import AsyncIterator, Iterator

import pytest
from app.api.health import CheckResult, check_database, check_redis
from app.config import Settings
from app.main import create_app
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def _ok_check() -> CheckResult:
    return CheckResult(status="ok", latency_ms=1.0)


def _error_check() -> CheckResult:
    return CheckResult(status="error", error="ConnectionError")


@pytest.fixture
def settings() -> Settings:
    """Чистые дефолты конфига, без чтения локального .env."""
    return Settings(_env_file=None)


@pytest.fixture
def app() -> Iterator[FastAPI]:
    """Приложение со здоровыми заглушками проверок зависимостей."""
    application = create_app()
    application.dependency_overrides[check_database] = _ok_check
    application.dependency_overrides[check_redis] = _ok_check
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def degrade_redis(app: FastAPI) -> None:
    """Перевести проверку Redis в состояние error для сценария деградации."""
    app.dependency_overrides[check_redis] = _error_check


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """HTTP-клиент поверх ASGI-приложения, без сети."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as async_client:
        yield async_client
