"""GET /sources и /sources/runs на данных сида (этап 8)."""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("seeded")]

SOURCES = "/api/v1/sources"
RUNS = "/api/v1/sources/runs"

EXPECTED_COUNTERS = {
    "html_careerhub": (8, 8),
    "html_jobboard": (0, 0),
    "tg_it_jobs": (17, 4),
    "tg_relocate_remote": (18, 0),
}
EXPECTED_LOCATIONS = {
    "html_careerhub": "https://careers.example.com/vacancies",
    "html_jobboard": "https://jobs.example.org/it",
    "tg_it_jobs": "@demo_it_jobs",
    "tg_relocate_remote": "@demo_relocate_jobs",
}
FORBIDDEN_KEYS = ("config", "list_selector", "fields")


async def _sources(client: AsyncClient) -> list[dict[str, Any]]:
    response = await client.get(SOURCES)
    assert response.status_code == 200, response.text
    for key in FORBIDDEN_KEYS:
        assert key not in response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


async def _runs(client: AsyncClient, **params: Any) -> list[dict[str, Any]]:
    response = await client.get(RUNS, params=params)
    assert response.status_code == 200, response.text
    for key in FORBIDDEN_KEYS:
        assert key not in response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


async def test_sources_list(api_client: AsyncClient) -> None:
    items = await _sources(api_client)
    assert [item["slug"] for item in items] == sorted(EXPECTED_COUNTERS)
    by_slug = {item["slug"]: item for item in items}
    for slug, (found, new) in EXPECTED_COUNTERS.items():
        item = by_slug[slug]
        assert (item["last_run_items_found"], item["last_run_items_new"]) == (found, new), slug
        assert item["location"] == EXPECTED_LOCATIONS[slug]

    failed = by_slug["html_jobboard"]
    assert failed["last_run_status"] == "failed"
    assert failed["last_error"]
    assert all(
        by_slug[s]["last_run_status"] == "success"
        for s in EXPECTED_COUNTERS
        if s != "html_jobboard"
    )


async def test_runs_list_and_filters(api_client: AsyncClient) -> None:
    runs = await _runs(api_client)
    assert len(runs) == 11
    started = [run["started_at"] for run in runs]
    assert started == sorted(started, reverse=True)

    by_slug = {item["slug"]: item["id"] for item in await _sources(api_client)}
    tg_runs = await _runs(api_client, source_id=by_slug["tg_it_jobs"])
    assert len(tg_runs) == 3
    assert {run["source_id"] for run in tg_runs} == {by_slug["tg_it_jobs"]}

    failed = await _runs(api_client, status="failed")
    assert len(failed) == 1
    assert failed[0]["source_id"] == by_slug["html_jobboard"]
    assert failed[0]["error_text"]

    assert len(await _runs(api_client, limit=2)) == 2
    assert await _runs(api_client, source_id=str(uuid.uuid4())) == []


@pytest.mark.parametrize("params", [{"limit": 0}, {"source_id": "junk"}])
async def test_runs_bad_query(api_client: AsyncClient, params: dict[str, Any]) -> None:
    response = await api_client.get(RUNS, params=params)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert set(error) == {"code", "message", "details"}
