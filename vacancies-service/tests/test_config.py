"""Тесты конфигурации: mock-режим по умолчанию и разбор CORS-origin'ов."""

from app.config import Settings


def test_defaults_enable_mock_mode(settings: Settings):
    assert settings.llm_mode == "mock"
    assert settings.profile_mode == "mock"
    assert settings.llm_api_key is None


def test_cors_origins_accepts_comma_separated_string():
    parsed = Settings(_env_file=None, cors_origins="http://a,http://b")

    assert parsed.cors_origins == ["http://a", "http://b"]
