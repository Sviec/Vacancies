"""Обработчики исключений: любой ответ с ошибкой — конверт раздела 6 ТЗ."""

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.middleware import REQUEST_ID_HEADER, get_request_id
from app.utils.errors import (
    HTTP_ERROR_FALLBACK_CODE,
    HTTP_STATUS_TO_CODE,
    AppError,
    build_error_payload,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=build_error_payload(code, message, dict(details or {})),
        headers={REQUEST_ID_HEADER: get_request_id(request)},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Зарегистрировать все обработчики ошибок приложения."""

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        log = logger.warning if exc.http_status < 500 else logger.error
        log(
            "app_error",
            code=exc.code,
            status_code=exc.http_status,
            message=exc.message,
            details=exc.details,
        )
        return _error_response(
            request,
            exc.http_status,
            exc.code,
            exc.message,
            exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        # jsonable_encoder обязателен: в ctx ошибок pydantic лежат
        # несериализуемые объекты, без него обработчик сам упал бы с 500.
        errors = jsonable_encoder(exc.errors())
        logger.warning("request_validation_failed", errors=errors)
        return _error_response(
            request,
            422,
            "VALIDATION_ERROR",
            "Request validation failed",
            {"errors": errors},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        code = HTTP_STATUS_TO_CODE.get(exc.status_code, HTTP_ERROR_FALLBACK_CODE)
        logger.warning("http_exception", code=code, status_code=exc.status_code)
        return _error_response(request, exc.status_code, code, str(exc.detail), {})

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Stacktrace уходит только в лог: ни SQL, ни traceback не попадают в HTTP-ответ.
        logger.exception("unhandled_exception", error_type=type(exc).__name__)
        return _error_response(
            request,
            500,
            "INTERNAL_ERROR",
            "Internal service error",
            {},
        )
