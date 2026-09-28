"""Фикстуры интеграционных тестов: отдельная база, созданная с нуля.

Основной набор тестов (этап 1) полностью офлайновый и работает через
`ASGITransport` + `dependency_overrides`. Здесь всё наоборот: нужна настоящая
база, и именно **чистая** — дрейф-тест сравнивает схему после `alembic upgrade
head` с `Base.metadata`, поэтому любые остатки от предыдущих прогонов сделали бы
результат недоказательным.

Тесты, пишущие в базу (ingest этапа 4), получают `db_session`: сессию поверх
внешней транзакции соединения, которая откатывается после теста. Сессия
работает в режиме `create_savepoint`, поэтому собственные `commit` и
`begin_nested` кода под тестом не выходят за пределы этой транзакции, а
следующий тест видит пустые таблицы. Дрейф-тест фикстуру не использует.

API-тесты этапа 5 ходят в приложение через `api_client`: `get_session`
подменён на тот же `db_session`.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import get_current_user_id
from app.config import get_settings
from app.db.session import get_session
from app.main import create_app

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


@pytest.fixture
async def db_session(migrated_test_database: str) -> AsyncIterator[AsyncSession]:
    """Сессия внутри транзакции, откатываемой после теста."""
    engine = create_async_engine(migrated_test_database, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            session = AsyncSession(
                bind=connection,
                join_transaction_mode="create_savepoint",
                expire_on_commit=False,
                autoflush=False,
            )
            try:
                yield session
            finally:
                await session.close()
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.fixture
def app_for_db(db_session: AsyncSession) -> Iterator[FastAPI]:
    """Приложение, чьи эндпоинты работают в транзакции `db_session`.

    Lifespan не запускается, engine приложения не создаётся. Коммит эндпоинта
    в режиме `create_savepoint` только освобождает savepoint; внешняя
    транзакция откатывается после теста.
    """
    application = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        try:
            yield db_session
        except Exception:
            await db_session.rollback()
            raise

    application.dependency_overrides[get_session] = _session_override
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
async def api_client(app_for_db: FastAPI) -> AsyncIterator[AsyncClient]:
    """HTTP-клиент поверх приложения с тестовой БД."""
    async with AsyncClient(
        transport=ASGITransport(app=app_for_db), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
def other_user(app_for_db: FastAPI) -> uuid.UUID:
    """Подменить текущего пользователя на другого (тесты изоляции)."""
    user_id = uuid.uuid4()
    app_for_db.dependency_overrides[get_current_user_id] = lambda: user_id
    return user_id
