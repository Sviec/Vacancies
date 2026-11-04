"""Тесты конфигурации: mock-режим по умолчанию и разбор CORS-origin'ов."""

import sys

import pytest

from app.config import Settings
from app.main import create_app

_HH_USER_AGENT = "vacancies-service/0.1 (you@example.com)"


def _bare_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


def test_defaults_enable_mock_mode(settings: Settings):
    assert settings.llm_mode == "mock"
    assert settings.profile_mode == "mock"
    assert settings.llm_api_key is None


def test_cors_origins_accepts_comma_separated_string():
    parsed = Settings(_env_file=None, cors_origins="http://a,http://b")

    assert parsed.cors_origins == ["http://a", "http://b"]


def test_hh_defaults_and_blank_strings_are_absent(settings: Settings) -> None:
    assert settings.hh_app_token is None
    assert settings.hh_client_id is None
    assert settings.hh_client_secret is None
    assert settings.hh_user_agent == _HH_USER_AGENT
    assert settings.hh_base_url == "https://api.hh.ru"
    assert settings.hh_request_delay_seconds == 1.0
    assert settings.hh_timeout_seconds == 20.0
    assert settings.hh_max_retries == 3

    blank = _bare_settings(
        **{
            "hh_client_id": "",
            "hh_client_secret": "  ",
            "hh_app_token": "\t",
            "hh_user_agent": "  ",
            "hh_base_url": "  ",
        }
    )
    assert blank.hh_client_id is None
    assert blank.hh_client_secret is None
    assert blank.hh_app_token is None
    assert blank.hh_user_agent is None
    assert blank.hh_base_url == "https://api.hh.ru"

    stripped = _bare_settings(hh_user_agent="  agent/1 (a@b.c)  ")
    assert stripped.hh_user_agent == "agent/1 (a@b.c)"


def test_create_app_does_not_import_hh_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Старт приложения не тянет HTTP-клиент hh. Сам модуль здесь не импортируется."""
    monkeypatch.setattr("app.main.get_settings", _bare_settings)
    saved = sys.modules.pop("app.adapters.hh", None)
    try:
        create_app()
        assert "app.adapters.hh" not in sys.modules
    finally:
        if saved is not None:
            sys.modules["app.adapters.hh"] = saved
