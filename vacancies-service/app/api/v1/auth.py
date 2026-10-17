"""Вход и регистрация. Сессия — httpOnly-кука, не тело ответа."""

from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response, status

from app.config import get_settings
from app.db.models import User
from app.db.session import SessionDep
from app.schemas.auth import AuthCredentials, UserRead
from app.services import auth
from app.utils.errors import UnauthenticatedError

router = APIRouter(prefix="/auth", tags=["auth"])


def _cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        max_age=settings.session_ttl_seconds,
        path="/",
    )


def _clear_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
    )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(body: AuthCredentials, session: SessionDep, response: Response) -> User:
    user = await auth.register_user(session, body.email, body.password)
    token = await auth.open_session(session, user.id, get_settings())
    await session.commit()
    _cookie(response, token)
    return user


@router.post("/login", response_model=UserRead)
async def login(body: AuthCredentials, session: SessionDep, response: Response) -> User:
    user = await auth.authenticate(session, body.email, body.password)
    token = await auth.open_session(session, user.id, get_settings())
    await session.commit()
    _cookie(response, token)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, session: SessionDep, response: Response) -> None:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        await auth.drop_session(session, token)
        await session.commit()
    _clear_cookie(response)


@router.get("/me", response_model=UserRead)
async def me(request: Request, session: SessionDep) -> User:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise UnauthenticatedError()
    user_id = await auth.user_id_for_token(session, token, now=datetime.now(UTC))
    if user_id is None:
        await session.commit()
        raise UnauthenticatedError()
    user = await session.get(User, user_id)
    if user is None:
        raise UnauthenticatedError()
    return user
