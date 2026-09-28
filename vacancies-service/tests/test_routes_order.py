"""Порядок маршрутов: статические пути вакансий матчатся раньше `/{vacancy_id}`."""

import ast
import inspect
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.routing import APIRoute
from httpx import AsyncClient

from app.api.v1 import router as router_module
from app.api.v1 import vacancies
from app.db.session import get_session
from app.utils.errors import DependencyUnavailableError


class _ExplodingSession:
    """Сессия-заглушка: любой запрос к БД — ошибка (значит, до БД дошли)."""

    async def execute(self, *_args: object, **_kwargs: object) -> None:
        raise DependencyUnavailableError


async def _exploding_session() -> AsyncIterator[_ExplodingSession]:
    yield _ExplodingSession()


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


def test_recommendations_router_included_before_vacancies() -> None:
    # У recommendations.router до этапа 6 нет маршрутов, поэтому порядок
    # проверяется по вызовам `api_router.include_router(<module>.router)`.
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
