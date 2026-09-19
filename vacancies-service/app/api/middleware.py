"""Middleware: request-id, контекст логирования и access-лог."""

import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.utils.logging import get_logger

REQUEST_ID_HEADER = "X-Request-ID"

logger = get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Привязывает request_id к контексту логов и пишет одну строку на запрос."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid4().hex
        request.state.request_id = request_id

        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        started = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.info(
                "http_request",
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()


def get_request_id(request: Request) -> str:
    """Вернуть request_id запроса.

    Fallback нужен для случаев, когда middleware не успел сработать
    (например, исключение на уровне сервера до вхождения в стек).
    """
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str):
        return request_id
    return request.headers.get(REQUEST_ID_HEADER) or uuid4().hex
