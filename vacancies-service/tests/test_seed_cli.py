"""Офлайн-проверки CLI сида: отказы происходят до создания engine."""

import argparse
import io
from datetime import UTC, datetime, timedelta
from typing import NoReturn

import pytest

import scripts.seed as cli
from app.config import Settings


def _no_engine(*_args: object, **_kwargs: object) -> NoReturn:
    msg = "init_engine must not be called"
    raise AssertionError(msg)


@pytest.fixture
def no_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "init_engine", _no_engine)
    monkeypatch.setattr(cli, "configure_logging", lambda _settings: None)


def _use_settings(monkeypatch: pytest.MonkeyPatch, **values: object) -> Settings:
    settings = Settings(_env_file=None, **values)  # type: ignore[arg-type]
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    return settings


def test_parse_now_accepts_aware_past_time() -> None:
    assert cli.parse_now("2026-09-28T12:00:00+00:00") == datetime(2026, 9, 28, 12, tzinfo=UTC)
    assert cli.parse_now("2026-09-28T15:00:00+03:00") == datetime(2026, 9, 28, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    "value",
    [
        "2026-09-28T12:00:00",
        "not-a-date",
        (datetime.now(UTC) + timedelta(days=1)).isoformat(),
    ],
)
def test_parse_now_rejects_naive_invalid_and_future(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        cli.parse_now(value)


def test_parser_defaults() -> None:
    args = cli.build_parser().parse_args([])
    assert args.reset is False
    assert args.yes is False
    assert args.dry_run is False
    assert args.now is None
    assert args.no_actions is False
    assert args.no_score_check is False
    assert args.preview == 3


def test_parser_rejects_negative_preview() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["--preview", "-1"])


def _never_read(_prompt: str) -> str:
    msg = "must not prompt"
    raise AssertionError(msg)


def test_confirm_reset_without_tty_and_yes_is_refused() -> None:
    assert not cli.confirm_reset(
        "vacancies", assume_yes=False, stdin_is_tty=False, read=_never_read
    )


def test_confirm_reset_with_yes() -> None:
    assert cli.confirm_reset("vacancies", assume_yes=True, stdin_is_tty=False, read=_never_read)


def test_confirm_reset_with_database_name() -> None:
    assert cli.confirm_reset(
        "vacancies", assume_yes=False, stdin_is_tty=True, read=lambda _p: " vacancies\n"
    )


def test_confirm_reset_with_other_name() -> None:
    assert not cli.confirm_reset(
        "vacancies", assume_yes=False, stdin_is_tty=True, read=lambda _p: "vacancies_test"
    )


def test_confirm_reset_on_eof() -> None:
    def eof(_prompt: str) -> str:
        raise EOFError

    assert not cli.confirm_reset("vacancies", assume_yes=False, stdin_is_tty=True, read=eof)


@pytest.mark.usefixtures("no_db")
def test_reset_without_confirmation_exits_before_engine(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_settings(
        monkeypatch, database_url="postgresql+asyncpg://u:secret@localhost:5433/vacancies_test"
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert cli.main(["--reset"]) == cli.EXIT_REFUSED
    captured = capsys.readouterr()
    assert "target: postgresql+asyncpg://u:***@localhost:5433/vacancies_test" in captured.out
    assert "secret" not in captured.out
    assert "--reset was not confirmed" in captured.err


@pytest.mark.usefixtures("no_db")
@pytest.mark.parametrize("argv", [[], ["--reset", "--yes"], ["--dry-run"]])
def test_prod_is_refused_before_engine(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    _use_settings(monkeypatch, environment="prod")
    assert cli.main(argv) == cli.EXIT_REFUSED
    assert "disabled in ENVIRONMENT=prod" in capsys.readouterr().err
