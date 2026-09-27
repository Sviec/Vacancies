"""Схема в миграциях совпадает с моделями SQLAlchemy.

Главная защита от дрейфа: без неё расхождение между `app/db/models.py` и
`migrations/versions/` обнаружится только на этапе 7, когда сид упадёт на
несуществующей колонке. Ручная команда `alembic revision --autogenerate` даёт то
же самое, но её никто не выполнит перед коммитом.
"""

from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.db.base import Base

pytestmark = pytest.mark.integration


def _exclude_alembic_version(
    _object: Any,
    name: str | None,
    type_: str,
    *_args: Any,
    **_kwargs: Any,
) -> bool:
    """Исключить служебную таблицу Alembic из сравнения.

    `alembic_version` создаёт сам Alembic, в `Base.metadata` её нет, и без этого
    фильтра дифф никогда не будет пустым — тест сломался бы, ничего не доказав.
    """
    return not (type_ == "table" and name == "alembic_version")


def _collect_diffs(sync_connection: Connection) -> list[Any]:
    """Сравнить фактическую схему базы с метаданными моделей."""
    migration_context = MigrationContext.configure(
        sync_connection,
        opts={
            # Тот же набор опций, что в `migrations/env.py`: при разных наборах
            # тест и autogenerate дают разный дифф, и «зелёный» тест перестаёт
            # что-либо гарантировать.
            "compare_type": True,
            "compare_server_default": True,
            "include_object": _exclude_alembic_version,
        },
    )
    return list(compare_metadata(migration_context, Base.metadata))


async def test_migrations_match_models(migrated_test_database: str) -> None:
    """После `alembic upgrade head` расхождений с моделями быть не должно."""
    engine = create_async_engine(migrated_test_database, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            diffs = await connection.run_sync(_collect_diffs)
    finally:
        await engine.dispose()

    assert diffs == [], f"Схема миграций расходится с моделями: {diffs}"


async def test_all_model_tables_exist(migrated_test_database: str) -> None:
    """Все 12 таблиц моделей физически созданы миграцией."""
    engine = create_async_engine(migrated_test_database, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            actual = await connection.run_sync(
                lambda sync_connection: set(
                    sync_connection.dialect.get_table_names(sync_connection)
                )
            )
    finally:
        await engine.dispose()

    missing = set(Base.metadata.tables) - actual
    assert not missing, f"Миграция не создала таблицы: {sorted(missing)}"
