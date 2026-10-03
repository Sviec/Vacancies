"""Общие FastAPI-зависимости слоя API."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends

from app.adapters.llm import LLMAdapter, build_llm_adapter
from app.adapters.profile import ProfileAdapter, build_profile_adapter
from app.config import Settings, get_settings


def get_current_user_id() -> UUID:
    """Идентификатор текущего пользователя.

    Авторизации нет (п. 0.2 ТЗ): всегда `DEMO_USER_ID` из конфига. Сервисы
    получают `user_id` только параметром, поэтому подменить источник можно
    в одном месте.
    """
    # TODO: будущий auth заменяет только тело этой функции (разбор токена).
    return get_settings().demo_user_id


def get_llm_adapter(settings: Annotated[Settings, Depends(get_settings)]) -> LLMAdapter:
    """LLM-адаптер по `llm_mode`. На этапе 9 ни один роут его не вызывает."""
    return build_llm_adapter(settings)


def get_profile_adapter(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProfileAdapter:
    """Profile-адаптер по `profile_mode`. На этапе 9 ни один роут его не вызывает."""
    return build_profile_adapter(settings)


CurrentUserDep = Annotated[UUID, Depends(get_current_user_id)]
LLMAdapterDep = Annotated[LLMAdapter, Depends(get_llm_adapter)]
ProfileAdapterDep = Annotated[ProfileAdapter, Depends(get_profile_adapter)]
