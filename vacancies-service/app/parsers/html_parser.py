"""HTML-парсер: один класс, сайт задаётся `sources.config`.

# TODO: LLM-обогащение partial не вызывается. parse_quality считает нормализатор.
# TODO: разбор CSS делает selectolax после page.content(). Селектор, который
# умеет только Playwright, не поддержан. @attr режется по последнему @.
# TODO: ответ robots.txt не 200 и не 404, либо сеть оборвалась: прогон failed,
# URL страницы не запрашивается. 404 у robots.txt — обход можно.
# TODO: оба ключа пагинации сразу: побеждает next_selector.
# TODO: нет url у карточки: external_id равен {page_url}#{index}.
# TODO: --no-sandbox у Chromium из-за non-root пользователя в образе.
"""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar, Protocol
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx
from selectolax.lexbor import LexborHTMLParser

from app.config import Settings
from app.enums import SourceType
from app.parsers.base import BaseParser, raw_vacancy
from app.parsers.config import page_delay_seconds, split_selector
from app.parsers.registry import register
from app.services.normalizer import RawVacancy

Sleep = Callable[[float], Awaitable[None]]
RobotsGet = Callable[[str], Awaitable[int | str]]


class PageFetcher(Protocol):
    """Загрузка HTML одной страницы. Браузер открывается реализацией, не раньше robots."""

    async def fetch(self, url: str) -> str: ...


@dataclass(frozen=True, slots=True)
class HtmlFields:
    """Селекторы полей карточки. `skills is None` — ключа в config не было."""

    title: str | None
    company: str | None
    city: str | None
    salary: str | None
    description: str | None
    url: str | None
    published_at: str | None
    skills: str | None


@dataclass(frozen=True, slots=True)
class HtmlPagination:
    """Пагинация. Оба способа сразу не живут: остаётся `next_selector`."""

    next_selector: str | None
    page_param: str | None
    max_pages: int


@dataclass(frozen=True, slots=True)
class HtmlSourceConfig:
    """Разобранный config HTML-источника. Без url или list_selector не собирается."""

    url: str
    list_selector: str
    fields: HtmlFields
    pagination: HtmlPagination
    delay_seconds: float | None


def html_source_config(data: Mapping[str, Any]) -> HtmlSourceConfig:
    """Собрать config из dict сида. Ошибка здесь — ещё до любого HTTP."""
    url = data.get("url")
    list_selector = data.get("list_selector")
    if not isinstance(url, str) or not url.strip():
        msg = "HTML source config requires url"
        raise ValueError(msg)
    if not isinstance(list_selector, str) or not list_selector.strip():
        msg = "HTML source config requires list_selector"
        raise ValueError(msg)
    fields_raw = data.get("fields") or {}
    if not isinstance(fields_raw, Mapping):
        msg = "HTML source config fields must be a mapping"
        raise ValueError(msg)
    pagination_raw = data.get("pagination") or {}
    if not isinstance(pagination_raw, Mapping):
        msg = "HTML source config pagination must be a mapping"
        raise ValueError(msg)
    next_selector = _optional_str(pagination_raw.get("next_selector"))
    page_param = _optional_str(pagination_raw.get("page_param"))
    # Оба ключа: листаем по ссылке «дальше», page_param не используем.
    if next_selector is not None:
        page_param = None
    return HtmlSourceConfig(
        url=url.strip(),
        list_selector=list_selector.strip(),
        fields=HtmlFields(
            title=_optional_str(fields_raw.get("title")),
            company=_optional_str(fields_raw.get("company")),
            city=_optional_str(fields_raw.get("city")),
            salary=_optional_str(fields_raw.get("salary")),
            description=_optional_str(fields_raw.get("description")),
            url=_optional_str(fields_raw.get("url")),
            published_at=_optional_str(fields_raw.get("published_at")),
            skills=_optional_str(fields_raw.get("skills")) if "skills" in fields_raw else None,
        ),
        pagination=HtmlPagination(
            next_selector=next_selector,
            page_param=page_param,
            max_pages=_max_pages(pagination_raw),
        ),
        delay_seconds=_delay(data.get("delay_seconds")),
    )


def parse_listing(
    html: str, page_url: str, config: HtmlSourceConfig
) -> tuple[list[dict[str, Any]], str | None]:
    """Карточки и абсолютный URL следующей страницы.

    `next_selector` читает href. Описание — текст без тегов: script и style
    выкидываются до `text()`.
    """
    tree = LexborHTMLParser(html)
    cards: list[dict[str, Any]] = []
    for index, node in enumerate(tree.css(config.list_selector)):
        cards.append(_card(node, page_url, index, config.fields))
    return cards, _next_page_url(tree, page_url, config.pagination.next_selector)


def page_url_for(url: str, page_param: str, page: int) -> str:
    """Подставить номер страницы в query, не теряя остальные параметры."""
    parts = urlsplit(url)
    kept = [(key, value) for key, value in _query_pairs(parts.query) if key != page_param]
    kept.append((page_param, str(page)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment))


def robots_permits(body: str, url: str, user_agent: str) -> bool:
    """Разрешает ли тело robots.txt загрузку `url` этому User-Agent."""
    parser = RobotFileParser()
    parser.parse(body.splitlines())
    return bool(parser.can_fetch(user_agent, url))


async def fetch_html_pages(
    start_url: str,
    config: HtmlSourceConfig,
    *,
    settings: Settings,
    fetcher: PageFetcher,
    robots_get: RobotsGet,
    sleep: Sleep,
) -> list[dict[str, Any]]:
    """Страницы листинга. Пауза только между страницами, не перед первой и не перед robots.txt."""
    robots_body = await _robots_body(start_url, settings, robots_get)
    delay = page_delay_seconds(config.delay_seconds, settings)
    if config.pagination.next_selector is not None:
        return await _fetch_by_next(
            start_url,
            config,
            settings,
            fetcher,
            sleep,
            robots_body,
            delay,
        )
    if config.pagination.page_param is not None:
        return await _fetch_by_page(
            start_url,
            config,
            settings,
            fetcher,
            sleep,
            robots_body,
            delay,
        )
    await _ensure_allowed(start_url, robots_body, settings)
    html = await fetcher.fetch(start_url)
    cards, _next = parse_listing(html, start_url, config)
    return cards


def _optional_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _delay(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _max_pages(pagination: Mapping[str, Any]) -> int:
    if "max_pages" not in pagination:
        return 1
    raw = pagination["max_pages"]
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        return 1
    pages = int(raw)
    return pages if pages >= 1 else 1


def _query_pairs(query: str) -> list[tuple[str, str]]:
    if not query:
        return []
    pairs: list[tuple[str, str]] = []
    for chunk in query.split("&"):
        key, sep, value = chunk.partition("=")
        if sep:
            pairs.append((key, value))
        elif key:
            pairs.append((key, ""))
    return pairs


def _plain_text(node: Any) -> str:
    for selector in ("script", "style"):
        for child in node.css(selector):
            child.decompose()
    text = node.text(separator=" ", strip=True)
    if not isinstance(text, str):
        return ""
    return " ".join(text.split())


def _field(node: Any, spec: str | None) -> str | None:
    if spec is None:
        return None
    selector, attr = split_selector(spec)
    found = node.css_first(selector)
    if found is None:
        return None
    if attr is not None:
        value = found.attributes.get(attr)
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        return stripped or None
    text = _plain_text(found)
    return text or None


def _skills(node: Any, spec: str) -> tuple[str, ...]:
    selector, attr = split_selector(spec)
    values: list[str] = []
    for found in node.css(selector):
        if attr is not None:
            raw = found.attributes.get(attr)
            text = raw.strip() if isinstance(raw, str) else ""
        else:
            text = _plain_text(found)
        if text:
            values.append(text)
    return tuple(values)


def _published_at(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _card(node: Any, page_url: str, index: int, fields: HtmlFields) -> dict[str, Any]:
    href = _field(node, fields.url)
    absolute = urljoin(page_url, href) if href else None
    # Нет ссылки карточки — стабильный id внутри страницы, не пустая строка.
    external_id = absolute if absolute else f"{page_url}#{index}"
    item: dict[str, Any] = {
        "external_id": external_id,
        "title": _field(node, fields.title) or "",
        "company": _field(node, fields.company),
        "city": _field(node, fields.city),
        "salary_text": _field(node, fields.salary),
        "description_raw": _field(node, fields.description) or "",
        "url": absolute,
        "published_at": _published_at(_field(node, fields.published_at)),
    }
    if fields.skills is not None:
        item["skills_hint"] = _skills(node, fields.skills)
    return item


def _next_page_url(tree: LexborHTMLParser, page_url: str, spec: str | None) -> str | None:
    if spec is None:
        return None
    selector, _attr = split_selector(spec)
    node = tree.css_first(selector)
    if node is None:
        return None
    href = node.attributes.get("href")
    if not isinstance(href, str) or not href.strip():
        return None
    return urljoin(page_url, href.strip())


def robots_url_for(page_url: str) -> str:
    parts = urlsplit(page_url)
    return urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))


async def _robots_body(start_url: str, settings: Settings, robots_get: RobotsGet) -> str | None:
    """Тело robots.txt либо None, если правил нет (флаг выключен или 404).

    Любой другой статус и сетевая ошибка пробрасываются: страницу не открываем.
    """
    if not settings.respect_robots_txt:
        return None
    result = await robots_get(robots_url_for(start_url))
    if isinstance(result, str):
        return result
    if result == 404:
        return None
    msg = f"robots.txt status {result}"
    raise RuntimeError(msg)


async def _ensure_allowed(url: str, robots_body: str | None, settings: Settings) -> None:
    if robots_body is None:
        return
    if robots_permits(robots_body, url, settings.playwright_user_agent):
        return
    msg = "robots.txt disallows crawling"
    raise RuntimeError(msg)


async def _fetch_by_next(
    start_url: str,
    config: HtmlSourceConfig,
    settings: Settings,
    fetcher: PageFetcher,
    sleep: Sleep,
    robots_body: str | None,
    delay: float,
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    seen: set[str] = set()
    url: str | None = start_url
    for index in range(config.pagination.max_pages):
        if url is None or url in seen:
            break
        if index > 0:
            await sleep(delay)
        seen.add(url)
        await _ensure_allowed(url, robots_body, settings)
        html = await fetcher.fetch(url)
        cards, url = parse_listing(html, url, config)
        collected.extend(cards)
    return collected


async def _fetch_by_page(
    start_url: str,
    config: HtmlSourceConfig,
    settings: Settings,
    fetcher: PageFetcher,
    sleep: Sleep,
    robots_body: str | None,
    delay: float,
) -> list[dict[str, Any]]:
    page_param = config.pagination.page_param
    if page_param is None:
        return []
    collected: list[dict[str, Any]] = []
    for page in range(1, config.pagination.max_pages + 1):
        if page > 1:
            await sleep(delay)
        url = page_url_for(start_url, page_param, page)
        await _ensure_allowed(url, robots_body, settings)
        html = await fetcher.fetch(url)
        cards, _next = parse_listing(html, url, config)
        if not cards:
            break
        collected.extend(cards)
    return collected


class _PlaywrightFetcher:
    """Chromium поднимается на первом `fetch`, то есть только после проверки robots.txt."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._playwright: Any = None
        self._browser: Any = None

    async def fetch(self, url: str) -> str:
        if self._browser is None:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            # Non-root в контейнере не может поднять Chromium без этих флагов.
            self._browser = await self._playwright.chromium.launch(
                headless=self._settings.playwright_headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
        page = await self._browser.new_page(user_agent=self._settings.playwright_user_agent)
        try:
            await page.goto(url, wait_until="domcontentloaded")
            content: str = await page.content()
            return content
        finally:
            await page.close()

    async def aclose(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None


def _httpx_robots_get(settings: Settings) -> RobotsGet:
    async def robots_get(url: str) -> int | str:
        try:
            async with httpx.AsyncClient(
                trust_env=False,
                timeout=20.0,
                follow_redirects=True,
                headers={"User-Agent": settings.playwright_user_agent},
            ) as client:
                response = await client.get(url)
        except httpx.HTTPError as exc:
            msg = f"robots.txt request failed: {exc}"
            raise RuntimeError(msg) from exc
        if response.status_code == 200:
            return response.text
        return response.status_code

    return robots_get


async def _async_sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)


@register
class HtmlParser(BaseParser):
    """Один класс на все HTML-сайты: отличия только в `sources.config`."""

    source_type: ClassVar[SourceType] = SourceType.HTML

    async def fetch_raw(self) -> list[dict[str, Any]]:
        config = html_source_config(self.config)
        fetcher = _PlaywrightFetcher(self.settings)
        try:
            return await fetch_html_pages(
                config.url,
                config,
                settings=self.settings,
                fetcher=fetcher,
                robots_get=_httpx_robots_get(self.settings),
                sleep=_async_sleep,
            )
        finally:
            await fetcher.aclose()

    def to_normalized(self, raw: dict[str, Any]) -> RawVacancy:
        return raw_vacancy(self, raw)
