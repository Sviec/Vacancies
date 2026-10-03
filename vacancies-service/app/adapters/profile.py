"""Адаптер profile-core-service: mock-фикстура и HTTP GET (раздел 9 ТЗ).

Выбор реализации — `build_profile_adapter`. Импорт модуля не создаёт клиент
и не требует URL.
"""

import json
from typing import Protocol
from uuid import UUID

import httpx
from pydantic import ValidationError

from app.adapters.fixtures import mock_profile_snapshot
from app.config import Settings
from app.schemas.adapters import ProfileSnapshot
from app.utils.errors import ExternalServiceError

_SERVICE = "profile"


class ProfileAdapter(Protocol):
    """Контракт получения профиля пользователя."""

    async def get_profile(self, user_id: UUID) -> ProfileSnapshot:
        """Вернуть навыки, опыт, образование и контакты пользователя."""
        ...


class MockProfileAdapter:
    """Фикстура профиля. Не принимает Settings и не открывает HTTP."""

    # TODO: экран «Профиль» по-прежнему копирует поля резюме; адаптер эти поля
    # только умеет отдать.
    async def get_profile(self, user_id: UUID) -> ProfileSnapshot:  # noqa: ARG002
        """Один снимок на любой user_id."""
        return mock_profile_snapshot()


class RealProfileAdapter:
    """GET профиля. Клиент создаётся внутри метода, не в конструкторе."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def get_profile(self, user_id: UUID) -> ProfileSnapshot:
        """Забрать снимок. Ошибки конфига и сети — ExternalServiceError, без повтора."""
        # TODO: profile-core — GET {PROFILE_SERVICE_URL}/users/{user_id} без
        # авторизации; лишние поля корня игнорируются.
        base_url = self._settings.profile_service_url
        if base_url is None:
            raise ExternalServiceError(
                "Profile service URL is not configured",
                details={"service": _SERVICE, "reason": "missing_service_url"},
            )
        url = f"{base_url.rstrip('/')}/users/{user_id}"
        try:
            async with httpx.AsyncClient(
                timeout=self._settings.profile_timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.get(url, headers={"Accept": "application/json"})
        except httpx.RequestError as exc:
            raise _network_error(exc) from None
        if response.status_code < 200 or response.status_code >= 300:
            raise _status_error(response.status_code)
        return _parse_snapshot(response)


def build_profile_adapter(settings: Settings) -> ProfileAdapter:
    """Mock не читает URL и не создаёт клиент. Real получает Settings как есть."""
    if settings.profile_mode == "mock":
        return MockProfileAdapter()
    return RealProfileAdapter(settings)


def _network_error(exc: httpx.RequestError) -> ExternalServiceError:
    reason = "timeout" if isinstance(exc, httpx.TimeoutException) else "connect"
    return ExternalServiceError(
        "External service call failed",
        details={"service": _SERVICE, "reason": reason},
    )


def _status_error(status_code: int) -> ExternalServiceError:
    return ExternalServiceError(
        "External service call failed",
        details={"service": _SERVICE, "status_code": status_code},
    )


def _invalid_payload() -> ExternalServiceError:
    return ExternalServiceError(
        "Profile service returned an invalid payload",
        details={"service": _SERVICE, "reason": "invalid_payload"},
    )


def _parse_snapshot(response: httpx.Response) -> ProfileSnapshot:
    """2xx и JSON-объект, который проходит ProfileSnapshot. Иначе — ошибка вызова."""
    try:
        payload = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise _invalid_payload() from None
    if not isinstance(payload, dict):
        raise _invalid_payload()
    try:
        return ProfileSnapshot.model_validate(payload)
    except ValidationError:
        raise _invalid_payload() from None
