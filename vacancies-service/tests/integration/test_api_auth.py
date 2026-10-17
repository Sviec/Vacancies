"""Регистрация и кука сессии. Общий демо-пользователь больше не открывает API."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.api.deps import get_current_user_id

pytestmark = pytest.mark.integration

AUTH = "/api/v1/auth"
RESUMES = "/api/v1/resumes"


async def test_api_without_session_is_401(api_client: AsyncClient, app_for_db: FastAPI) -> None:
    app_for_db.dependency_overrides.pop(get_current_user_id)
    response = await api_client.get(RESUMES)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def test_register_login_and_logout(api_client: AsyncClient, app_for_db: FastAPI) -> None:
    app_for_db.dependency_overrides.pop(get_current_user_id)
    registered = await api_client.post(
        f"{AUTH}/register",
        json={"email": "New.User@Example.com", "password": "password1"},
    )
    assert registered.status_code == 201, registered.text
    body = registered.json()
    assert body["email"] == "new.user@example.com"
    assert "password" not in body
    assert api_client.cookies.get("session")

    resumes = await api_client.get(RESUMES)
    assert resumes.status_code == 200
    assert resumes.json()["items"] == []

    await api_client.post(f"{AUTH}/logout")
    assert api_client.cookies.get("session") is None
    assert (await api_client.get(RESUMES)).status_code == 401

    logged_in = await api_client.post(
        f"{AUTH}/login",
        json={"email": "new.user@example.com", "password": "password1"},
    )
    assert logged_in.status_code == 200
    me = await api_client.get(f"{AUTH}/me")
    assert me.status_code == 200
    assert me.json()["email"] == "new.user@example.com"


async def test_duplicate_email_is_409(api_client: AsyncClient, app_for_db: FastAPI) -> None:
    app_for_db.dependency_overrides.pop(get_current_user_id)
    payload = {"email": "twice@example.com", "password": "password1"}
    assert (await api_client.post(f"{AUTH}/register", json=payload)).status_code == 201
    again = await api_client.post(f"{AUTH}/register", json=payload)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "CONFLICT"


async def test_wrong_password_is_401(api_client: AsyncClient, app_for_db: FastAPI) -> None:
    app_for_db.dependency_overrides.pop(get_current_user_id)
    await api_client.post(
        f"{AUTH}/register",
        json={"email": "who@example.com", "password": "password1"},
    )
    response = await api_client.post(
        f"{AUTH}/login",
        json={"email": "who@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["details"] == {"reason": "invalid_credentials"}
