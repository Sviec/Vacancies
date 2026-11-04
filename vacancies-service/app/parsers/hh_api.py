"""Обход вакансий hh.ru через API. HTML и Telegram этот модуль не трогает.

Клиент создаётся внутри `fetch_raw`. Импорт модуля сеть не открывает и
`httpx.AsyncClient` не создаёт: регистрация — только класс и имя провайдера.
"""

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, ClassVar

import httpx
from redis.asyncio import Redis

from app.adapters.hh import HHClient
from app.config import Settings
from app.enums import SourceType
from app.parsers.api_providers import register_provider
from app.parsers.base import BaseParser
from app.parsers.hh_card import AreaIndex, build_area_index, map_hh_card
from app.parsers.registry import register
from app.services.hh_catalog import HhListing, employer_view, same_hh_listing
from app.services.normalizer import RawVacancy
from app.utils.errors import ExternalServiceError

_PER_PAGE = 100
_PAGE_CAP = 2000
_OVERLAP = timedelta(minutes=10)
_MIN_WINDOW = timedelta(minutes=5)
_AREAS_KEY = "hh:areas"
_AREAS_TTL_SECONDS = 86400

RedisFactory = Callable[[str], Redis]


def _redis_from_url(url: str) -> Redis:
    return Redis.from_url(url, decode_responses=True)


@dataclass(frozen=True, slots=True)
class _Window:
    """Окно поиска: либо `period`, либо пара дат. Вместе они не уходят в hh."""

    date_from: datetime | None
    date_to: datetime | None
    period: int | None


@register
class HHApiParser(BaseParser):
    """Один класс на все запросы hh. Отличия — в `sources.config`."""

    source_type: ClassVar[SourceType] = SourceType.API

    def __init__(
        self,
        *,
        slug: str,
        config: Mapping[str, Any],
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        areas: AreaIndex | None = None,
        redis_factory: RedisFactory = _redis_from_url,
    ) -> None:
        super().__init__(slug=slug, config=config, settings=settings)
        self._transport = transport
        self._sleep = sleep
        self._preset_areas = areas
        self._redis_factory = redis_factory
        self._area_index: AreaIndex | None = areas
        self._bound = False
        self._cursor: datetime | None = None
        self._known: dict[str, HhListing] = {}
        self._now: datetime | None = None
        self.item_errors: list[str] = []
        self.seen_external_ids: list[str] = []
        self._handled: set[str] = set()
        self._results: list[dict[str, Any]] = []
        self._stop = False
        self._limit = 0

    def bind(
        self,
        cursor: datetime | None,
        known: Mapping[str, Mapping[str, Any]],
        now: datetime,
    ) -> None:
        """Зафиксировать каталог и момент прогона. Без этого `fetch_raw` не ходит в сеть."""
        _require_aware(now, "now")
        if cursor is not None:
            _require_aware(cursor, "cursor")
        self._cursor = cursor
        stored: dict[str, HhListing] = {}
        for key, value in known.items():
            name = value.get("name")
            stored[str(key)] = {
                "name": name if isinstance(name, str) else None,
                "salary_range": value.get("salary_range"),
                "employer": employer_view(value.get("employer")),
            }
        self._known = stored
        self._now = now
        self._bound = True

    async def fetch_raw(self) -> list[dict[str, Any]]:
        """Карточки, которые надо записать. Известные без изменений сюда не попадают."""
        now = self._now
        if not self._bound or now is None:
            msg = "HHApiParser.fetch_raw called before bind"
            raise RuntimeError(msg)
        self._reset_run()
        # stale_after_days — # TODO: этап 13d
        # skills_mode — # TODO: dictionary_only уже внутри map_hh_card
        query = _require_query(self.config)
        limit = _whole_int(self.config.get("max_vacancies_per_run"), minimum=0, default=400)
        if limit == 0:
            return []
        self._limit = limit
        backfill_days = _whole_int(self.config.get("backfill_days"), minimum=1, default=7)
        client = HHClient(self.settings, transport=self._transport, sleep=self._sleep)
        self._area_index = await self._resolve_areas(client)
        window = _initial_window(self._cursor, now, backfill_days)
        await self._walk(client, query, window, now, backfill_days)
        return list(self._results)

    def to_normalized(self, raw: dict[str, Any]) -> RawVacancy:
        """Карточка прогона → `RawVacancy`. `parsed_at` в payload карточки не кладётся."""
        parsed_at = raw["parsed_at"]
        if not isinstance(parsed_at, datetime):
            msg = "parsed_at must be a timezone-aware datetime"
            raise TypeError(msg)
        card = {key: value for key, value in raw.items() if key != "parsed_at"}
        return map_hh_card(card, slug=self.slug, parsed_at=parsed_at, areas=self._area_index)

    def _reset_run(self) -> None:
        self.item_errors = []
        self.seen_external_ids = []
        self._handled = set()
        self._results = []
        self._stop = False

    async def _resolve_areas(self, client: HHClient) -> AreaIndex | None:
        """Готовый индекс, Redis `hh:areas` или один `GET /areas`. Ошибка Redis не роняет прогон."""
        if self._preset_areas is not None:
            return self._preset_areas
        redis: Redis | None = None
        cached: object | None = None
        try:
            try:
                redis = self._redis_factory(self.settings.redis_url)
                cached = await _read_areas_cache(redis)
            except Exception:
                cached = None
            if cached is not None:
                return _index_or_none(cached)
            tree = await client.areas()
            index = _index_or_none(tree)
            if index is not None and redis is not None:
                await _write_areas_cache(redis, tree)
            return index
        finally:
            if redis is not None:
                with contextlib.suppress(Exception):
                    await redis.aclose()

    async def _walk(
        self,
        client: HHClient,
        query: Mapping[str, Any],
        window: _Window,
        now: datetime,
        backfill_days: int,
    ) -> None:
        if self._stop:
            return
        first = await client.search(_search_params(query, window, page=0))
        found, _items = _require_page(first)
        if found > _PAGE_CAP:
            target = window
            if window.period is not None:
                # Пробный ответ с period не используем: окно заменяется парой дат.
                target = _Window(now - timedelta(days=backfill_days), now, None)
            if _splittable(target):
                older, newer = _halves(target)
                await self._walk(client, query, older, now, backfill_days)
                await self._walk(client, query, newer, now, backfill_days)
                return
            if target is not window:
                await self._walk(client, query, target, now, backfill_days)
                return
            # TODO: хвост found > 2000 в несжимаемом окне не добирается
        await self._read_window(client, query, window, first)

    async def _read_window(
        self,
        client: HHClient,
        query: Mapping[str, Any],
        window: _Window,
        first: dict[str, Any],
    ) -> None:
        """Собрать страницы окна и только потом качать карточки от старых к новым.

        hh с `order_by=publication_time` отдаёт новые первыми, поэтому страница 0
        не первая в обходе. Лимит обрывает GET и более новые окна, не середину сортировки.
        """
        collected: list[object] = []
        payload = first
        page = 0
        while True:
            page_found, page_items = _require_page(payload)
            collected.extend(page_items)
            next_page = page + 1
            if (
                not page_items
                or next_page * _PER_PAGE >= page_found
                or next_page * _PER_PAGE >= _PAGE_CAP
            ):
                break
            payload = await client.search(_search_params(query, window, page=next_page))
            page = next_page
        await self._take_cards(client, collected)

    async def _take_cards(self, client: HHClient, collected: list[object]) -> None:
        rows: list[tuple[tuple[int, float, str], str, dict[str, Any]]] = []
        for item in collected:
            if not isinstance(item, dict):
                self.item_errors.append("search item: not an object")
                continue
            external_id = _external_id(item.get("id"))
            if external_id is None:
                self.item_errors.append("search item: missing id")
                continue
            rows.append((_sort_key(item, external_id), external_id, item))
        rows.sort(key=lambda row: row[0])
        now = self._now
        if now is None:
            msg = "HHApiParser.fetch_raw called before bind"
            raise RuntimeError(msg)
        for _key, external_id, item in rows:
            if external_id in self._handled:
                continue
            self._handled.add(external_id)
            known = self._known.get(external_id)
            if known is not None and same_hh_listing(item, known):
                self.seen_external_ids.append(external_id)
                continue
            if len(self._results) >= self._limit:
                self._stop = True
                return
            card = await self._fetch_card(client, external_id)
            if card is None:
                continue
            try:
                map_hh_card(card, slug=self.slug, parsed_at=now, areas=self._area_index)
            except (ValueError, TypeError) as exc:
                self.item_errors.append(f"vacancy {external_id}: {exc}")
                continue
            self._results.append(card)
            if len(self._results) >= self._limit:
                self._stop = True
                return

    async def _fetch_card(self, client: HHClient, external_id: str) -> dict[str, Any] | None:
        try:
            return await client.vacancy(external_id)
        except ExternalServiceError as exc:
            line = _card_item_error(exc, external_id)
            if line is None:
                raise
            self.item_errors.append(line)
            return None


register_provider("hh", HHApiParser)


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = f"{label} must be timezone-aware"
        raise ValueError(msg)


def _require_query(config: Mapping[str, Any]) -> dict[str, Any]:
    query = config.get("query")
    if not isinstance(query, Mapping):
        msg = "hh query must be an object"
        raise ValueError(msg)
    return dict(query)


def _whole_int(value: object, *, minimum: int, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        return default
    return value


def _initial_window(cursor: datetime | None, now: datetime, backfill_days: int) -> _Window:
    if cursor is None:
        return _Window(None, None, backfill_days)
    return _Window(cursor - _OVERLAP, now, None)


def _search_params(query: Mapping[str, Any], window: _Window, *, page: int) -> dict[str, Any]:
    params = dict(query)
    params.pop("date_from", None)
    params.pop("date_to", None)
    params.pop("period", None)
    params.pop("page", None)
    params["order_by"] = "publication_time"
    params["per_page"] = _PER_PAGE
    params["no_magic"] = "true"
    params["page"] = page
    if window.period is not None:
        params["period"] = window.period
        return params
    if window.date_from is None or window.date_to is None:
        msg = "hh search window has neither period nor dates"
        raise RuntimeError(msg)
    params["date_from"] = _hh_timestamp(window.date_from)
    params["date_to"] = _hh_timestamp(window.date_to)
    return params


def _hh_timestamp(value: datetime) -> str:
    _require_aware(value, "hh datetime")
    return value.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%S%z")


def _splittable(window: _Window) -> bool:
    if window.date_from is None or window.date_to is None:
        return False
    if window.date_to - window.date_from <= _MIN_WINDOW:
        return False
    middle = _midpoint(window.date_from, window.date_to)
    older = _Window(window.date_from, middle, None)
    newer = _Window(middle, window.date_to, None)
    if _same_bounds(older, window) or _same_bounds(newer, window):
        return False
    return window.date_from < middle < window.date_to


def _halves(window: _Window) -> tuple[_Window, _Window]:
    if window.date_from is None or window.date_to is None:
        msg = "hh search window cannot be split without dates"
        raise RuntimeError(msg)
    middle = _midpoint(window.date_from, window.date_to)
    return _Window(window.date_from, middle, None), _Window(middle, window.date_to, None)


def _midpoint(start: datetime, end: datetime) -> datetime:
    return (start + (end - start) / 2).replace(microsecond=0)


def _same_bounds(child: _Window, parent: _Window) -> bool:
    return child.date_from == parent.date_from and child.date_to == parent.date_to


def _require_page(payload: object) -> tuple[int, list[object]]:
    if not isinstance(payload, dict):
        msg = "hh search response needs an integer found and a list of items"
        raise ValueError(msg)
    found = payload.get("found")
    items = payload.get("items")
    if isinstance(found, bool) or not isinstance(found, int) or not isinstance(items, list):
        msg = "hh search response needs an integer found and a list of items"
        raise ValueError(msg)
    return found, items


def _external_id(value: object) -> str | None:
    """Строка как есть. Целое, кроме bool, — через `str`. Пустое и прочее — нет id."""
    if isinstance(value, str):
        if not value.strip():
            return None
        return value
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return str(value)


def _sort_key(item: Mapping[str, Any], external_id: str) -> tuple[int, float, str]:
    published = _published_at(item.get("published_at"))
    if published is None:
        return (1, 0.0, external_id)
    return (0, published.timestamp(), external_id)


def _published_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _card_item_error(exc: ExternalServiceError, external_id: str) -> str | None:
    status = exc.details.get("status_code")
    if status == 404:
        return f"vacancy {external_id}: 404"
    if status == 400:
        # TODO: 400 карточки hh остаётся в item_errors и не останавливает прогон.
        return f"vacancy {external_id}: 400"
    if exc.details.get("reason") == "invalid_payload":
        return f"vacancy {external_id}: invalid_payload"
    return None


def _index_or_none(tree: object) -> AreaIndex | None:
    try:
        return build_area_index(tree)
    except ValueError:
        # TODO: битое дерево /areas не останавливает обход; обход с areas=None.
        return None


async def _read_areas_cache(redis: Redis) -> object | None:
    raw = await redis.get(_AREAS_KEY)
    if raw is None or raw == b"" or raw == "":
        return None
    text = raw.decode("utf-8") if isinstance(raw, bytes | bytearray) else raw
    parsed: object = json.loads(text)
    return parsed


async def _write_areas_cache(redis: Redis, tree: object) -> None:
    try:
        await redis.set(
            _AREAS_KEY,
            json.dumps(tree, ensure_ascii=False),
            ex=_AREAS_TTL_SECONDS,
        )
    except Exception:
        return
