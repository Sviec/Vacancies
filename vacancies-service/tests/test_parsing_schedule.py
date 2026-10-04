"""Расписание планировщика: флаг, демо, тип и интервал."""

import uuid

import app.parsers  # регистрация HTML и Telegram
from app.config import Settings
from app.db.models import Source
from app.enums import SourceType
from app.parsers.config import schedules_for

_ = app.parsers.HtmlParser


def _source(**overrides: object) -> Source:
    data: dict[str, object] = {
        "id": uuid.uuid4(),
        "slug": "html_live",
        "source_type": SourceType.HTML,
        "config": {"url": "https://jobs.example.org/it"},
        "is_enabled": True,
    }
    data.update(overrides)
    return Source(**data)


def test_schedules_empty_when_parsers_disabled() -> None:
    settings = Settings(_env_file=None, parsers_enabled=False)
    assert schedules_for([_source()], settings) == []


def test_schedules_skip_demo_disabled_and_api() -> None:
    settings = Settings(_env_file=None, parsers_enabled=True, parser_default_interval_hours=3)
    live = _source(slug="live")
    demo = _source(slug="demo", config={"demo": True, "url": "https://example.com"})
    disabled = _source(slug="off", is_enabled=False)
    api = _source(slug="api", source_type=SourceType.API, config={"url": "https://api"})
    specs = schedules_for([live, demo, disabled, api], settings)
    assert [spec.source_id for spec in specs] == [live.id]


def test_interval_hours_and_default() -> None:
    settings = Settings(_env_file=None, parsers_enabled=True, parser_default_interval_hours=4)
    with_hours = _source(slug="hours", config={"interval_hours": 3})
    missing = _source(slug="default", config={})
    short = _source(slug="short", config={"interval_hours": 0})
    specs = {
        spec.source_id: spec.interval_seconds
        for spec in schedules_for([with_hours, missing, short], settings)
    }
    assert specs[with_hours.id] == 10800
    assert specs[missing.id] == settings.parser_default_interval_hours * 3600
    assert specs[short.id] == settings.parser_default_interval_hours * 3600
