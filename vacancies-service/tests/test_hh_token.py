"""Офлайн-тесты scripts.hh_token: без .env и без сети."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

import scripts.hh_token as cli
from app.config import Settings

_BASE = "https://hh.test"
_CLIENT_ID = "test-client-id"
_CREDENTIAL = "test-client-secret"
_USER_AGENT = "hh-test-agent/1 (tester@example.com)"
_GRANTED = "test-access-token"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "hh_client_id": _CLIENT_ID,
        "hh_client_secret": _CREDENTIAL,
        "hh_user_agent": _USER_AGENT,
        "hh_base_url": _BASE,
        "hh_app_token": None,
        "hh_timeout_seconds": 12.5,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def _forbid_http(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("HTTP client must not be created")


@pytest.fixture(autouse=True)
def _block_real_http(monkeypatch: pytest.MonkeyPatch) -> None:
    real_init = httpx.AsyncClient.__init__

    def guarded(self: httpx.AsyncClient, *args: object, **kwargs: object) -> None:
        if not isinstance(kwargs.get("transport"), httpx.MockTransport):
            raise AssertionError("real network is not allowed")
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", guarded)
    monkeypatch.setattr(httpx.Client, "__init__", _forbid_http)


def _use_settings(monkeypatch: pytest.MonkeyPatch, **overrides: object) -> Settings:
    settings = _settings(**overrides)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    return settings


def _stamp_at(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setattr(cli, "default_stamp_path", lambda: path)


async def _fail_sleep(_seconds: float) -> None:
    raise AssertionError("sleep must not be called")


def test_without_yes_does_not_touch_network(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    stamp = tmp_path / ".hh_token_last_request"
    _stamp_at(monkeypatch, stamp)
    monkeypatch.setattr(httpx.AsyncClient, "__init__", _forbid_http)
    monkeypatch.setattr(httpx.Client, "__init__", _forbid_http)

    def _explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("must not read settings or call hh")

    monkeypatch.setattr(cli, "get_settings", _explode)
    monkeypatch.setattr(cli, "request_application_token", _explode)

    assert cli.main([]) == cli.EXIT_REFUSED
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "токен будет отозван" in captured.err
    assert "--yes" in captured.err
    assert not stamp.exists()


@pytest.mark.parametrize(
    "missing",
    ["hh_client_id", "hh_client_secret", "hh_user_agent"],
)
def test_missing_credential_exits_before_network(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    missing: str,
) -> None:
    stamp = tmp_path / ".hh_token_last_request"
    _stamp_at(monkeypatch, stamp)
    monkeypatch.setattr(httpx.AsyncClient, "__init__", _forbid_http)
    monkeypatch.setattr(httpx.Client, "__init__", _forbid_http)
    _use_settings(monkeypatch, **{missing: None})

    assert cli.main(["--yes"]) == cli.EXIT_ERROR
    captured = capsys.readouterr()
    assert captured.out == ""
    assert _CREDENTIAL not in captured.err
    assert _GRANTED not in captured.err
    assert not stamp.exists()


async def test_fresh_stamp_makes_no_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(httpx.AsyncClient, "__init__", _forbid_http)
    monkeypatch.setattr(httpx.Client, "__init__", _forbid_http)
    moment = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
    stamp = tmp_path / ".hh_token_last_request"
    original = moment.isoformat() + "\n"
    stamp.write_text(original, encoding="utf-8")

    with pytest.raises(cli.HHTokenScriptError) as exc_info:
        await cli.request_application_token(
            _settings(),
            stamp_path=stamp,
            now=lambda: moment + timedelta(seconds=30),
            sleep=_fail_sleep,
        )

    assert exc_info.value.exit_code == cli.EXIT_REFUSED
    assert "270" in exc_info.value.message
    assert stamp.read_text(encoding="utf-8") == original


async def test_broken_stamp_makes_no_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(httpx.AsyncClient, "__init__", _forbid_http)
    monkeypatch.setattr(httpx.Client, "__init__", _forbid_http)
    stamp = tmp_path / ".hh_token_last_request"
    stamp.write_text("not-a-timestamp\n", encoding="utf-8")

    with pytest.raises(cli.HHTokenScriptError) as exc_info:
        await cli.request_application_token(
            _settings(),
            stamp_path=stamp,
            now=lambda: datetime(2026, 11, 4, 12, 0, tzinfo=UTC),
            sleep=_fail_sleep,
        )

    assert exc_info.value.exit_code == cli.EXIT_REFUSED
    assert "вручную" in exc_info.value.message
    assert stamp.read_text(encoding="utf-8") == "not-a-timestamp\n"


def _install_transport(
    monkeypatch: pytest.MonkeyPatch,
    transport: httpx.MockTransport,
    opened: list[dict[str, object]],
) -> None:
    real = httpx.AsyncClient

    def factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        opened.append(
            {
                "timeout": kwargs.get("timeout"),
                "follow_redirects": kwargs.get("follow_redirects"),
            }
        )
        kwargs["transport"] = transport
        return real(*args, **kwargs)

    monkeypatch.setattr(cli.httpx, "AsyncClient", factory)


def test_success_prints_only_the_token(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    stamp = tmp_path / ".hh_token_last_request"
    _stamp_at(monkeypatch, stamp)
    settings = _use_settings(monkeypatch)
    seen: list[httpx.Request] = []
    opened: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "hh.test"
        assert request.url.host != "api.hh.ru"
        seen.append(request)
        return httpx.Response(200, json={"access_token": _GRANTED, "token_type": "bearer"})

    _install_transport(monkeypatch, httpx.MockTransport(handler), opened)

    assert cli.main(["--yes"]) == cli.EXIT_OK
    captured = capsys.readouterr()
    assert captured.out == f"{_GRANTED}\n"
    assert "HH_APP_TOKEN" in captured.err
    assert ".env" in captured.err
    assert _CREDENTIAL not in captured.out
    assert _CREDENTIAL not in captured.err
    assert _GRANTED not in captured.err
    assert len(seen) == 1
    assert len(opened) == 1
    assert opened[0]["timeout"] == settings.hh_timeout_seconds
    assert opened[0]["follow_redirects"] is False

    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == f"{_BASE}/token"
    body = parse_qs(request.content.decode())
    assert body["grant_type"] == ["client_credentials"]
    assert body["client_id"] == [_CLIENT_ID]
    assert body["client_secret"] == [_CREDENTIAL]
    assert request.headers["hh-user-agent"] == _USER_AGENT
    assert request.headers["user-agent"] == _USER_AGENT
    assert "authorization" not in request.headers
    assert "application/x-www-form-urlencoded" in request.headers["content-type"]
    assert stamp.is_file()
    parsed = datetime.fromisoformat(stamp.read_text(encoding="utf-8").strip())
    assert parsed.tzinfo is not None


def test_forbidden_then_cooldown_does_not_call_again(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    stamp = tmp_path / ".hh_token_last_request"
    _stamp_at(monkeypatch, stamp)
    _use_settings(monkeypatch)
    seen: list[httpx.Request] = []
    opened: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "hh.test"
        seen.append(request)
        return httpx.Response(
            403,
            json={"errors": [{"type": "forbidden"}], "description": "do-not-leak"},
        )

    _install_transport(monkeypatch, httpx.MockTransport(handler), opened)

    assert cli.main(["--yes"]) == cli.EXIT_ERROR
    first = capsys.readouterr()
    assert "403" in first.err
    assert "do-not-leak" not in first.err
    assert _CREDENTIAL not in first.err
    assert stamp.is_file()
    assert len(seen) == 1
    assert len(opened) == 1

    assert cli.main(["--yes"]) == cli.EXIT_REFUSED
    second = capsys.readouterr()
    assert second.out == ""
    assert "5 минут" in second.err
    assert _CREDENTIAL not in second.err
    assert len(seen) == 1
    assert len(opened) == 1
