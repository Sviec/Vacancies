"""CLI сида демо-данных (этап 7).

Запуск из `vacancies-service/`:
    python -m scripts.seed [--dry-run] [--reset --yes] [--now ISO] [--no-actions]
                           [--no-score-check] [--preview N]

Коды выхода: 0 — успех; 1 — ошибка данных, ingest или БД; 2 — оценка эталонного
резюме вне диапазона; 3 — отказ до соединения с БД (prod или неподтверждённый --reset).
"""

import argparse
import asyncio
import io
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Final

from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.config import Settings, get_settings
from app.db.session import dispose_engine, get_sessionmaker, init_engine
from app.services.seed import EXIT_DATA_ERROR, SeedError, SeedOptions, format_report, run_seed
from app.services.seed_data import load_seed_dataset
from app.utils.logging import configure_logging

EXIT_OK: Final = 0
EXIT_REFUSED: Final = 3


def parse_now(value: str) -> datetime:
    """ISO 8601 с таймзоной, не в будущем."""
    # TODO: --now в будущем и без таймзоны запрещён.
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        msg = f"invalid ISO 8601 datetime: {value!r}"
        raise argparse.ArgumentTypeError(msg) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        msg = f"--now must include a timezone offset, got {value!r}"
        raise argparse.ArgumentTypeError(msg)
    if parsed > datetime.now(UTC):
        msg = f"--now must not be in the future, got {value!r}"
        raise argparse.ArgumentTypeError(msg)
    return parsed


def _non_negative(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        msg = f"expected a non-negative integer, got {value!r}"
        raise argparse.ArgumentTypeError(msg) from exc
    if number < 0:
        msg = f"expected a non-negative integer, got {value!r}"
        raise argparse.ArgumentTypeError(msg)
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.seed",
        description="Seed demo sources, parse runs, vacancies, resumes and user actions.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete the whole vacancy domain and demo user's resumes before seeding",
    )
    parser.add_argument("--yes", action="store_true", help="confirm --reset without a prompt")
    parser.add_argument(
        "--dry-run", action="store_true", help="run everything and roll the transaction back"
    )
    parser.add_argument(
        "--now",
        type=parse_now,
        default=None,
        help="reference time (ISO 8601 with timezone); default: current UTC time",
    )
    parser.add_argument("--no-actions", action="store_true", help="do not seed user actions")
    parser.add_argument(
        "--no-score-check",
        action="store_true",
        help="do not fail when a demo resume score is out of the expected range",
    )
    parser.add_argument(
        "--preview",
        type=_non_negative,
        default=3,
        help="number of top recommendations per resume in the report (0 disables)",
    )
    return parser


def confirm_reset(
    database: str,
    *,
    assume_yes: bool,
    stdin_is_tty: bool,
    read: Callable[[str], str] = input,
) -> bool:
    """--yes подтверждает сразу; в TTY нужно ввести имя БД; без TTY — отказ."""
    if assume_yes:
        return True
    if not stdin_is_tty:
        return False
    try:
        answer = read(f"Type the database name ({database}) to confirm --reset: ")
    except EOFError:
        return False
    return answer.strip() == database


def _error(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)


async def amain(args: argparse.Namespace, settings: Settings) -> int:
    # TODO: в ENVIRONMENT=prod сид запрещён целиком, флага обхода нет.
    if settings.environment == "prod":
        _error("seeding is disabled in ENVIRONMENT=prod")
        return EXIT_REFUSED

    url = make_url(settings.database_url)
    now: datetime = args.now if args.now is not None else datetime.now(UTC).replace(microsecond=0)
    mode = "dry-run (rollback)" if args.dry_run else "commit"
    print(f"target: {url.render_as_string(hide_password=True)}")
    print(f"now: {now.isoformat()}  mode: {mode}  reset: {args.reset}")

    if args.reset and not confirm_reset(
        url.database or "", assume_yes=args.yes, stdin_is_tty=sys.stdin.isatty()
    ):
        _error("--reset was not confirmed (use --yes or type the database name in a terminal)")
        return EXIT_REFUSED

    try:
        dataset = load_seed_dataset()
    except (OSError, ValueError) as exc:
        _error(f"invalid seed data: {exc}")
        return EXIT_DATA_ERROR

    options = SeedOptions(
        now=now,
        user_id=settings.demo_user_id,
        reset=args.reset,
        with_actions=not args.no_actions,
        check_scores=not args.no_score_check,
        preview_top=args.preview,
    )
    init_engine(settings)
    try:
        async with get_sessionmaker()() as session:
            try:
                report = await run_seed(session, options, dataset=dataset)
            except BaseException:
                await session.rollback()
                raise
            if args.dry_run:
                await session.rollback()
            else:
                await session.commit()
    except SeedError as exc:
        _error(exc.message)
        for detail in exc.details:
            print(f"  {detail}", file=sys.stderr)
        return exc.exit_code
    except ProgrammingError as exc:
        _error(f"database schema is missing or outdated: {exc.orig}")
        print(
            "  hint: run `alembic upgrade head` first (in Docker: the `migrate` service)",
            file=sys.stderr,
        )
        return EXIT_DATA_ERROR
    except (DBAPIError, OSError) as exc:
        _error(f"database error: {exc}")
        return EXIT_DATA_ERROR
    except ValueError as exc:
        _error(f"invalid seed data: {exc}")
        return EXIT_DATA_ERROR
    finally:
        await dispose_engine()

    print(format_report(report))
    if args.dry_run:
        print("dry-run: transaction rolled back, nothing was written")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    # Отчёт содержит кириллицу и эмодзи из данных: консоль Windows (cp1251/cp866)
    # не должна падать на них.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="backslashreplace")
    args = build_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings)
    return asyncio.run(amain(args, settings))


if __name__ == "__main__":
    raise SystemExit(main())
