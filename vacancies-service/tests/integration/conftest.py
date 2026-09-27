"""Фикстуры интеграционных тестов: отдельная база, созданная с нуля.

Основной набор тестов (этап 1) полностью офлайновый и работает через
`ASGITransport` + `dependency_overrides`. Здесь всё наоборот: нужна настоящая
база, и именно **чистая** — дрейф-тест сравнивает схему после `alembic upgrade
head` с `Base.metadata`, поэтому любые остатки от предыдущих прогонов сделали бы
результат недоказательным.

Транзакционной фикстуры с rollback на каждый тест здесь нет: на этапе 2 нечего
проверять запросами. Её добавит этап 5 поверх этого же файла вместе с первыми
CRUD-эндпоинтами.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings

TEST_DB_NAME = "vacancies_test"
ADMIN_DB_NAME = "postgres"

SERVICE_ROOT = Path(__file__).resolve().parents[2]


def _replace_database(url: str, database: str) -> str:
    """Подменить имя базы в DSN, не разбирая остальные его части."""
    base, _, _ = url.rpartition("/")
    return f"{base}/{database}"


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """DSN тестовой базы, выведенный из рабочего `DATABASE_URL`."""
    return _replace_database(get_settings().database_url, TEST_DB_NAME)


@pytest.fixture(scope="session")
def alembic_config() -> Config:
    """Конфиг Alembic с абсолютным `script_location`.

    Абсолютный путь обязателен: в `alembic.ini` он относительный, и при запуске
    pytest из любого каталога, кроме корня сервиса, миграции не нашлись бы.
    """
    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_ROOT / "migrations"))
    return config


@pytest.fixture(scope="session")
async def _recreated_test_database(test_database_url: str) -> AsyncIterator[str]:
    """Пересоздать тестовую базу перед прогоном.

    Подключение идёт к служебной базе `postgres` в режиме AUTOCOMMIT: `CREATE
    DATABASE` и `DROP DATABASE` внутри транзакции PostgreSQL не выполняет.
    """
    admin_url = _replace_database(test_database_url, ADMIN_DB_NAME)
    engine = create_async_engine(admin_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            # Имя базы — константа модуля, не пользовательский ввод; параметром
            # его передать нельзя, DDL в PostgreSQL не принимает bind-параметры.
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}"'))
            await connection.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    finally:
        await engine.dispose()

    yield test_database_url


@pytest.fixture(scope="session")
def _alembic_env_pointed_at_test_db(test_database_url: str) -> Iterator[None]:
    """Заставить `migrations/env.py` смотреть на тестовую базу.

    `env.py` берёт DSN из `get_settings()`, а тот закэширован через `lru_cache`,
    поэтому недостаточно выставить переменную окружения — кэш нужно сбросить до
    и после подмены, иначе настройки протекут в остальные тесты сессии.
    """
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = test_database_url
    get_settings.cache_clear()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        get_settings.cache_clear()


@pytest.fixture(scope="session")
async def migrated_test_database(
    _recreated_test_database: str,
    _alembic_env_pointed_at_test_db: None,
    alembic_config: Config,
) -> str:
    """Применить все миграции к чистой тестовой базе и вернуть её DSN."""
    # `env.py` внутри вызывает `asyncio.run`, поэтому команду нельзя выполнять в
    # уже работающем событийном цикле — уносим в отдельный поток с его циклом.
    await asyncio.to_thread(command.upgrade, alembic_config, "head")
    return _recreated_test_database
