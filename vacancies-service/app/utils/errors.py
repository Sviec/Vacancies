"""Доменные исключения и единый формат ошибок API (раздел 6 ТЗ).

Поле `message` — на английском: API считается техническим интерфейсом,
локализация выполняется на фронтенде по полю `code`.
"""

from typing import Any, ClassVar


class AppError(Exception):
    """Базовая ошибка приложения, отображаемая в конверт `{"error": {...}}`."""

    code: ClassVar[str] = "INTERNAL_ERROR"
    http_status: ClassVar[int] = 500
    default_message: ClassVar[str] = "Internal service error"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.default_message
        # details всегда dict, никогда None: сериализуется как {}, не как null.
        self.details: dict[str, Any] = details or {}
        super().__init__(self.message)


class NotFoundError(AppError):
    """Запрошенный ресурс не существует."""

    code: ClassVar[str] = "NOT_FOUND"
    http_status: ClassVar[int] = 404
    default_message: ClassVar[str] = "Requested resource was not found"


class DomainValidationError(AppError):
    """Нарушено бизнес-правило.

    Имя отличается от `pydantic.ValidationError`, чтобы их нельзя было спутать
    при импорте в одном модуле.
    """

    code: ClassVar[str] = "VALIDATION_ERROR"
    http_status: ClassVar[int] = 422
    default_message: ClassVar[str] = "Request data is invalid"


class ConflictError(AppError):
    """Операция конфликтует с текущим состоянием ресурса."""

    code: ClassVar[str] = "CONFLICT"
    http_status: ClassVar[int] = 409
    default_message: ClassVar[str] = "Operation conflicts with the current state"


class DemoSourceError(ConflictError):
    """Демо-источник сида не обходится ни вручную, ни планировщиком."""

    code: ClassVar[str] = "DEMO_SOURCE"
    default_message: ClassVar[str] = "Demo source is not crawled"


class ParsersDisabledError(ConflictError):
    """PARSERS_ENABLED=false: наружу не ходим и задачи не ставим."""

    code: ClassVar[str] = "PARSERS_DISABLED"
    default_message: ClassVar[str] = "Parsers are disabled"


class SourceDisabledError(ConflictError):
    """Источник выключен (`is_enabled` ложен)."""

    code: ClassVar[str] = "SOURCE_DISABLED"
    default_message: ClassVar[str] = "Source is disabled"


class SourceNotRunnableError(ConflictError):
    """Для типа источника нет зарегистрированного парсера."""

    code: ClassVar[str] = "SOURCE_NOT_RUNNABLE"
    default_message: ClassVar[str] = "Source type has no parser"


class SourceAlreadyRunningError(ConflictError):
    """По источнику уже есть активная задача обхода."""

    code: ClassVar[str] = "SOURCE_ALREADY_RUNNING"
    default_message: ClassVar[str] = "A parse job for this source is already running"


class RateLimitedError(AppError):
    """Превышен лимит обращений (свой или внешнего источника)."""

    code: ClassVar[str] = "RATE_LIMITED"
    http_status: ClassVar[int] = 429
    default_message: ClassVar[str] = "Too many requests, please retry later"


class ExternalServiceError(AppError):
    """Внешняя система вернула ошибку или недоступна."""

    code: ClassVar[str] = "EXTERNAL_SERVICE_ERROR"
    http_status: ClassVar[int] = 502
    default_message: ClassVar[str] = "External service call failed"


class LLMResponseInvalidError(ExternalServiceError):
    """LLM вернула ответ, не проходящий валидацию схемы (п. 5.3 ТЗ)."""

    code: ClassVar[str] = "LLM_RESPONSE_INVALID"
    http_status: ClassVar[int] = 502
    default_message: ClassVar[str] = "LLM returned a response that failed validation"


class ParseFailedError(ExternalServiceError):
    """Источник вакансий не удалось распарсить (раздел 5.1 ТЗ)."""

    code: ClassVar[str] = "PARSE_FAILED"
    http_status: ClassVar[int] = 502
    default_message: ClassVar[str] = "Source parsing failed"


class DependencyUnavailableError(AppError):
    """Инфраструктурная зависимость (БД, Redis) недоступна."""

    code: ClassVar[str] = "DEPENDENCY_UNAVAILABLE"
    http_status: ClassVar[int] = 503
    default_message: ClassVar[str] = "A required dependency is unavailable"


# Соответствие HTTP-статусов кодам ошибок для starlette.HTTPException,
# у которого нет собственного кода (в т.ч. автоматический 404 на неизвестный маршрут).
HTTP_STATUS_TO_CODE: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    503: "DEPENDENCY_UNAVAILABLE",
}

HTTP_ERROR_FALLBACK_CODE = "HTTP_ERROR"


def build_error_payload(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Собрать тело ошибки строго в формате раздела 6 ТЗ."""
    return {"error": {"code": code, "message": message, "details": details or {}}}
