"""Планировщик обхода: отдельный процесс `python -m app.tasks.scheduler`.

# TODO: первый плановый запуск через один интервал, не в момент старта.
# Смена интервала требует рестарта процесса scheduler.
Воркер расписание не ведёт (`Worker.work(with_scheduler=False)`).
"""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import redis
from redis.exceptions import RedisError
from rq_scheduler import Scheduler
from sqlalchemy import select

from app.config import Settings, get_settings
from app.db.models import Source
from app.db.session import dispose_engine, get_sessionmaker, init_engine
from app.utils.logging import configure_logging, get_logger

if TYPE_CHECKING:
    from app.parsers.config import ScheduleSpec

logger = get_logger(__name__)

_PARSE_KIND = "parse_schedule"


def main() -> None:
    """Подключиться к Redis и либо ждать, либо поставить расписание и крутить scheduler.run()."""
    settings = get_settings()
    configure_logging(settings)
    idle = threading.Event()
    try:
        connection = redis.Redis.from_url(settings.redis_url)
        connection.ping()
        scheduler = Scheduler(queue_name=settings.rq_queue_name, connection=connection)
        _cancel_parse_schedules(scheduler)
    except (RedisError, OSError):
        logger.exception("scheduler_redis_unavailable")
        idle.wait()
        return

    if not settings.parsers_enabled:
        # Источники не читаем и наружу не ходим: демо живёт на сиде.
        logger.info("scheduler_idle", reason="parsers_disabled")
        idle.wait()
        return

    specs = asyncio.run(_load_schedules(settings))
    _install_schedules(scheduler, specs, settings)
    scheduler.run()


def _cancel_parse_schedules(scheduler: Scheduler) -> None:
    jobs = list(scheduler.get_jobs())
    for job in jobs:
        meta = job.meta or {}
        if meta.get("kind") != _PARSE_KIND:
            continue
        scheduler.cancel(job)
        job.delete()


async def _load_schedules(settings: Settings) -> list[ScheduleSpec]:
    # Регистрация классов только здесь: при выключенных парсерах Telethon не импортируется.
    import app.parsers
    from app.parsers.config import schedules_for

    _ = (app.parsers.HtmlParser, app.parsers.TelegramParser)
    init_engine(settings)
    try:
        session_factory = get_sessionmaker()
        async with session_factory() as session:
            rows = list((await session.scalars(select(Source))).all())
            return schedules_for(rows, settings)
    finally:
        await dispose_engine()


def _install_schedules(scheduler: Scheduler, specs: list[ScheduleSpec], settings: Settings) -> None:
    from app.tasks.parse_source import run_source

    now = datetime.now(UTC)
    for spec in specs:
        # Первый запуск — через интервал. Сразу стартует только ручной POST.
        scheduler.schedule(
            scheduled_time=now + timedelta(seconds=spec.interval_seconds),
            func=run_source,
            args=(str(spec.source_id),),
            interval=spec.interval_seconds,
            repeat=None,
            timeout=settings.rq_default_timeout,
            meta={"kind": _PARSE_KIND, "source_id": str(spec.source_id)},
        )
    logger.info("scheduler_planned", sources=len(specs))


if __name__ == "__main__":
    main()
