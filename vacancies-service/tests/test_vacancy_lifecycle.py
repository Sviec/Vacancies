"""Суточное гашение и перепроверка hh без базы, Redis и сети."""

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
import pytest

import app.services.vacancy_lifecycle as lifecycle_module
import app.tasks.lifecycle as lifecycle_task
import app.tasks.scheduler as scheduler_module
from app.config import Settings
from app.services.vacancy_lifecycle import (
    HhRecheckTarget,
    canon_should_deactivate,
    posting_is_stale,
    recheck_cards,
    recheck_limit,
    source_config_is_hh,
    take_recheck_page,
)
from app.tasks.lifecycle import run_lifecycle

NOW = datetime(2026, 11, 4, 12, tzinfo=UTC)
_OLD = NOW - timedelta(days=100)
_MONTH = {"stale_after_days": 30}
_APP = "test-app-token"
_AGENT = "hh-test-agent/1 (tester@example.com)"


class _Flag:
    def __init__(self, active: bool) -> None:
        self.is_active = active
        self.last_seen_at = NOW
        self.raw_payload = {"keep": True}


class _Job:
    def __init__(self, kind: str | None) -> None:
        self.meta = None if kind is None else {"kind": kind}
        self.deleted = False

    def delete(self) -> None:
        self.deleted = True


class _Scheduler:
    def __init__(self) -> None:
        self.jobs: list[_Job] = []
        self.cancelled: list[_Job] = []
        self.scheduled: list[dict[str, object]] = []

    def get_jobs(self) -> list[_Job]:
        return list(self.jobs)

    def cancel(self, job: _Job) -> None:
        self.cancelled.append(job)

    def schedule(self, **kwargs: object) -> None:
        self.scheduled.append(kwargs)


def _settings(
    *,
    token: str | None = _APP,
    user_agent: str | None = _AGENT,
) -> Settings:
    return Settings(
        _env_file=None,
        hh_app_token=token,
        hh_user_agent=user_agent,
        hh_base_url="https://hh.test",
        hh_request_delay_seconds=0,
        hh_timeout_seconds=5,
        hh_max_retries=0,
    )


def _target(external_id: str, active: bool) -> tuple[HhRecheckTarget, _Flag]:
    flag = _Flag(active)
    return HhRecheckTarget(uuid4(), uuid4(), external_id, flag), flag


def _transport(
    routes: dict[str, httpx.Response | Exception],
) -> tuple[list[str], httpx.MockTransport]:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "hh.test"
        assert request.url.host != "api.hh.ru"
        seen.append(request.url.path)
        item = routes[request.url.path]
        if isinstance(item, Exception):
            raise item
        return item

    return seen, httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _block_real_http(monkeypatch: pytest.MonkeyPatch) -> None:
    real_init = httpx.AsyncClient.__init__

    def guarded(self: httpx.AsyncClient, *args: object, **kwargs: object) -> None:
        if not isinstance(kwargs.get("transport"), httpx.MockTransport):
            raise AssertionError("real network is not allowed")
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", guarded)

    def _forbid_sync(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("sync HTTP client is not allowed")

    monkeypatch.setattr(httpx.Client, "__init__", _forbid_sync)


def test_stale_day_boundary() -> None:
    assert posting_is_stale(NOW - timedelta(days=30), _MONTH, NOW) is False
    assert posting_is_stale(NOW - timedelta(days=30, seconds=1), _MONTH, NOW) is True
    assert posting_is_stale(NOW - timedelta(days=29), _MONTH, NOW) is False
    one_day = {"stale_after_days": 1}
    assert posting_is_stale(NOW - timedelta(days=1), one_day, NOW) is False
    assert posting_is_stale(NOW - timedelta(days=1, microseconds=1), one_day, NOW) is True
    shifted = (NOW - timedelta(days=30)).astimezone(timezone(timedelta(hours=3)))
    assert posting_is_stale(shifted, _MONTH, NOW) is False


@pytest.mark.parametrize(
    "config",
    [
        {},
        None,
        {"stale_after_days": True},
        {"stale_after_days": False},
        {"stale_after_days": 0},
        {"stale_after_days": -3},
        {"stale_after_days": 30.0},
        {"stale_after_days": "30"},
    ],
)
def test_non_whole_days_never_stale(config: object) -> None:
    assert posting_is_stale(_OLD, config, NOW) is False


def test_naive_last_seen_does_not_crash_and_naive_now_raises() -> None:
    assert posting_is_stale(datetime(2020, 1, 1), _MONTH, NOW) is False  # noqa: DTZ001
    with pytest.raises(ValueError, match="timezone-aware"):
        posting_is_stale(_OLD, _MONTH, datetime(2026, 11, 4, 12))  # noqa: DTZ001


def test_canon_without_postings_and_partial_stale() -> None:
    fresh = NOW - timedelta(days=1)
    assert canon_should_deactivate([], NOW) is False
    assert canon_should_deactivate([], datetime(2026, 11, 4)) is False  # noqa: DTZ001
    assert canon_should_deactivate([(_OLD, _MONTH)], NOW) is True
    assert canon_should_deactivate([(_OLD, _MONTH), (fresh, _MONTH)], NOW) is False
    assert canon_should_deactivate([(_OLD, _MONTH), (_OLD, None)], NOW) is False
    assert canon_should_deactivate([(_OLD, _MONTH), (_OLD, {})], NOW) is False
    assert canon_should_deactivate([(_OLD, {"stale_after_days": True})], NOW) is False


def test_hh_config_requires_exact_provider_and_skips_demo() -> None:
    assert source_config_is_hh({"provider": "hh"}) is True
    assert source_config_is_hh({"provider": "hh", "demo": False}) is True
    assert source_config_is_hh({"provider": "hh", "demo": "true"}) is True
    assert source_config_is_hh({"provider": "hh", "demo": True}) is False
    assert source_config_is_hh({"provider": "HH"}) is False
    assert source_config_is_hh({"provider": "hh "}) is False
    assert source_config_is_hh({"provider": 1}) is False
    assert source_config_is_hh({}) is False
    assert source_config_is_hh(None) is False


def test_recheck_limit_matches_whole_int() -> None:
    assert recheck_limit(True) == 400
    assert recheck_limit(False) == 400
    assert recheck_limit(None) == 400
    assert recheck_limit("10") == 400
    assert recheck_limit(1.5) == 400
    assert recheck_limit(-1) == 400
    assert recheck_limit(0) == 0
    assert recheck_limit(12) == 12


def test_cursor_slice_does_not_wrap() -> None:
    ids = [UUID(int=number) for number in range(1, 6)]
    taken, cursor = take_recheck_page(ids, cursor=None, limit=2)
    assert taken == ids[:2]
    assert cursor == ids[1]

    taken, cursor = take_recheck_page(ids, cursor=ids[1], limit=2)
    assert taken == ids[2:4]
    assert cursor == ids[3]

    taken, cursor = take_recheck_page(ids, cursor=ids[3], limit=2)
    assert taken == [ids[4]]
    assert cursor is None
    assert ids[0] not in taken

    kept, same = take_recheck_page(ids, cursor=ids[0], limit=0)
    assert kept == []
    assert same == ids[0]


@pytest.mark.parametrize(
    "payload",
    [{}, {"archived": False}, {"archived": "yes"}, {"name": "live"}],
)
async def test_card_without_archived_true_becomes_active(payload: dict[str, object]) -> None:
    seen, transport = _transport({"/vacancies/9": httpx.Response(200, json=payload)})
    target, flag = _target("9", False)
    assert await recheck_cards([target], _settings(), transport=transport) is False
    assert flag.is_active is True
    assert flag.last_seen_at == NOW
    assert flag.raw_payload == {"keep": True}
    assert seen == ["/vacancies/9"]


async def test_archived_card_becomes_inactive() -> None:
    _seen, transport = _transport(
        {"/vacancies/9": httpx.Response(200, json={"archived": True, "id": "9"})}
    )
    target, flag = _target("9", True)
    assert await recheck_cards([target], _settings(), transport=transport) is False
    assert flag.is_active is False
    assert flag.raw_payload == {"keep": True}


async def test_not_found_deactivates_and_requests_the_next_card() -> None:
    seen, transport = _transport(
        {
            "/vacancies/1": httpx.Response(404, json={"errors": [{"type": "not_found"}]}),
            "/vacancies/2": httpx.Response(200, json={}),
        }
    )
    first, first_flag = _target("1", True)
    second, second_flag = _target("2", False)
    assert await recheck_cards([first, second], _settings(), transport=transport) is False
    assert first_flag.is_active is False
    assert second_flag.is_active is True
    assert seen == ["/vacancies/1", "/vacancies/2"]


@pytest.mark.parametrize(
    "failure",
    [403, 429, 500, 503, 400, "timeout", "connect", "invalid_payload"],
)
async def test_soft_failure_keeps_flag_and_requests_the_next_card(failure: int | str) -> None:
    if failure == "timeout":
        first: httpx.Response | Exception = httpx.TimeoutException("slow")
    elif failure == "connect":
        first = httpx.ConnectError("down")
    elif failure == "invalid_payload":
        first = httpx.Response(200, json=[])
    else:
        first = httpx.Response(int(failure), json={"errors": [{"type": "bad"}]})
    seen, transport = _transport(
        {
            "/vacancies/1": first,
            "/vacancies/2": httpx.Response(200, json={"archived": True}),
        }
    )
    first_target, first_flag = _target("1", True)
    second_target, second_flag = _target("2", True)
    stopped = await recheck_cards(
        [first_target, second_target],
        _settings(),
        transport=transport,
    )
    assert stopped is False
    assert first_flag.is_active is True
    assert second_flag.is_active is False
    assert first_flag.last_seen_at == NOW
    assert seen == ["/vacancies/1", "/vacancies/2"]


@pytest.mark.parametrize(
    ("token", "user_agent"),
    [
        (None, "hh-test-agent/1 (tester@example.com)"),
        ("test-app-token", None),
    ],
)
async def test_missing_credentials_do_not_open_client_or_deactivate(
    monkeypatch: pytest.MonkeyPatch,
    token: str | None,
    user_agent: str | None,
) -> None:
    opened = {"client": 0, "http": 0}

    def _client_init(*_args: object, **_kwargs: object) -> None:
        opened["client"] += 1
        raise AssertionError("HHClient")

    def _http_init(*_args: object, **_kwargs: object) -> None:
        opened["http"] += 1
        raise AssertionError("AsyncClient")

    monkeypatch.setattr("app.adapters.hh.HHClient.__init__", _client_init)
    monkeypatch.setattr(httpx.AsyncClient, "__init__", _http_init)
    target, flag = _target("1001", True)
    stopped = await recheck_cards([target], _settings(token=token, user_agent=user_agent))
    assert stopped is True
    assert flag.is_active is True
    assert opened == {"client": 0, "http": 0}


async def test_empty_batch_does_not_construct_client(monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbid(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("HHClient")

    monkeypatch.setattr("app.adapters.hh.HHClient.__init__", _forbid)
    assert await recheck_cards([], _settings()) is False


def test_import_does_not_bind_hh_client() -> None:
    assert "HHClient" not in vars(lifecycle_module)
    assert "HHClient" not in vars(lifecycle_task)
    assert "run_lifecycle" not in vars(scheduler_module)


def test_disabled_parsers_do_not_construct_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.tasks.lifecycle.get_settings",
        lambda: Settings(_env_file=None, parsers_enabled=False),
    )

    def _forbid(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("must not run")

    monkeypatch.setattr("app.adapters.hh.HHClient.__init__", _forbid)
    monkeypatch.setattr("app.tasks.lifecycle.init_engine", _forbid)
    monkeypatch.setattr("app.tasks.lifecycle.redis.Redis.from_url", _forbid)
    run_lifecycle()


def test_schedule_is_installed_and_cancelled_without_main(monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbid(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("HHClient")

    monkeypatch.setattr("app.adapters.hh.HHClient.__init__", _forbid)
    settings = Settings(_env_file=None, rq_default_timeout=900)
    fake = _Scheduler()
    before = datetime.now(UTC)
    scheduler_module._install_lifecycle(fake, settings)  # type: ignore[arg-type]
    after = datetime.now(UTC)

    assert len(fake.scheduled) == 1
    call = fake.scheduled[0]
    assert call["func"] is run_lifecycle
    assert call["args"] == ()
    assert call["interval"] == 86400
    assert call["repeat"] is None
    assert call["timeout"] == 900
    assert call["meta"] == {"kind": "lifecycle_schedule"}
    scheduled = call["scheduled_time"]
    assert isinstance(scheduled, datetime)
    assert before + timedelta(days=1) <= scheduled <= after + timedelta(days=1)

    parse_job = _Job("parse_schedule")
    life_job = _Job("lifecycle_schedule")
    other = _Job("foreign")
    bare = _Job(None)
    fake.jobs = [parse_job, life_job, other, bare]
    scheduler_module._cancel_schedules(fake)  # type: ignore[arg-type]
    assert parse_job.deleted is True
    assert life_job.deleted is True
    assert other.deleted is False
    assert bare.deleted is False
    assert fake.cancelled == [parse_job, life_job]
