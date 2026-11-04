"""Обход hh без сети: MockTransport и Settings(_env_file=None)."""

import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

import app.parsers  # регистрация HTML и hh; сам обход ниже на MockTransport
from app.adapters.hh import HHClient
from app.config import Settings
from app.db.models import Source
from app.enums import SourceType
from app.parsers.api_providers import require_api_provider
from app.parsers.config import schedules_for
from app.parsers.hh_api import HHApiParser
from app.parsers.hh_card import build_area_index
from app.parsers.registry import build_parser
from app.services.parsing import perform_run
from app.utils.errors import ExternalServiceError, SourceNotRunnableError

_ = app.parsers.HtmlParser

_BASE = "https://hh.test"
NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
CURSOR = datetime(2026, 11, 4, 10, 15, tzinfo=UTC)
_AREAS = build_area_index([{"id": "113", "name": "Россия", "areas": []}])


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "hh_app_token": "test-app-token",
        "hh_user_agent": "hh-test-agent/1 (tester@example.com)",
        "hh_base_url": _BASE,
        "hh_request_delay_seconds": 0,
        "hh_timeout_seconds": 5,
        "hh_max_retries": 0,
        "parsers_enabled": True,
        "redis_url": "redis://localhost:6379/0",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def _forbid_http(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("HTTP client must not be created")


@pytest.fixture(autouse=True)
def _block_real_http(monkeypatch: pytest.MonkeyPatch) -> None:
    real_init = httpx.AsyncClient.__init__

    def guarded(self: httpx.AsyncClient, *args: object, **kwargs: object) -> None:
        if not isinstance(kwargs.get("transport"), httpx.MockTransport):
            raise AssertionError("real network is not allowed")
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", guarded)
    monkeypatch.setattr(httpx.Client, "__init__", _forbid_http)
    monkeypatch.setattr(HHClient, "__init__", _guard_hh_client(HHClient.__init__))


def _guard_hh_client(
    real_init: Callable[..., None],
) -> Callable[..., None]:
    def guarded(self: HHClient, *args: object, **kwargs: object) -> None:
        transport = kwargs.get("transport")
        if not isinstance(transport, httpx.MockTransport):
            raise AssertionError("HHClient requires MockTransport")
        real_init(self, *args, **kwargs)

    return guarded


def _json(status: int, payload: object) -> httpx.Response:
    return httpx.Response(status, json=payload)


def _search(found: int, items: list[object]) -> httpx.Response:
    return _json(200, {"found": found, "items": items})


def _card(external_id: str, name: str = "Специалист") -> dict[str, Any]:
    return {
        "id": external_id,
        "name": name,
        "alternate_url": f"https://hh.ru/vacancy/{external_id}",
        "employer": {"id": "5", "name": "Acme"},
        "published_at": "2026-10-28T15:04:05+0300",
        "description": "<p>Python</p>",
        "experience": {"id": "between3And6"},
        "work_format": [],
    }


def _hit(
    external_id: object,
    *,
    name: str = "Специалист",
    published_at: str | None = "2026-11-01T10:00:00+0000",
    salary_range: object = None,
    employer: object | None = None,
) -> dict[str, Any]:
    return {
        "id": external_id,
        "name": name,
        "published_at": published_at,
        "salary_range": salary_range,
        "employer": {"id": "5", "name": "Acme"} if employer is None else employer,
    }


def _known(
    name: str = "Специалист",
    *,
    salary_range: object = None,
    employer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "salary_range": salary_range,
        "employer": {"id": "5", "name": "Acme"} if employer is None else employer,
    }


class _Script:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = list(responses)
        self.seen: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        assert request.url.host == "hh.test"
        assert request.url.host != "api.hh.ru"
        self.seen.append(request)
        if not self.responses:
            raise AssertionError(request.url.path)
        return self.responses.pop(0)


def _parser(
    script: _Script | None = None,
    *,
    config: dict[str, Any] | None = None,
    areas: object = _AREAS,
    redis_factory: Callable[[str], Any] | None = None,
    **settings: object,
) -> HHApiParser:
    body = {
        "provider": "hh",
        "query": {"text": "python"},
        "backfill_days": 7,
        "max_vacancies_per_run": 400,
    }
    if config is not None:
        body.update(config)

    def _redis_must_not_be_called(url: str) -> Any:
        raise AssertionError(url)

    kwargs: dict[str, Any] = {
        "slug": "hh_it",
        "config": body,
        "settings": _settings(**settings),
        "sleep": _no_sleep,
        "redis_factory": redis_factory or _redis_must_not_be_called,
    }
    if script is not None:
        kwargs["transport"] = script.transport
    if areas is not _MISSING:
        kwargs["areas"] = areas
    return HHApiParser(**kwargs)


_MISSING = object()


async def _no_sleep(_seconds: float) -> None:
    return None


def _params(request: httpx.Request) -> Mapping[str, str]:
    return request.url.params


async def test_fetch_raw_without_bind_raises() -> None:
    script = _Script([])
    parser = _parser(script)
    with pytest.raises(RuntimeError, match="bind"):
        await parser.fetch_raw()
    assert script.seen == []


async def test_query_must_be_object_before_http() -> None:
    script = _Script([_search(1, [_hit("1")])])
    parser = _parser(script, config={"query": "python"})
    parser.bind(None, {}, NOW)
    with pytest.raises(ValueError, match="query"):
        await parser.fetch_raw()
    assert script.seen == []


async def test_zero_limit_skips_http() -> None:
    script = _Script([_search(1, [_hit("1")])])
    parser = _parser(script, config={"max_vacancies_per_run": 0})
    parser.bind(None, {}, NOW)
    assert await parser.fetch_raw() == []
    assert script.seen == []


async def test_cursor_uses_overlap_without_period() -> None:
    script = _Script([_search(0, [])])
    parser = _parser(script)
    parser.bind(CURSOR, {}, NOW)
    assert await parser.fetch_raw() == []
    assert len(script.seen) == 1
    params = _params(script.seen[0])
    assert "period" not in params
    assert params["date_from"] == "2026-11-04T10:05:00+0000"
    assert params["date_to"] == "2026-11-04T12:00:00+0000"
    assert params["order_by"] == "publication_time"
    assert params["per_page"] == "100"
    assert params["no_magic"] == "true"
    assert params["page"] == "0"
    assert params["text"] == "python"


async def test_period_copies_query_keys() -> None:
    script = _Script([_search(0, [])])
    parser = _parser(
        script,
        config={
            "backfill_days": 3,
            "query": {
                "text": "python OR golang",
                "search_field": ["name", "description"],
                "area": ["113"],
            },
        },
    )
    parser.bind(None, {}, NOW)
    assert await parser.fetch_raw() == []
    params = script.seen[0].url.params
    assert "date_from" not in params
    assert "date_to" not in params
    assert params["period"] == "3"
    assert params["text"] == "python OR golang"
    assert params.get_list("search_field") == ["name", "description"]
    assert params.get_list("area") == ["113"]
    assert params["order_by"] == "publication_time"
    assert params["per_page"] == "100"
    assert params["no_magic"] == "true"


async def test_found_over_2000_splits_from_old_to_new() -> None:
    probe = _hit("probe", published_at="2026-11-04T11:00:00+0000")
    older = _hit("old", published_at="2026-11-03T18:00:00+0000")
    script = _Script(
        [
            _search(2001, [probe]),
            _search(1, [older]),
            _json(200, _card("old")),
            _search(0, []),
        ]
    )
    parser = _parser(script, config={"backfill_days": 1})
    parser.bind(None, {}, NOW)
    found = await parser.fetch_raw()
    assert [item["id"] for item in found] == ["old"]
    assert [request.url.path for request in script.seen] == [
        "/vacancies",
        "/vacancies",
        "/vacancies/old",
        "/vacancies",
    ]
    first, left, _card_request, right = script.seen
    assert first.url.params["period"] == "1"
    assert "date_from" not in first.url.params
    assert left.url.params["date_from"] == "2026-11-03T12:00:00+0000"
    assert left.url.params["date_to"] == "2026-11-04T00:00:00+0000"
    assert "period" not in left.url.params
    assert right.url.params["date_from"] == "2026-11-04T00:00:00+0000"
    assert right.url.params["date_to"] == "2026-11-04T12:00:00+0000"
    assert script.responses == []


async def test_limit_fetches_oldest_card_only() -> None:
    newer = _hit("new", published_at="2026-11-04T11:00:00+0000")
    older = _hit(101, name="Старая", published_at="2026-11-01T08:00:00+0000")
    script = _Script(
        [
            _search(150, [newer]),
            _search(150, [older]),
            _json(200, _card("101", "Старая")),
        ]
    )
    parser = _parser(script, config={"max_vacancies_per_run": 1})
    parser.bind(CURSOR, {}, NOW)
    found = await parser.fetch_raw()
    assert [item["id"] for item in found] == ["101"]
    assert [request.url.path for request in script.seen] == [
        "/vacancies",
        "/vacancies",
        "/vacancies/101",
    ]
    assert [request.url.params["page"] for request in script.seen[:2]] == ["0", "1"]


async def test_known_listing_is_not_fetched_again() -> None:
    salary = {"from": 10, "currency": "RUR", "gross": True}
    item = _hit(
        "10",
        name="Same",
        salary_range={"gross": True, "currency": "RUR", "from": 10},
        employer={"name": "Acme", "id": "5", "trusted": True},
    )
    script = _Script([_search(1, [item]), _json(200, _card("10"))])
    parser = _parser(script)
    parser.bind(CURSOR, {"10": _known("Same", salary_range=salary)}, NOW)
    assert await parser.fetch_raw() == []
    assert [request.url.path for request in script.seen] == ["/vacancies"]
    assert parser.seen_external_ids == ["10"]
    assert parser.item_errors == []


async def test_changed_name_fetches_card() -> None:
    script = _Script(
        [
            _search(1, [_hit("10", name="New")]),
            _json(200, _card("10", "New")),
        ]
    )
    parser = _parser(script)
    parser.bind(CURSOR, {"10": _known("Old")}, NOW)
    found = await parser.fetch_raw()
    assert [item["id"] for item in found] == ["10"]
    assert script.seen[-1].url.path == "/vacancies/10"
    assert parser.seen_external_ids == []


async def test_search_403_is_raised() -> None:
    script = _Script([_json(403, {"errors": [{"type": "forbidden"}]})])
    parser = _parser(script)
    parser.bind(None, {}, NOW)
    with pytest.raises(ExternalServiceError) as caught:
        await parser.fetch_raw()
    assert caught.value.details["status_code"] == 403
    assert [request.url.path for request in script.seen] == ["/vacancies"]


async def test_search_429_does_not_retry_when_retries_are_zero() -> None:
    script = _Script([_json(429, {"errors": [{"type": "too_many_requests"}]})])
    parser = _parser(script, hh_max_retries=0)
    parser.bind(None, {}, NOW)
    with pytest.raises(ExternalServiceError) as caught:
        await parser.fetch_raw()
    assert caught.value.details["status_code"] == 429
    assert len(script.seen) == 1


async def test_one_missing_card_stays_in_item_errors() -> None:
    missing = _hit("1", published_at="2026-11-01T08:00:00+0000")
    kept = _hit("2", published_at="2026-11-02T08:00:00+0000")
    script = _Script(
        [
            _search(2, [kept, missing]),
            _json(404, {"errors": [{"type": "not_found"}]}),
            _json(200, _card("2")),
        ]
    )
    parser = _parser(script)
    parser.bind(CURSOR, {}, NOW)
    found = await parser.fetch_raw()
    assert [item["id"] for item in found] == ["2"]
    assert parser.item_errors == ["vacancy 1: 404"]
    assert [request.url.path for request in script.seen] == [
        "/vacancies",
        "/vacancies/1",
        "/vacancies/2",
    ]


async def test_redis_factory_failure_falls_back_to_one_areas_call() -> None:
    calls: list[str] = []

    def factory(url: str) -> Any:
        calls.append(url)
        raise RuntimeError("redis down")

    script = _Script(
        [
            _json(200, [{"id": "113", "name": "Россия", "areas": []}]),
            _search(0, []),
        ]
    )
    parser = _parser(script, areas=None, redis_factory=factory)
    parser.bind(None, {}, NOW)
    assert await parser.fetch_raw() == []
    assert calls == ["redis://localhost:6379/0"]
    assert [request.url.path for request in script.seen] == ["/areas", "/vacancies"]


async def test_preset_area_index_skips_areas_and_redis() -> None:
    script = _Script([_search(0, [])])
    parser = _parser(script, areas=_AREAS)
    parser.bind(None, {}, NOW)
    assert await parser.fetch_raw() == []
    assert [request.url.path for request in script.seen] == ["/vacancies"]


def test_provider_details_and_build_parser() -> None:
    from app.parsers.hh_api import HHApiParser as Parser

    with pytest.raises(SourceNotRunnableError) as missing:
        require_api_provider({})
    assert missing.value.details["provider"] is None
    with pytest.raises(SourceNotRunnableError) as foreign:
        require_api_provider({"provider": "superjob"})
    assert foreign.value.details["provider"] == "superjob"
    with pytest.raises(SourceNotRunnableError) as blank:
        require_api_provider({"provider": ""})
    assert blank.value.details["provider"] == ""
    assert require_api_provider({"provider": "hh"}) is Parser

    hh_id = uuid.uuid4()
    html_id = uuid.uuid4()
    source = Source(
        id=hh_id,
        slug="hh_it",
        source_type=SourceType.API,
        config={"provider": "hh", "query": {"text": "python"}},
        is_enabled=True,
    )
    parser = build_parser(source, _settings())
    assert type(parser) is Parser
    assert parser.slug == "hh_it"
    assert parser.config["query"] == {"text": "python"}

    html = Source(
        id=html_id,
        slug="html_live",
        source_type=SourceType.HTML,
        config={"url": "https://jobs.example.org/it"},
        is_enabled=True,
    )
    schedules = schedules_for(
        [
            source,
            html,
            Source(
                id=uuid.uuid4(),
                slug="sj",
                source_type=SourceType.API,
                config={"provider": "superjob"},
                is_enabled=True,
            ),
        ],
        _settings(parsers_enabled=True),
    )
    assert [item.source_id for item in schedules] == [hh_id, html_id]


async def test_parsers_disabled_returns_before_factory() -> None:
    source = Source(
        id=uuid.uuid4(),
        slug="hh_it",
        source_type=SourceType.API,
        config={"provider": "hh", "query": {"text": "python"}},
        is_enabled=True,
    )

    class _Session:
        async def get(self, _model: object, ident: object) -> Source | None:
            assert ident == source.id
            return source

        def add(self, _obj: object) -> None:
            raise AssertionError("parse_run")

        async def commit(self) -> None:
            raise AssertionError("commit")

    def factory(_source: Source, _settings: Settings) -> HHApiParser:
        raise AssertionError("factory")

    await perform_run(
        _Session(),  # type: ignore[arg-type]
        source.id,
        _settings(parsers_enabled=False),
        now=NOW,
        parser_factory=factory,
    )


async def test_bool_id_is_an_item_error() -> None:
    script = _Script([_search(1, [_hit(True)])])
    parser = _parser(script)
    parser.bind(CURSOR, {}, NOW)
    assert await parser.fetch_raw() == []
    assert parser.item_errors == ["search item: missing id"]
    assert [request.url.path for request in script.seen] == ["/vacancies"]


async def test_unsplittable_window_stops_before_page_20() -> None:
    def factory(url: str) -> Any:
        raise AssertionError(url)

    pages: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "hh.test"
        page = request.url.params["page"]
        pages.append(page)
        if int(page) >= 20:
            raise AssertionError(page)
        return _search(
            5000,
            [
                _hit(
                    page,
                    name="Same",
                    employer={"id": "1", "name": "A"},
                )
            ],
        )

    script = _Script([])
    script.transport = httpx.MockTransport(handler)
    known = {str(index): _known("Same", employer={"id": "1", "name": "A"}) for index in range(20)}
    parser = HHApiParser(
        slug="hh_it",
        config={"provider": "hh", "query": {"text": "python"}, "backfill_days": 7},
        settings=_settings(),
        transport=script.transport,
        sleep=_no_sleep,
        areas=_AREAS,
        redis_factory=factory,
    )
    # Ширина 5 минут: курсор на 5 минут впереди now, date_from = cursor - 10 минут.
    parser.bind(NOW + timedelta(minutes=5), known, NOW)
    assert await parser.fetch_raw() == []
    assert pages == [str(index) for index in range(20)]
    assert parser.seen_external_ids == sorted(str(index) for index in range(20))
