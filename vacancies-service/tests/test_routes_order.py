"""Порядок маршрутов: статические пути вакансий матчатся раньше `/{vacancy_id}`."""

import ast
import inspect
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.routing import APIRoute
from httpx import AsyncClient

from app.api.v1 import resumes, vacancies
from app.api.v1 import router as router_module
from app.db.session import get_session
from app.utils.errors import DependencyUnavailableError


class _ExplodingSession:
    """Сессия-заглушка: любой запрос к БД — ошибка (значит, до БД дошли)."""

    async def execute(self, *_args: object, **_kwargs: object) -> None:
        raise DependencyUnavailableError


async def _exploding_session() -> AsyncIterator[_ExplodingSession]:
    yield _ExplodingSession()


def test_generate_declared_before_resume_id() -> None:
    paths = [route.path for route in resumes.router.routes if isinstance(route, APIRoute)]
    assert paths.index("/resumes/generate") < paths.index("/resumes/{resume_id}")


async def test_generate_validates_body_before_db(app: FastAPI, client: AsyncClient) -> None:
    app.dependency_overrides[get_session] = _exploding_session
    response = await client.post("/api/v1/resumes/generate", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_filters_meta_declared_before_vacancy_id() -> None:
    paths = [route.path for route in vacancies.router.routes if isinstance(route, APIRoute)]
    assert paths.index("/vacancies/filters/meta") < paths.index("/vacancies/{vacancy_id}")


async def test_filters_meta_is_not_captured_by_vacancy_id(
    app: FastAPI, client: AsyncClient
) -> None:
    app.dependency_overrides[get_session] = _exploding_session
    # Маршрут `/{vacancy_id}` ответил бы 422 (не UUID) ещё до обращения к БД.
    meta = await client.get("/api/v1/vacancies/filters/meta")
    assert meta.status_code == 503
    assert meta.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    by_id = await client.get("/api/v1/vacancies/not-a-uuid")
    assert by_id.status_code == 422


async def test_recommended_is_not_captured_by_vacancy_id(app: FastAPI, client: AsyncClient) -> None:
    app.dependency_overrides[get_session] = _exploding_session
    # 503 означает, что запрос дошёл до сервиса рекомендаций, а не упал на
    # разборе "recommended" как UUID в `/{vacancy_id}` (422).
    response = await client.get("/api/v1/vacancies/recommended")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"


async def test_recommended_validates_query_before_db(app: FastAPI, client: AsyncClient) -> None:
    app.dependency_overrides[get_session] = _exploding_session
    for query in ("limit=0", "limit=201", "resume_id=not-a-uuid", "page=1"):
        response = await client.get(f"/api/v1/vacancies/recommended?{query}")
        assert response.status_code == 422, query
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_sources_runs_route_exists(app: FastAPI, client: AsyncClient) -> None:
    app.dependency_overrides[get_session] = _exploding_session
    # 503 — запрос дошёл до сервиса источников (не 404 и не 405).
    for path in ("/api/v1/sources", "/api/v1/sources/runs"):
        response = await client.get(path)
        assert response.status_code == 503, path
        assert response.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"


async def test_sources_runs_validates_query_before_db(app: FastAPI, client: AsyncClient) -> None:
    app.dependency_overrides[get_session] = _exploding_session
    for query in ("limit=0", "limit=201", "source_id=junk", "status=unknown", "page=1"):
        response = await client.get(f"/api/v1/sources/runs?{query}")
        assert response.status_code == 422, query
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_sort_match_without_resume_is_422(app: FastAPI, client: AsyncClient) -> None:
    app.dependency_overrides[get_session] = _exploding_session
    response = await client.get("/api/v1/vacancies?sort=match")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_recommendations_router_included_before_vacancies() -> None:
    # Порядок проверяется по вызовам `api_router.include_router(<module>.router)`.
    tree = ast.parse(inspect.getsource(router_module))
    included = [
        node.args[0].value.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "include_router"
        and isinstance(node.args[0], ast.Attribute)
        and isinstance(node.args[0].value, ast.Name)
    ]
    assert included.index("recommendations") < included.index("vacancies")
