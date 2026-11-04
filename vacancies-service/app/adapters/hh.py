"""HTTP-клиент api.hh.ru.

Импорт модуля не создаёт ``httpx.AsyncClient``. ``PARSERS_ENABLED`` здесь не
проверяется: при ``false`` сети нет, потому что вызовов нет. ``client_id`` и
``client_secret`` клиент не читает — их берёт только ``scripts/hh_token.py``.
"""

import asyncio
import re
import time
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, cast
from urllib.parse import quote

import httpx

from app.config import Settings
from app.utils.errors import ExternalServiceError

_SERVICE = "hh"
_RETRY_STATUSES = frozenset({429, 500, 503})
_INTEGER_SECONDS = re.compile(r"[+-]?\d+")


class HHClient:
    """Запросы к API hh. Один экземпляр выполняет их по очереди."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._sleep = sleep
        self._clock = clock
        self._lock = asyncio.Lock()
        self._last_attempt_at: float | None = None

    async def search(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """Поиск вакансий. ``params`` уходит в query как есть, списки повторяют ключ."""
        return _as_object(await self._get("/vacancies", params=params))

    async def vacancy(self, id: str) -> dict[str, Any]:
        """Карточка вакансии. Пустой id — ошибка до сети."""
        cleaned = id.strip()
        if not cleaned:
            raise ExternalServiceError(
                "HH vacancy id is empty",
                details={"service": _SERVICE, "reason": "invalid_id"},
            )
        return _as_object(await self._get(f"/vacancies/{quote(cleaned, safe='')}"))

    async def areas(self) -> list[Any]:
        """Дерево регионов."""
        return _as_array(await self._get("/areas"))

    async def dictionaries(self) -> dict[str, Any]:
        """Справочники hh."""
        return _as_object(await self._get("/dictionaries"))

    def _headers(self) -> dict[str, str]:
        """Проверить токен и User-Agent до создания HTTP-клиента."""
        token = self._settings.hh_app_token
        if token is None:
            raise ExternalServiceError(
                "HH application token is not configured",
                details={"service": _SERVICE, "reason": "missing_token"},
            )
        user_agent = self._settings.hh_user_agent
        if user_agent is None:
            raise ExternalServiceError(
                "HH User-Agent is not configured",
                details={"service": _SERVICE, "reason": "missing_user_agent"},
            )
        return {
            "HH-User-Agent": user_agent,
            "User-Agent": user_agent,
            "Authorization": f"Bearer {token.get_secret_value()}",
            "Accept": "application/json",
        }

    async def _get(self, path: str, *, params: Mapping[str, Any] | None = None) -> object:
        headers = self._headers()
        url = f"{self._settings.hh_base_url.rstrip('/')}{path}"
        async with self._lock:
            async with httpx.AsyncClient(
                timeout=self._settings.hh_timeout_seconds,
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = await self._fetch(client, url, params=params, headers=headers)
            return _decode(response)

    async def _fetch(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: Mapping[str, Any] | None,
        headers: dict[str, str],
    ) -> httpx.Response:
        attempts = 1 + max(0, self._settings.hh_max_retries)
        for attempt_index in range(attempts):
            await self._pause_before_attempt()
            try:
                response = await client.get(url, params=cast(Any, params), headers=headers)
            except httpx.RequestError as exc:
                # TODO: таймаут и обрыв соединения не повторяются.
                self._last_attempt_at = self._clock()
                raise _network_error(exc) from None
            self._last_attempt_at = self._clock()
            if 200 <= response.status_code < 300:
                return response
            retryable = response.status_code in _RETRY_STATUSES
            if not retryable or attempt_index + 1 == attempts:
                raise _status_error(response, attempts=attempts if retryable else None)
            wait = _retry_wait(self._settings.hh_request_delay_seconds, attempt_index, response)
            if wait > 0:
                await self._sleep(wait)
            # Ожидание повтора заменяет паузу: следующая попытка не досыпает delay.
            self._last_attempt_at = self._clock() - self._settings.hh_request_delay_seconds
        raise ExternalServiceError(
            "External service call failed",
            details={"service": _SERVICE, "attempts": attempts},
        )

    async def _pause_before_attempt(self) -> None:
        """Доспать паузу с конца предыдущей попытки. Первая попытка не ждёт."""
        delay = self._settings.hh_request_delay_seconds
        started = self._last_attempt_at
        if delay == 0 or started is None:
            return
        remaining = delay - (self._clock() - started)
        if remaining > 0:
            await self._sleep(remaining)


def _retry_wait(delay: float, retry_index: int, response: httpx.Response) -> float:
    """Backoff с нуля. ``Retry-After`` увеличивает ожидание, но не суммируется с паузой."""
    backoff = delay * (2.0**retry_index)
    header = response.headers.get("Retry-After")
    if header is None:
        return backoff
    retry_after = _retry_after_seconds(header)
    if retry_after is None:
        return backoff
    return max(backoff, retry_after)


def _retry_after_seconds(header: str) -> float | None:
    """Целые секунды или HTTP-date. Неразобранное и отрицательное — нет значения."""
    text = header.strip()
    if _INTEGER_SECONDS.fullmatch(text):
        seconds = int(text)
        if seconds < 0:
            return None
        return float(seconds)
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    delta = (parsed - datetime.now(UTC)).total_seconds()
    if delta < 0:
        return None
    return delta


def _hh_error_type(response: httpx.Response) -> str | None:
    """Достать ``errors[0].type``. Сырое тело в ошибку не попадает."""
    try:
        payload = response.json()
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    errors = payload.get("errors")
    if not isinstance(errors, list) or not errors:
        return None
    first = errors[0]
    if not isinstance(first, dict):
        return None
    error_type = first.get("type")
    if not isinstance(error_type, str):
        return None
    return error_type


def _decode(response: httpx.Response) -> object:
    try:
        return response.json()
    except (ValueError, UnicodeDecodeError):
        raise _invalid_payload() from None


def _as_object(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise _invalid_payload()
    return cast(dict[str, Any], payload)


def _as_array(payload: object) -> list[Any]:
    if not isinstance(payload, list):
        raise _invalid_payload()
    return payload


def _invalid_payload() -> ExternalServiceError:
    return ExternalServiceError(
        "External service call failed",
        details={"service": _SERVICE, "reason": "invalid_payload"},
    )


def _network_error(exc: httpx.RequestError) -> ExternalServiceError:
    reason = "timeout" if isinstance(exc, httpx.TimeoutException) else "connect"
    return ExternalServiceError(
        "External service call failed",
        details={"service": _SERVICE, "reason": reason},
    )


def _status_error(response: httpx.Response, *, attempts: int | None) -> ExternalServiceError:
    details: dict[str, Any] = {
        "service": _SERVICE,
        "status_code": response.status_code,
    }
    error_type = _hh_error_type(response)
    if error_type is not None:
        details["hh_error_type"] = error_type
    if attempts is not None:
        details["attempts"] = attempts
    return ExternalServiceError("External service call failed", details=details)
