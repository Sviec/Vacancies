"""POST /sources/{id}/run без Postgres и Redis: сессия и enqueue подменены."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.api.v1 import sources as sources_api
from app.config import Settings
from app.db.models import Source
from app.db.session import get_session
from app.enums import SourceType
from app.utils.errors import SourceAlreadyRunningError


class _FakeSession:
    def __init__(self, source: Source | None) -> None:
        self.source = source

    async def get(self, _model: object, _ident: object) -> Source | None:
        return self.source


class _Redis:
    def close(self) -> None:
        return None


def _source(**overrides: object) -> Source:
    data: dict[str, Any] = {
        "id": uuid.uuid4(),
        "slug": "html_live",
        "source_type": SourceType.HTML,
        "config": {"url": "https://jobs.example.org/it", "list_selector": "div"},
        "is_enabled": True,
    }
    data.update(overrides)
    return Source(**data)


def _bind(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    source: Source | None,
    *,
    parsers_enabled: bool,
) -> list[Source]:
    async def _session() -> AsyncIterator[_FakeSession]:
        yield _FakeSession(source)

    app.dependency_overrides[get_session] = _session
    monkeypatch.setattr(
        sources_api,
        "get_settings",
        lambda: Settings(_env_file=None, parsers_enabled=parsers_enabled),
    )
    enqueued: list[Source] = []

    def _enqueue(item: Source, _settings: Settings, _connection: object) -> str:
        enqueued.append(item)
        return "job-1"

    monkeypatch.setattr(sources_api, "enqueue_manual_run", _enqueue)
    monkeypatch.setattr(sources_api.redis.Redis, "from_url", _redis_must_not_be_called)
    return enqueued


def _redis_must_not_be_called(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("redis")


def _allow_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sources_api.redis.Redis, "from_url", lambda *_a, **_k: _Redis())


async def test_demo_is_409_even_when_parsers_disabled(
    app: FastAPI, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(config={"demo": True})
    enqueued = _bind(app, monkeypatch, source, parsers_enabled=False)
    response = await client.post(f"/api/v1/sources/{source.id}/run")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DEMO_SOURCE"
    assert enqueued == []


async def test_parsers_disabled(
    app: FastAPI, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source()
    enqueued = _bind(app, monkeypatch, source, parsers_enabled=False)
    response = await client.post(f"/api/v1/sources/{source.id}/run")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PARSERS_DISABLED"
    assert enqueued == []


async def test_source_disabled(
    app: FastAPI, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(is_enabled=False)
    enqueued = _bind(app, monkeypatch, source, parsers_enabled=True)
    response = await client.post(f"/api/v1/sources/{source.id}/run")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SOURCE_DISABLED"
    assert enqueued == []


async def test_unknown_source_is_404(
    app: FastAPI, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    enqueued = _bind(app, monkeypatch, None, parsers_enabled=True)
    response = await client.post(f"/api/v1/sources/{uuid.uuid4()}/run")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert enqueued == []


async def test_api_source_is_not_runnable(
    app: FastAPI, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(source_type=SourceType.API, slug="api_vendor", config={"url": "https://api"})
    enqueued = _bind(app, monkeypatch, source, parsers_enabled=True)
    response = await client.post(f"/api/v1/sources/{source.id}/run")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SOURCE_NOT_RUNNABLE"
    assert enqueued == []


async def test_already_running(
    app: FastAPI, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source()
    _bind(app, monkeypatch, source, parsers_enabled=True)
    _allow_redis(monkeypatch)

    def _busy(_source: Source, _settings: Settings, _connection: object) -> str:
        raise SourceAlreadyRunningError(details={"source_id": str(source.id), "slug": source.slug})

    monkeypatch.setattr(sources_api, "enqueue_manual_run", _busy)
    response = await client.post(f"/api/v1/sources/{source.id}/run")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SOURCE_ALREADY_RUNNING"


async def test_enqueue_returns_202(
    app: FastAPI, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source()
    enqueued = _bind(app, monkeypatch, source, parsers_enabled=True)
    _allow_redis(monkeypatch)
    response = await client.post(f"/api/v1/sources/{source.id}/run")
    assert response.status_code == 202
    assert response.json() == {"source_id": str(source.id), "job_id": "job-1"}
    assert enqueued == [source]
