"""Общие типы и хелперы Pydantic-схем (пагинация, ошибки, денежные поля)."""

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

# ISO-4217: ровно три заглавные латинские буквы (RUB, USD, EUR).
CurrencyCode = Annotated[str, Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")]

# sha256 в hex lowercase — 64 символа [0-9a-f]. Формулу хеша считает нормализатор
# (этап 4); здесь только формат.
ContentHashHex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

PageNumber = Annotated[int, Field(default=1, ge=1)]
PageSize = Annotated[int, Field(default=20, ge=1, le=100)]


class VacancySort(StrEnum):
    """Сортировка ленты вакансий (п. 5.5 ТЗ). Живёт только в схемах, не в app.enums."""

    RELEVANCE = "relevance"
    DATE = "date"
    SALARY = "salary"


def validate_salary_range(salary_min: int | None, salary_max: int | None) -> None:
    """Если оба края вилки заданы — нижний не больше верхнего."""
    if salary_min is not None and salary_max is not None and salary_min > salary_max:
        msg = "salary_min must be less than or equal to salary_max"
        raise ValueError(msg)


class PaginatedResponse[T](BaseModel):
    """Универсальный конверт постраничной выдачи."""

    items: list[T]
    total: int = Field(ge=0)
    page: int
    page_size: int


class ErrorDetail(BaseModel):
    """Тело ошибки внутри конверта раздела 6 ТЗ."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Зеркало `{"error": {"code", "message", "details"}}` из app.utils.errors."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorDetail
