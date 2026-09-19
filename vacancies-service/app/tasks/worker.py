"""Точка входа RQ-воркера: `python -m app.tasks.worker`.

# TODO: RQ использует fork, поэтому воркер работает только в Docker/Linux;
# локально на Windows он не запускается.

Задачи здесь не регистрируются — они появятся на этапе 11 вместе с
`app/tasks/queue.py` и планировщиком.
"""

import redis
from rq import Queue, Worker

from app.config import get_settings
from app.utils.logging import configure_logging, get_logger

logger = get_logger(__name__)


def main() -> None:
    """Запустить воркер на очереди из конфига."""
    settings = get_settings()
    configure_logging(settings)
    # СИНХРОННЫЙ клиент: RQ не умеет async (см. комментарий в app/db/redis.py).
    connection = redis.Redis.from_url(settings.redis_url)
    queue = Queue(
        settings.rq_queue_name,
        connection=connection,
        default_timeout=settings.rq_default_timeout,
    )
    logger.info("worker_starting", queue=settings.rq_queue_name)
    # with_scheduler=False: на этапе 1 планировать нечего.
    Worker([queue], connection=connection).work(with_scheduler=False)


if __name__ == "__main__":
    main()
