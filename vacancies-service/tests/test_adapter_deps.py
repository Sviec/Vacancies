"""Фабрики адаптеров и Depends: без сети и без чтения секрета в mock."""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.adapters.llm import MockLLMAdapter, RealLLMAdapter, build_llm_adapter
from app.adapters.profile import MockProfileAdapter, RealProfileAdapter, build_profile_adapter
from app.api.deps import LLMAdapterDep
from app.config import Settings, get_settings


def test_build_llm_mock_ignores_filled_key() -> None:
    settings = Settings(
        _env_file=None,
        llm_mode="mock",
        llm_api_key=SecretStr("sk-secret"),
        llm_base_url="https://should-not-be-called.example/v1",
    )
    adapter = build_llm_adapter(settings)
    assert isinstance(adapter, MockLLMAdapter)
    assert not isinstance(adapter, RealLLMAdapter)


def test_build_llm_real_type() -> None:
    settings = Settings(_env_file=None, llm_mode="real", llm_api_key=SecretStr("sk-secret"))
    adapter = build_llm_adapter(settings)
    assert isinstance(adapter, RealLLMAdapter)


def test_build_profile_mock_and_real() -> None:
    mock_settings = Settings(
        _env_file=None,
        profile_mode="mock",
        profile_service_url="https://profile.example",
    )
    real_settings = Settings(
        _env_file=None,
        profile_mode="real",
        profile_service_url="https://profile.example",
    )
    assert isinstance(build_profile_adapter(mock_settings), MockProfileAdapter)
    assert isinstance(build_profile_adapter(real_settings), RealProfileAdapter)


async def test_get_llm_adapter_uses_depends_settings(app: FastAPI) -> None:
    custom = Settings(_env_file=None, llm_mode="real", llm_api_key=SecretStr("sk-from-depends"))
    app.dependency_overrides[get_settings] = lambda: custom

    @app.get("/_test/llm-adapter")
    async def _probe(adapter: LLMAdapterDep) -> dict[str, str]:
        return {"kind": type(adapter).__name__}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/_test/llm-adapter")
    assert response.status_code == 200
    assert response.json() == {"kind": "RealLLMAdapter"}
