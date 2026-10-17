"""Регистрация, вход и сессия. Сервис только flush-ит, коммит делает эндпоинт."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import AuthSession, User
from app.services.passwords import hash_password, verify_password
from app.utils.errors import ConflictError, UnauthenticatedError


def new_session_token() -> str:
    """Случайный токен для куки. В базу пишется только sha256."""
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def register_user(session: AsyncSession, email: str, password: str) -> User:
    """Создать пользователя. Занятая почта — 409."""
    user = User(email=email, password_hash=hash_password(password))
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(
            "An account with this email already exists",
            details={"field": "email"},
        ) from exc
    return user


async def authenticate(session: AsyncSession, email: str, password: str) -> User:
    """Проверить почту и пароль. Одинаковая ошибка, если пользователя нет или пароль неверный."""
    user = await session.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(password, user.password_hash):
        raise UnauthenticatedError(
            "Invalid email or password",
            details={"reason": "invalid_credentials"},
        )
    return user


async def open_session(session: AsyncSession, user_id: UUID, settings: Settings) -> str:
    """Создать сессию и вернуть сырой токен для куки."""
    token = new_session_token()
    row = AuthSession(
        user_id=user_id,
        token_hash=token_hash(token),
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.session_ttl_seconds),
    )
    session.add(row)
    await session.flush()
    return token


async def user_id_for_token(session: AsyncSession, token: str, *, now: datetime) -> UUID | None:
    """Найти живую сессию. Просроченную строку удалить."""
    digest = token_hash(token)
    row = await session.scalar(select(AuthSession).where(AuthSession.token_hash == digest))
    if row is None:
        return None
    if row.expires_at <= now:
        await session.delete(row)
        await session.flush()
        return None
    return row.user_id


async def drop_session(session: AsyncSession, token: str) -> None:
    await session.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash(token)))
    await session.flush()


async def find_user_id_by_email(session: AsyncSession, email: str) -> UUID | None:
    user_id = await session.scalar(select(User.id).where(User.email == email.strip().lower()))
    return user_id if isinstance(user_id, UUID) else None
