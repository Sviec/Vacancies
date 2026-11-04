"""Офлайн-тесты клиента hh: Settings без .env и httpx.MockTransport."""

from collections.abc import Callable
from urllib.parse import parse_qs, quote

import httpx
import pytest

from app.adapters.hh import HHClient
from app.config import Settings
from app.utils.errors import ExternalServiceError

_BASE = "https://hh.test"
_APP = "test-app-token"
_USER_AGENT = "hh-test-agent/1 (tester@example.com)"
_CLIENT_ID = "test-client-id"
_CREDENTIAL = "test-client-secret"
_METHODS = ("search", "vacancy", "areas", "dictionaries")


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "hh_app_token": _APP,
        "hh_user_agent": _USER_AGENT,
        "hh_base_url": _BASE,
        "hh_client_id": _CLIENT_ID,
        "hh_client_secret": _CREDENTIAL,
        "hh_request_delay_seconds": 1.0,
        "hh_timeout_seconds": 20.0,
        "hh_max_retries": 3,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


class _Clock:
    """Часы стоят на месте: sleep только записывает паузу, время не двигает."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)


def _forbid_http(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("HTTP client must not be created")


@pytest.fixture(autouse=True)
def _block_real_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """Любой клиент без MockTransport — ошибка теста, а не запрос в сеть."""
    real_init = httpx.AsyncClient.__init__

    def guarded(self: httpx.AsyncClient, *args: object, **kwargs: object) -> None:
        if not isinstance(kwargs.get("transport"), httpx.MockTransport):
            raise AssertionError("real network is not allowed")
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", guarded)
    monkeypatch.setattr(httpx.Client, "__init__", _forbid_http)


def _transport(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[list[httpx.Request], httpx.MockTransport]:
    seen: list[httpx.Request] = []

    def _spy(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "hh.test"
        assert request.url.host != "api.hh.ru"
        seen.append(request)
        return handler(request)

    return seen, httpx.MockTransport(_spy)


def _queue(responses: list[httpx.Response]) -> tuple[list[httpx.Request], httpx.MockTransport]:
    pending = list(responses)

    def handler(_request: httpx.Request) -> httpx.Response:
        return pending.pop(0)

    return _transport(handler)


def _client(
    transport: httpx.MockTransport,
    clock: _Clock | None = None,
    **overrides: object,
) -> tuple[HHClient, _Clock]:
    timer = clock or _Clock()
    client = HHClient(
        _settings(**overrides),
        transport=transport,
        sleep=timer.sleep,
        clock=timer.clock,
    )
    return client, timer


async def _invoke(client: HHClient, method: str) -> object:
    if method == "search":
        return await client.search({"text": "python"})
    if method == "vacancy":
        return await client.vacancy("1")
    if method == "areas":
        return await client.areas()
    if method == "dictionaries":
        return await client.dictionaries()
    raise AssertionError(method)


@pytest.mark.parametrize("method", _METHODS)
async def test_missing_token_makes_no_request(method: str) -> None:
    seen, transport = _queue([httpx.Response(200, json={"items": []})])
    client, clock = _client(transport, hh_app_token=None)
    with pytest.raises(ExternalServiceError) as exc_info:
        await _invoke(client, method)
    assert seen == []
    assert clock.slept == []
    assert type(exc_info.value) is ExternalServiceError
    assert exc_info.value.message == "HH application token is not configured"
    assert exc_info.value.details == {"service": "hh", "reason": "missing_token"}


@pytest.mark.parametrize("method", _METHODS)
async def test_missing_user_agent_makes_no_request(method: str) -> None:
    seen, transport = _queue([httpx.Response(200, json={"items": []})])
    client, clock = _client(transport, hh_user_agent=None)
    with pytest.raises(ExternalServiceError) as exc_info:
        await _invoke(client, method)
    assert seen == []
    assert clock.slept == []
    assert type(exc_info.value) is ExternalServiceError
    assert exc_info.value.message == "HH User-Agent is not configured"
    assert exc_info.value.details == {"service": "hh", "reason": "missing_user_agent"}


async def test_missing_config_does_not_construct_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx.AsyncClient, "__init__", _forbid_http)
    monkeypatch.setattr(httpx.Client, "__init__", _forbid_http)
    without_token, _clock = _client_without_transport(hh_app_token=None)
    without_agent, _clock = _client_without_transport(hh_user_agent=None)
    for client in (without_token, without_agent):
        for method in _METHODS:
            with pytest.raises(ExternalServiceError):
                await _invoke(client, method)
    blank_id = HHClient(_settings(), sleep=_Clock().sleep, clock=_Clock().clock)
    with pytest.raises(ExternalServiceError) as exc_info:
        await blank_id.vacancy("  ")
    assert exc_info.value.details == {"service": "hh", "reason": "invalid_id"}


def _client_without_transport(**overrides: object) -> tuple[HHClient, _Clock]:
    timer = _Clock()
    return (
        HHClient(_settings(**overrides), sleep=timer.sleep, clock=timer.clock),
        timer,
    )


async def test_headers_paths_and_repeated_query() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/areas":
            return httpx.Response(200, json=[{"id": "113", "name": "Россия"}])
        if request.url.path == "/dictionaries":
            return httpx.Response(200, json={"currency": []})
        if request.url.path.startswith("/vacancies/"):
            return httpx.Response(200, json={"id": "12/3 4"})
        return httpx.Response(200, json={"items": [], "found": 0})

    seen, transport = _transport(handler)
    client, clock = _client(transport, hh_request_delay_seconds=0)
    vacancy_id = "12/3 4"
    search = await client.search(
        {"text": "python", "professional_role": ["96", "160"]},
    )
    card = await client.vacancy(vacancy_id)
    areas = await client.areas()
    dictionaries = await client.dictionaries()

    assert search == {"items": [], "found": 0}
    assert card == {"id": vacancy_id}
    assert areas == [{"id": "113", "name": "Россия"}]
    assert dictionaries == {"currency": []}
    assert clock.slept == []
    assert len(seen) == 4

    assert seen[0].method == "GET"
    assert seen[0].url.path == "/vacancies"
    query = seen[0].url.query
    parsed_query = parse_qs(query.decode() if isinstance(query, bytes) else query)
    assert parsed_query["professional_role"] == ["96", "160"]
    assert parsed_query["text"] == ["python"]
    assert seen[1].url.raw_path == b"/vacancies/" + quote(vacancy_id, safe="").encode()
    assert seen[2].url.path == "/areas"
    assert seen[3].url.path == "/dictionaries"

    for request in seen:
        assert request.headers["hh-user-agent"] == _USER_AGENT
        assert request.headers["user-agent"] == _USER_AGENT
        assert request.headers["authorization"] == f"Bearer {_APP}"
        assert request.headers["accept"] == "application/json"
        blob = " ".join([request.headers.get(key, "") for key in request.headers])
        assert "client_secret" not in blob.lower()
        assert _CREDENTIAL not in blob
        assert _CLIENT_ID not in blob
        assert _CREDENTIAL.encode() not in request.content
        assert _CLIENT_ID not in str(request.url)
        assert _CREDENTIAL not in str(request.url)


async def test_second_call_waits_one_delay() -> None:
    seen, transport = _queue(
        [
            httpx.Response(200, json={"items": []}),
            httpx.Response(200, json={"id": "1"}),
        ]
    )
    client, clock = _client(transport, hh_request_delay_seconds=1.0)
    await client.search({"text": "python"})
    await client.vacancy("1")
    assert len(seen) == 2
    assert clock.slept == [1.0]


async def test_retry_after_replaces_backoff() -> None:
    seen, transport = _queue(
        [
            httpx.Response(
                429,
                headers={"Retry-After": "5"},
                json={"errors": [{"type": "too_many_requests"}]},
            ),
            httpx.Response(200, json={"items": []}),
        ]
    )
    delay = 1.0
    client, clock = _client(transport, hh_request_delay_seconds=delay)
    result = await client.search({"text": "python"})
    assert result == {"items": []}
    assert len(seen) == 2
    assert clock.slept == [max(delay * (2**0), 5)]


async def test_retries_500_then_503_then_200() -> None:
    seen, transport = _queue(
        [
            httpx.Response(500, content=b""),
            httpx.Response(503, content=b""),
            httpx.Response(200, json={"id": "9"}),
        ]
    )
    client, clock = _client(transport, hh_request_delay_seconds=1.0)
    assert await client.vacancy("9") == {"id": "9"}
    assert len(seen) == 3
    assert clock.slept == [1.0, 2.0]


async def test_exhausted_503_reports_attempts() -> None:
    settings = _settings()
    attempts = 1 + settings.hh_max_retries
    seen, transport = _queue([httpx.Response(503, content=b"")] * attempts)
    client, _clock = _client(transport)
    with pytest.raises(ExternalServiceError) as exc_info:
        await client.dictionaries()
    assert len(seen) == attempts
    assert type(exc_info.value) is ExternalServiceError
    assert exc_info.value.message == "External service call failed"
    assert exc_info.value.details == {
        "service": "hh",
        "status_code": 503,
        "attempts": attempts,
    }
    assert _APP not in exc_info.value.message
    assert _APP not in str(exc_info.value.details)


@pytest.mark.parametrize("status_code", [400, 403, 404])
async def test_client_error_is_not_retried(status_code: int) -> None:
    seen, transport = _queue(
        [
            httpx.Response(
                status_code,
                headers={"Retry-After": "5"},
                json={"errors": [{"type": "bad_argument"}], "request_id": "do-not-leak"},
            ),
            httpx.Response(200, json={"items": []}),
        ]
    )
    client, clock = _client(transport)
    with pytest.raises(ExternalServiceError) as exc_info:
        await client.search({"text": "python"})
    assert len(seen) == 1
    assert clock.slept == []
    assert exc_info.value.message == "External service call failed"
    assert exc_info.value.details == {
        "service": "hh",
        "status_code": status_code,
        "hh_error_type": "bad_argument",
    }
    rendered = f"{exc_info.value.message} {exc_info.value.details}"
    assert "do-not-leak" not in rendered
    assert _APP not in rendered
    assert _CREDENTIAL not in rendered


async def test_read_timeout_is_not_retried() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.url.host == "hh.test"
        raise httpx.ReadTimeout("timed out", request=request)

    client, clock = _client(httpx.MockTransport(handler))
    with pytest.raises(ExternalServiceError) as exc_info:
        await client.areas()
    assert len(seen) == 1
    assert clock.slept == []
    assert type(exc_info.value) is ExternalServiceError
    assert exc_info.value.message == "External service call failed"
    assert exc_info.value.details == {"service": "hh", "reason": "timeout"}


async def test_non_json_and_wrong_shape_are_invalid_payload() -> None:
    seen, transport = _queue(
        [
            httpx.Response(200, content=b"not-json"),
            httpx.Response(200, json={"items": []}),
        ]
    )
    client, clock = _client(transport)
    with pytest.raises(ExternalServiceError) as exc_info:
        await client.search({"text": "python"})
    assert len(seen) == 1
    assert clock.slept == []
    assert exc_info.value.details == {"service": "hh", "reason": "invalid_payload"}

    seen_areas, transport_areas = _queue(
        [
            httpx.Response(200, json={"id": "113"}),
            httpx.Response(200, json=[]),
        ]
    )
    areas_client, areas_clock = _client(transport_areas)
    with pytest.raises(ExternalServiceError) as areas_exc:
        await areas_client.areas()
    assert len(seen_areas) == 1
    assert areas_clock.slept == []
    assert areas_exc.value.details == {"service": "hh", "reason": "invalid_payload"}
