"""Настройки сервиса.

Все дефолты подобраны так, чтобы сервис поднимался и полностью работал в
mock-режиме, без внешних ключей и без доступа в сеть (п. 0.3 и раздел 11.2 ТЗ).

Веса скоринга резюме (раздел 5.4) и матчинга (раздел 5.6) сюда сознательно
НЕ вынесены: это константы в коде. Иначе воспроизводимость оценки
(критерий приёмки 5) стала бы зависеть от окружения.
"""

from functools import lru_cache
from typing import Annotated, Literal
from uuid import UUID

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация сервиса, читается из переменных окружения и `.env`."""

    # env_prefix не задаём: имена переменных используются как есть (DATABASE_URL и т.п.)
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Приложение ---
    app_name: str = "vacancies-service"
    app_version: str = "0.1.0"
    environment: Literal["local", "dev", "prod"] = "local"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    api_host: str = "0.0.0.0"  # noqa: S104 — сервис слушает внутри контейнера
    api_port: int = 8000

    # --- База данных ---
    database_url: str = "postgresql+asyncpg://vacancies:vacancies@localhost:5432/vacancies"
    db_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_pre_ping: bool = True

    # --- Redis и очередь задач ---
    redis_url: str = "redis://localhost:6379/0"
    rq_queue_name: str = "vacancies"
    rq_default_timeout: int = 900

    # --- Демо-пользователь ---
    # Авторизации в этой версии нет (п. 0.2 ТЗ): user_id всегда передаётся
    # в сервисный слой явно, а его значение по умолчанию берётся отсюда.
    demo_user_id: UUID = UUID("00000000-0000-0000-0000-000000000001")

    # --- Адаптеры внешних систем (раздел 9) ---
    # TODO: Real без ключа или URL бросает ExternalServiceError в методе
    # адаптера; model_validator на старте Settings не делается.
    llm_mode: Literal["mock", "real"] = "mock"
    llm_provider: Literal["openai", "anthropic", "openrouter"] = "openai"
    llm_api_key: SecretStr | None = None
    llm_base_url: str | None = None
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 30.0
    # П. 5.3 ТЗ: при невалидном JSON — ровно одна попытка повтора, затем ошибка.
    llm_max_retries: int = 1
    profile_mode: Literal["mock", "real"] = "mock"
    profile_service_url: str | None = None
    profile_timeout_seconds: float = 10.0

    # --- Парсеры (раздел 5.1) ---
    parsers_enabled: bool = False
    parser_default_interval_hours: int = 3
    telegram_api_id: int | None = None
    telegram_api_hash: SecretStr | None = None
    telegram_session_name: str = "vacancies"
    telegram_rate_limit_seconds: float = 2.0
    playwright_headless: bool = True
    playwright_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    http_request_delay_seconds: float = 1.5
    respect_robots_txt: bool = True

    # --- Логирование ---
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"

    # --- CORS ---
    # NoDecode обязателен: без него pydantic-settings пытается разобрать значение
    # списочного поля как JSON ещё до валидаторов и падает с SettingsError на
    # обычной строке из .env. С ним разбор целиком отдан _split_cors_origins.
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # --- Пагинация и health ---
    default_page_size: int = 20
    max_page_size: int = 100
    health_check_timeout_seconds: float = 2.0

    @field_validator(
        "llm_api_key",
        "llm_base_url",
        "profile_service_url",
        "telegram_api_id",
        "telegram_api_hash",
        mode="before",
    )
    @classmethod
    def _empty_string_is_none(cls, value: object) -> object:
        """Считать пустое значение в `.env` отсутствующим.

        В `.env.example` необязательные ключи присутствуют пустыми (`LLM_API_KEY=`),
        чтобы список переменных был полным. Без этого преобразования они стали бы
        `SecretStr('')` и `''`, и проверки вида `if settings.llm_api_key is None`
        на этапе 9 пропустили бы незаполненный ключ дальше.
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Разрешить перечисление origin'ов строкой через запятую.

        Без этого pydantic-settings требует в `.env` JSON-массив, и обычная
        строка `http://a,http://b` валит старт приложения.
        """
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Вернуть закэшированный экземпляр настроек."""
    return Settings()
