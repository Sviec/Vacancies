"""Точка входа Alembic (этап 2 раздела 12 ТЗ).

DSN не хранится в `alembic.ini`: он приходит из `app/config.py`, то есть из
того же `DATABASE_URL`, который читает приложение. Второго места, где задана
база, в проекте нет.

Модуль не проходит через `mypy`: проверка запускается только на `app`.
`alembic.context` в рантайме — прокси-объект, собираемый `EnvironmentContext`,
и strict-режим на нём даёт исключительно шум. `ruff` (включая набор ANN) файл
проверяет полностью.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# Импорт ради побочного эффекта: объявление моделей регистрирует таблицы в
# Base.metadata. Без него autogenerate увидел бы пустые метаданные и предложил
# бы удалить всю схему.
import app.db.models  # noqa: F401
from app.config import get_settings
from app.db.base import Base

config = context.config

# Без проверки на None падает `alembic` с --raiseerr и при программном вызове
# из тестов: там config_file_name не задан.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """Вернуть DSN приложения."""
    return get_settings().database_url


def run_migrations_offline() -> None:
    """Сгенерировать SQL без подключения к базе (`alembic upgrade --sql`)."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Выполнить миграции на уже открытом синхронном соединении."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Обе сравнивающие опции обязаны быть включены и здесь, и в дрейф-тесте
        # (tests/integration/test_migration_drift.py): при разных наборах опций
        # тест и autogenerate дают разный дифф, и «чистый» тест перестаёт
        # что-либо доказывать.
        compare_type=True,
        compare_server_default=True,
        # Схема одна (public): включение обошлось бы в отражение системных схем
        # и в ложные диффы по ним.
        include_schemas=False,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Поднять async-движок и прогнать миграции через `run_sync`."""
    # `%` в пароле ConfigParser принял бы за начало интерполяции `%(...)s` и
    # уронил бы запуск на InterpolationSyntaxError, никак не связанной с БД.
    config.set_main_option("sqlalchemy.url", get_url().replace("%", "%%"))

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        # NullPool: процесс alembic одноразовый, пул соединений ему не нужен и
        # только задерживает выход после завершения миграции.
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Выполнить миграции с подключением к базе."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
