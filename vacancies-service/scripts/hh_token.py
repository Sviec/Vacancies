"""Ручной обмен client_credentials на токен приложения hh.ru.

Запуск из каталога ``vacancies-service``:

    python -m scripts.hh_token --yes

На старте API и в тестах скрипт не вызывается. Файл ``.env`` не меняется.
Повторный POST /token отзывает текущий токен приложения, поэтому без ``--yes``
запроса нет, а с ``--yes`` — не чаще одного раза в 5 минут.

Коды выхода: 0 — токен напечатан; 1 — нет ключей или hh ответил ошибкой;
3 — нет подтверждения, рано повторять или файл отметки повреждён.
"""

import argparse
import asyncio
import io
import math
import sys
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import httpx

from app.config import Settings, get_settings

EXIT_OK: Final = 0
EXIT_ERROR: Final = 1
EXIT_REFUSED: Final = 3
_MIN_INTERVAL_SECONDS: Final = 300
_STAMP_NAME: Final = ".hh_token_last_request"

_CONFIRM_WARNING = (
    "Повторный POST /token отзывает текущий токен приложения: "
    "старый HH_APP_TOKEN перестанет работать, токен будет отозван. "
    "Запрос не чаще одного раза в 5 минут. "
    "Чтобы выполнить запрос, повторите команду с --yes."
)
_SAVE_HINT = "Положите значение в HH_APP_TOKEN сами. Скрипт файл .env не менял."


class HHTokenScriptError(Exception):
    """Ошибка скрипта. Это не ошибка API и не повод повторять POST."""

    def __init__(self, message: str, *, exit_code: int) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code


def default_stamp_path() -> Path:
    """``vacancies-service/.hh_token_last_request`` — одна строка ISO UTC."""
    return Path(__file__).resolve().parent.parent / _STAMP_NAME


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.hh_token",
        description=(
            "Exchange hh client credentials for an application access token. "
            "A repeat revokes the current token."
        ),
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm POST /token; a repeat revokes the current application token",
    )
    return parser


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _require_credentials(settings: Settings) -> tuple[str, str, str]:
    client_id = settings.hh_client_id
    client_secret = settings.hh_client_secret
    user_agent = settings.hh_user_agent
    if client_id is None or client_secret is None or user_agent is None:
        raise HHTokenScriptError(
            "HH_CLIENT_ID, HH_CLIENT_SECRET and HH_USER_AGENT are required",
            exit_code=EXIT_ERROR,
        )
    return client_id.get_secret_value(), client_secret.get_secret_value(), user_agent


def _broken_stamp(path: Path) -> HHTokenScriptError:
    return HHTokenScriptError(
        f"Файл отметки повреждён ({path}). Удалите его вручную.",
        exit_code=EXIT_REFUSED,
    )


def _load_stamp(path: Path) -> datetime | None:
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise _broken_stamp(path) from None
    try:
        parsed = datetime.fromisoformat(raw.strip())
    except ValueError:
        raise _broken_stamp(path) from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _broken_stamp(path)
    return parsed.astimezone(UTC)


def _store_stamp(path: Path, moment: datetime) -> None:
    path.write_text(_as_utc(moment).isoformat() + "\n", encoding="utf-8")


def _ensure_interval(stamped: datetime, current: datetime) -> None:
    elapsed = (current - stamped).total_seconds()
    if elapsed >= _MIN_INTERVAL_SECONDS:
        return
    remaining = math.ceil(_MIN_INTERVAL_SECONDS - elapsed)
    raise HHTokenScriptError(
        f"Повтор возможен через {remaining} с. Запрос не чаще одного раза в 5 минут.",
        exit_code=EXIT_REFUSED,
    )


def _access_token(response: httpx.Response) -> str:
    if response.status_code != 200:
        raise HHTokenScriptError(
            f"hh token request failed with status {response.status_code}",
            exit_code=EXIT_ERROR,
        )
    try:
        payload = response.json()
    except (ValueError, UnicodeDecodeError):
        raise HHTokenScriptError("hh token response is not JSON", exit_code=EXIT_ERROR) from None
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token.strip():
        raise HHTokenScriptError(
            "hh token response has no access_token",
            exit_code=EXIT_ERROR,
        )
    return token


async def _post_token(
    *,
    settings: Settings,
    transport: httpx.AsyncBaseTransport | None,
    client_id: str,
    client_secret: str,
    user_agent: str,
) -> str:
    url = f"{settings.hh_base_url.rstrip('/')}/token"
    try:
        async with httpx.AsyncClient(
            timeout=settings.hh_timeout_seconds,
            transport=transport,
            follow_redirects=False,
        ) as client:
            response = await client.post(
                url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={
                    "HH-User-Agent": user_agent,
                    "User-Agent": user_agent,
                },
            )
    except httpx.RequestError:
        raise HHTokenScriptError("hh token request failed", exit_code=EXIT_ERROR) from None
    return _access_token(response)


async def request_application_token(
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    stamp_path: Path | None = None,
    now: Callable[[], datetime] | None = None,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> str:
    """Один POST /token. Отметка пишется до запроса, в том числе если hh ответит ошибкой.

    ``sleep`` тесты могут подменить. Повторов нет, и скрипт его не вызывает:
    ограничение в 5 минут — это файл отметки, а не пауза.
    """
    del sleep
    client_id, client_secret, user_agent = _require_credentials(settings)
    path = default_stamp_path() if stamp_path is None else stamp_path
    current = _as_utc(datetime.now(UTC) if now is None else now())
    stamped = await asyncio.to_thread(_load_stamp, path)
    if stamped is not None:
        _ensure_interval(stamped, current)
    try:
        await asyncio.to_thread(_store_stamp, path, current)
    except OSError:
        raise HHTokenScriptError(
            "cannot write the hh token request stamp",
            exit_code=EXIT_ERROR,
        ) from None
    return await _post_token(
        settings=settings,
        transport=transport,
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Прочитать аргументы и, если есть ``--yes``, запросить токен."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="backslashreplace")
    args = build_parser().parse_args(argv)
    if not args.yes:
        print(_CONFIRM_WARNING, file=sys.stderr)
        return EXIT_REFUSED
    try:
        token = asyncio.run(request_application_token(get_settings()))
    except HHTokenScriptError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return exc.exit_code
    print(token)
    print(_SAVE_HINT, file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
