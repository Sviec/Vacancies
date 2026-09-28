"""Async-engine и фабрика сессий SQLAlchemy.

Lifecycle: модульный синглтон с явной инициализацией из `lifespan`, а не
хранение объектов в `app.state`. Причина — тот же engine нужен RQ-воркеру
(`app/tasks/worker.py`) и `scripts/seed.py` (этап 7), у которых нет объекта
FastAPI-приложения.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_engine(settings: Settings) -> AsyncEngine:
    """Создать engine и фабрику сессий. Повторный вызов возвращает существующий engine."""
    global _engine, _sessionmaker
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.db_echo,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=settings.db_pool_pre_ping,
        )
        _sessionmaker = async_sessionmaker(
            _engine,
            expire_on_commit=False,
            autoflush=False,
        )
    return _engine


def get_engine() -> AsyncEngine:
    """Вернуть инициализированный engine."""
    if _engine is None:
        raise RuntimeError(
            "Database engine is not initialized: call init_engine(settings) "
            "from the application lifespan or worker entrypoint first."
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Вернуть инициализированную фабрику сессий."""
    if _sessionmaker is None:
        raise RuntimeError(
            "Session factory is not initialized: call init_engine(settings) "
            "from the application lifespan or worker entrypoint first."
        )
    return _sessionmaker


async def dispose_engine() -> None:
    """Закрыть пул соединений и сбросить синглтоны."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI-зависимость: сессия на время обработки запроса.

    Коммит здесь не делается сознательно. Сервисы только делают `flush` и
    никогда не коммитят (как `ingest`): так они композируются в одну
    транзакцию (этап 10: «создать резюме + оценить»). Коммит делает эндпоинт
    как оркестратор — `await session.commit()` сразу после вызова сервиса,
    до сборки ответа. Коммит в exit-коде yield-зависимости мог бы выполниться
    уже после отправки ответа (поведение FastAPI менялось между версиями).
    """
    # TODO: граница транзакции — эндпоинт; сервисы только flush-ят.
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(get_session)]
