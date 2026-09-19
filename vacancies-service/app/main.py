"""Точка входа FastAPI-приложения."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.api.errors import register_exception_handlers
from app.api.middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from app.api.v1.router import api_router
from app.config import get_settings
from app.db.redis import close_redis, init_redis
from app.db.session import dispose_engine, init_engine
from app.utils.logging import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:  # noqa: ARG001 — сигнатура FastAPI
    """Инициализировать и освободить внешние подключения.

    Соединения при старте сознательно не проверяются: сервис обязан
    подниматься при недоступном Postgres или Redis, а `/health` в этом случае
    вернёт `degraded`. Иначе `docker compose up` падал бы на гонке стартов.
    """
    settings = get_settings()
    configure_logging(settings)
    init_engine(settings)
    init_redis(settings)
    logger.info(
        "service_started",
        version=settings.app_version,
        environment=settings.environment,
        llm_mode=settings.llm_mode,
        profile_mode=settings.profile_mode,
    )
    try:
        yield
    finally:
        await close_redis()
        await dispose_engine()
        logger.info("service_stopped")


def create_app() -> FastAPI:
    """Собрать приложение. Фабрика нужна тестам для изолированных экземпляров."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
    )

    # TODO: allow_credentials=False — авторизации нет (п. 0.2 ТЗ), куки не
    # используются. Пересмотреть, когда появится auth.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(api_router)
    return app


app = create_app()
