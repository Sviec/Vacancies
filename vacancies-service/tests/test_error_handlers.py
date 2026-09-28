"""Конверт ошибки для нарушения ограничения БД (`IntegrityError` → 409)."""

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError


async def test_integrity_error_is_conflict_without_sql(app: FastAPI, client: AsyncClient) -> None:
    async def _boom() -> None:
        raise IntegrityError(
            "INSERT INTO resumes ...", {}, Exception("uq_resumes_primary_per_user")
        )

    app.add_api_route("/_test/integrity", _boom)
    response = await client.get("/_test/integrity")
    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "CONFLICT",
            "message": "Operation conflicts with the current state",
            "details": {},
        }
    }
    assert "uq_resumes" not in response.text
