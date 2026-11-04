"""Настройки сервиса.

Все дефолты подобраны так, чтобы сервис поднимался и полностью работал в
mock-режиме, без внешних ключей и без доступа в сеть (п. 0.3 и раздел 11.2 ТЗ).

Веса скоринга резюме (раздел 5.4) и матчинга (раздел 5.6) сюда сознательно
НЕ вынесены: это константы в коде. Иначе воспроизводимость оценки
(критерий приёмки 5) стала бы зависеть от окружения.
"""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, ValidationInfo, field_validator
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

    # --- Сессия входа ---
    # Случайный токен в httpOnly-куке. Secure включайте, когда сайт открыт по HTTPS.
    session_cookie_name: str = "session"
    session_ttl_seconds: int = 14 * 24 * 60 * 60
    session_cookie_secure: bool = False

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

    # --- hh.ru (этап 13a) ---
    # TODO: пустой HH_APP_TOKEN не валит старт; ошибка в методе HHClient.
    # Сервис токен не перевыпускает.
    hh_client_id: SecretStr | None = None
    hh_client_secret: SecretStr | None = None
    hh_app_token: SecretStr | None = None
    hh_user_agent: str | None = "vacancies-service/0.1 (you@example.com)"
    hh_base_url: str = "https://api.hh.ru"
    hh_request_delay_seconds: float = Field(default=1.0, ge=0)
    hh_timeout_seconds: float = Field(default=20.0, gt=0)
    # Число повторов после первой попытки: всего попыток 1 + hh_max_retries.
    hh_max_retries: int = Field(default=3, ge=0)

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
        "hh_client_id",
        "hh_client_secret",
        "hh_app_token",
        "hh_user_agent",
        mode="before",
    )
    @classmethod
    def _empty_string_is_none(cls, value: object, info: ValidationInfo) -> object:
        """Считать пустое значение в `.env` отсутствующим.

        В `.env.example` необязательные ключи присутствуют пустыми (`LLM_API_KEY=`),
        чтобы список переменных был полным. Без этого преобразования они стали бы
        `SecretStr('')` и `''`, и проверки вида `if settings.llm_api_key is None`
        на этапе 9 пропустили бы незаполненный ключ дальше.
        Пустой HH User-Agent тоже отсутствует; непустой обрезается.
        """
        if isinstance(value, str) and not value.strip():
            return None
        if info.field_name == "hh_user_agent" and isinstance(value, str):
            return value.strip()
        return value

    @field_validator("hh_base_url", mode="before")
    @classmethod
    def _blank_hh_base_url_is_default(cls, value: object) -> object:
        """Пустой URL не становится None: клиенту нужна строка."""
        if isinstance(value, str) and not value.strip():
            return "https://api.hh.ru"
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
