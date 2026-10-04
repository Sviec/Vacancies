"""HTML-парсер без Playwright: листинг, пагинация, robots.txt, два config на одном классе."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.config import Settings
from app.enums import SourceType
from app.parsers.config import page_delay_seconds, split_selector
from app.parsers.html_parser import (
    HtmlParser,
    fetch_html_pages,
    html_source_config,
    page_url_for,
    parse_listing,
    robots_permits,
)

FIXTURES = Path(__file__).parent / "fixtures" / "html"
NOW = datetime(2026, 10, 1, 12, tzinfo=UTC)

CAREER: dict[str, Any] = {
    "url": "https://careers.example.com/vacancies",
    "list_selector": "article.vacancy-card",
    "fields": {
        "title": "h2.vacancy-title",
        "company": ".vacancy-company",
        "city": ".vacancy-location",
        "salary": ".vacancy-salary",
        "description": ".vacancy-body",
        "url": "a.vacancy-link@href",
        "published_at": "time@datetime",
        "skills": ".vacancy-tags li",
    },
    "pagination": {"next_selector": "a.pager-next", "max_pages": 5},
    "delay_seconds": 2,
}

JOBBOARD: dict[str, Any] = {
    "url": "https://jobs.example.org/it",
    "list_selector": "div.job-item",
    "fields": {
        "title": ".job-item__title",
        "company": ".job-item__employer",
        "city": ".job-item__city",
        "salary": ".job-item__salary",
        "description": ".job-item__text",
        "url": "a.job-item__link@href",
        "published_at": ".job-item__date@data-published",
        "skills": ".job-item__skills span",
    },
    "pagination": {"page_param": "page", "max_pages": 3},
    "delay_seconds": 2,
}


class _Fetcher:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.urls: list[str] = []

    async def fetch(self, url: str) -> str:
        self.urls.append(url)
        if url not in self.pages:
            msg = f"unexpected url {url}"
            raise AssertionError(msg)
        return self.pages[url]


def _settings(**overrides: object) -> Settings:
    data: dict[str, object] = {"_env_file": None, "respect_robots_txt": True}
    data.update(overrides)
    return Settings(**data)


def test_split_selector_cuts_last_attribute() -> None:
    assert split_selector("a.link@href") == ("a.link", "href")
    assert split_selector("time@datetime") == ("time", "datetime")
    assert split_selector(".job-item__date@data-published") == (".job-item__date", "data-published")
    assert split_selector("article.vacancy-card") == ("article.vacancy-card", None)
    assert split_selector("foo@bar@href") == ("foo@bar", "href")


def test_page_delay_is_at_least_one_second() -> None:
    settings = _settings(http_request_delay_seconds=1.5)
    assert page_delay_seconds(None, settings) == 1.5
    assert page_delay_seconds(0.2, settings) == 1.0
    assert page_delay_seconds(2.0, settings) == 2.0


def test_page_url_for_sets_page_param() -> None:
    assert page_url_for("https://jobs.example.org/it", "page", 1) == (
        "https://jobs.example.org/it?page=1"
    )
    assert page_url_for("https://jobs.example.org/it?page=1", "page", 2) == (
        "https://jobs.example.org/it?page=2"
    )


def test_config_requires_url_and_list_selector_before_http() -> None:
    with pytest.raises(ValueError, match="url"):
        html_source_config({"list_selector": "article"})
    with pytest.raises(ValueError, match="list_selector"):
        html_source_config({"url": "https://example.com"})


def test_both_pagination_keys_keep_next_selector() -> None:
    config = html_source_config(
        {
            "url": "https://example.com/jobs",
            "list_selector": "article",
            "pagination": {"next_selector": "a.next", "page_param": "page", "max_pages": 4},
        }
    )
    assert config.pagination.next_selector == "a.next"
    assert config.pagination.page_param is None
    assert config.pagination.max_pages == 4


def test_missing_max_pages_is_one() -> None:
    config = html_source_config({"url": "https://example.com", "list_selector": "article"})
    assert config.pagination.max_pages == 1
    assert config.pagination.next_selector is None
    assert config.pagination.page_param is None


def test_careerhub_listing_text_links_and_skills() -> None:
    html = (FIXTURES / "careerhub_page.html").read_text(encoding="utf-8")
    config = html_source_config(CAREER)
    page_url = CAREER["url"]
    cards, nxt = parse_listing(html, page_url, config)
    assert nxt == "https://careers.example.com/vacancies?page=2"
    assert len(cards) == 2
    first = cards[0]
    assert first["title"] == "Backend Engineer"
    assert first["company"] == "Acme"
    assert first["city"] == "Berlin"
    assert first["salary_text"] == "от 200 000 руб."
    assert "salary_min" not in first
    assert first["external_id"] == "https://careers.example.com/jobs/1"
    assert first["url"] == "https://careers.example.com/jobs/1"
    assert first["published_at"] == datetime(2026, 1, 15, 10, tzinfo=UTC)
    assert first["skills_hint"] == ("Python", "SQL")
    description = first["description_raw"]
    assert "Hello" in description and "world" in description
    assert "secret" not in description
    assert "<" not in description
    second = cards[1]
    assert second["title"] == ""
    assert second["company"] is None
    assert second["external_id"] == f"{page_url}#1"
    assert second["skills_hint"] == ()


def test_jobboard_listing_attributes() -> None:
    html = (FIXTURES / "jobboard_page.html").read_text(encoding="utf-8")
    config = html_source_config(JOBBOARD)
    cards, nxt = parse_listing(html, JOBBOARD["url"], config)
    assert nxt is None
    assert len(cards) == 1
    card = cards[0]
    assert card["title"] == "QA Engineer"
    assert card["external_id"] == "https://jobs.example.org/it/42"
    assert card["published_at"] == datetime(2026, 2, 1, tzinfo=UTC)
    assert card["skills_hint"] == ("Go", "SQL")
    assert "alert" not in card["description_raw"]
    assert "<" not in card["description_raw"]


def test_skills_key_absent_omits_hint() -> None:
    html = "<article class='vacancy-card'><h2 class='vacancy-title'>Dev</h2></article>"
    raw = dict(CAREER)
    fields = dict(CAREER["fields"])
    del fields["skills"]
    raw["fields"] = fields
    cards, _nxt = parse_listing(html, CAREER["url"], html_source_config(raw))
    assert "skills_hint" not in cards[0]


def test_two_configs_one_html_parser_class() -> None:
    settings = _settings()
    career = HtmlParser(slug="html_careerhub", config=CAREER, settings=settings)
    board = HtmlParser(slug="html_jobboard", config=JOBBOARD, settings=settings)
    assert type(career) is type(board) is HtmlParser
    career_html = (FIXTURES / "careerhub_page.html").read_text(encoding="utf-8")
    board_html = (FIXTURES / "jobboard_page.html").read_text(encoding="utf-8")
    career_cards, _nxt = parse_listing(
        career_html, CAREER["url"], html_source_config(career.config)
    )
    board_cards, _nxt = parse_listing(board_html, JOBBOARD["url"], html_source_config(board.config))
    career_raw = dict(career_cards[0])
    career_raw["parsed_at"] = NOW
    career_raw["source"] = "evil"
    vacancy = career.to_normalized(career_raw)
    assert vacancy.source == "html_careerhub"
    assert vacancy.source_type is SourceType.HTML
    assert vacancy.title == "Backend Engineer"
    board_raw = dict(board_cards[0])
    board_raw["parsed_at"] = NOW
    assert board.to_normalized(board_raw).source == "html_jobboard"


def test_robots_disallow_blocks_fetcher() -> None:
    body = "User-agent: *\nDisallow: /\n"
    assert robots_permits(body, "https://jobs.example.org/it", "Mozilla") is False


async def test_disallow_does_not_call_fetcher() -> None:
    fetcher = _Fetcher({})

    async def robots_get(url: str) -> str:
        assert url == "https://jobs.example.org/robots.txt"
        return "User-agent: *\nDisallow: /\n"

    async def sleep(_seconds: float) -> None:
        raise AssertionError("sleep")

    with pytest.raises(RuntimeError, match="disallows"):
        await fetch_html_pages(
            JOBBOARD["url"],
            html_source_config(JOBBOARD),
            settings=_settings(),
            fetcher=fetcher,
            robots_get=robots_get,
            sleep=sleep,
        )
    assert fetcher.urls == []


async def test_robots_404_allows_fetch_and_other_status_does_not() -> None:
    page = (FIXTURES / "jobboard_page.html").read_text(encoding="utf-8")
    config = html_source_config({**JOBBOARD, "pagination": {"page_param": "page", "max_pages": 1}})
    fetcher = _Fetcher({"https://jobs.example.org/it?page=1": page})

    async def missing(_url: str) -> int:
        return 404

    async def sleep(_seconds: float) -> None:
        return None

    cards = await fetch_html_pages(
        JOBBOARD["url"],
        config,
        settings=_settings(),
        fetcher=fetcher,
        robots_get=missing,
        sleep=sleep,
    )
    assert len(cards) == 1
    assert fetcher.urls == ["https://jobs.example.org/it?page=1"]

    async def broken(_url: str) -> int:
        return 500

    fetcher.urls.clear()
    with pytest.raises(RuntimeError, match="status 500"):
        await fetch_html_pages(
            JOBBOARD["url"],
            config,
            settings=_settings(),
            fetcher=fetcher,
            robots_get=broken,
            sleep=sleep,
        )
    assert fetcher.urls == []


async def test_robots_network_error_does_not_fetch() -> None:
    fetcher = _Fetcher({})

    async def robots_get(_url: str) -> int:
        raise ConnectionError("down")

    async def sleep(_seconds: float) -> None:
        return None

    with pytest.raises(ConnectionError):
        await fetch_html_pages(
            JOBBOARD["url"],
            html_source_config(JOBBOARD),
            settings=_settings(),
            fetcher=fetcher,
            robots_get=robots_get,
            sleep=sleep,
        )
    assert fetcher.urls == []


async def test_respect_robots_false_skips_robots_get() -> None:
    page = "<article class='vacancy-card'><h2 class='vacancy-title'>Dev</h2></article>"
    config = html_source_config(
        {
            "url": "https://careers.example.com/vacancies",
            "list_selector": "article.vacancy-card",
            "fields": {"title": "h2.vacancy-title"},
        }
    )
    fetcher = _Fetcher({config.url: page})

    async def robots_get(_url: str) -> str:
        raise AssertionError("robots")

    async def sleep(_seconds: float) -> None:
        raise AssertionError("sleep")

    cards = await fetch_html_pages(
        config.url,
        config,
        settings=_settings(respect_robots_txt=False),
        fetcher=fetcher,
        robots_get=robots_get,
        sleep=sleep,
    )
    assert cards[0]["title"] == "Dev"
    assert fetcher.urls == [config.url]


async def test_page_param_stops_on_empty_and_delays_between_pages() -> None:
    page = (FIXTURES / "jobboard_page.html").read_text(encoding="utf-8")
    empty = "<html></html>"
    config = html_source_config(
        {**JOBBOARD, "delay_seconds": 0.2, "pagination": {"page_param": "page", "max_pages": 3}}
    )
    urls = {
        "https://jobs.example.org/it?page=1": page,
        "https://jobs.example.org/it?page=2": empty,
    }
    fetcher = _Fetcher(urls)
    slept: list[float] = []
    log: list[str] = []

    async def robots_get(_url: str) -> int:
        log.append("robots")
        return 404

    async def sleep(seconds: float) -> None:
        log.append("sleep")
        slept.append(seconds)

    async def fetch(url: str) -> str:
        log.append("fetch")
        return await fetcher.fetch(url)

    class _Wrap:
        async def fetch(self, url: str) -> str:
            return await fetch(url)

    cards = await fetch_html_pages(
        JOBBOARD["url"],
        config,
        settings=_settings(),
        fetcher=_Wrap(),
        robots_get=robots_get,
        sleep=sleep,
    )
    assert len(cards) == 1
    assert fetcher.urls == [
        "https://jobs.example.org/it?page=1",
        "https://jobs.example.org/it?page=2",
    ]
    assert slept == [1.0]
    assert log == ["robots", "fetch", "sleep", "fetch"]


async def test_next_selector_stops_without_href_repeat_or_max_pages() -> None:
    first = (FIXTURES / "careerhub_page.html").read_text(encoding="utf-8")
    second = (
        "<html><article class='vacancy-card'><h2 class='vacancy-title'>Next</h2></article></html>"
    )
    config = html_source_config(
        {
            **CAREER,
            "delay_seconds": 2,
            "pagination": {"next_selector": "a.pager-next", "max_pages": 5},
        }
    )
    start = CAREER["url"]
    nxt = "https://careers.example.com/vacancies?page=2"
    fetcher = _Fetcher({start: first, nxt: second})
    slept: list[float] = []

    async def robots_get(_url: str) -> int:
        return 404

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    cards = await fetch_html_pages(
        start,
        config,
        settings=_settings(),
        fetcher=fetcher,
        robots_get=robots_get,
        sleep=sleep,
    )
    assert [card["title"] for card in cards][:2] == ["Backend Engineer", ""]
    assert cards[-1]["title"] == "Next"
    assert fetcher.urls == [start, nxt]
    assert slept == [2.0]

    loop = "<html><a class='pager-next' href='https://careers.example.com/vacancies'>x</a></html>"
    looping = _Fetcher({start: loop})
    await fetch_html_pages(
        start,
        html_source_config(
            {**CAREER, "pagination": {"next_selector": "a.pager-next", "max_pages": 5}}
        ),
        settings=_settings(respect_robots_txt=False),
        fetcher=looping,
        robots_get=robots_get,
        sleep=sleep,
    )
    assert looping.urls == [start]

    limited = _Fetcher({start: first, nxt: second})
    slept.clear()
    await fetch_html_pages(
        start,
        html_source_config(
            {**CAREER, "pagination": {"next_selector": "a.pager-next", "max_pages": 1}}
        ),
        settings=_settings(respect_robots_txt=False),
        fetcher=limited,
        robots_get=robots_get,
        sleep=sleep,
    )
    assert limited.urls == [start]
    assert slept == []
