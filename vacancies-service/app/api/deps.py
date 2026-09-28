"""Общие FastAPI-зависимости слоя API."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends

from app.config import get_settings


def get_current_user_id() -> UUID:
    """Идентификатор текущего пользователя.

    Авторизации нет (п. 0.2 ТЗ): всегда `DEMO_USER_ID` из конфига. Сервисы
    получают `user_id` только параметром, поэтому подменить источник можно
    в одном месте.
    """
    # TODO: будущий auth заменяет только тело этой функции (разбор токена).
    return get_settings().demo_user_id


CurrentUserDep = Annotated[UUID, Depends(get_current_user_id)]
