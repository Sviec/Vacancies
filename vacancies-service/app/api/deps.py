"""Общие FastAPI-зависимости слоя API."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

from app.adapters.llm import LLMAdapter, build_llm_adapter
from app.adapters.profile import ProfileAdapter, build_profile_adapter
from app.config import Settings, get_settings
from app.db.session import SessionDep
from app.services import auth
from app.utils.errors import UnauthenticatedError


async def get_current_user_id(request: Request, session: SessionDep) -> UUID:
    """Идентификатор текущего пользователя по куке сессии.

    Сервисы по-прежнему получают `user_id` параметром. Нет куки или сессия
    просрочена — 401, общего демо-пользователя больше нет.
    """
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise UnauthenticatedError()
    user_id = await auth.user_id_for_token(session, token, now=datetime.now(UTC))
    if user_id is None:
        await session.commit()
        raise UnauthenticatedError()
    return user_id


def get_llm_adapter(settings: Annotated[Settings, Depends(get_settings)]) -> LLMAdapter:
    """LLM-адаптер по `llm_mode`. Роуты резюме получают его через `LLMAdapterDep`."""
    return build_llm_adapter(settings)


def get_profile_adapter(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProfileAdapter:
    """Profile-адаптер по `profile_mode`. На этапе 9 ни один роут его не вызывает."""
    return build_profile_adapter(settings)


CurrentUserDep = Annotated[UUID, Depends(get_current_user_id)]
LLMAdapterDep = Annotated[LLMAdapter, Depends(get_llm_adapter)]
ProfileAdapterDep = Annotated[ProfileAdapter, Depends(get_profile_adapter)]
