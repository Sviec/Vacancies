"""Telegram-парсер без сети: regex, flood wait, отсутствие ключей и файла сессии."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.config import Settings
from app.enums import SourceType
from app.parsers import telegram_parser
from app.parsers.telegram_parser import (
    TelegramNotConfigured,
    TelegramParser,
    call_with_flood_wait,
    extract_telegram_post,
    passes_keywords,
)

NOW = datetime(2026, 10, 1, 12, tzinfo=UTC)
POST = (
    "Senior Python\n"
    "\n"
    "Компания: Acme Corp\n"
    "Город: Берлин\n"
    "Зарплата: от 200 000 руб.\n"
    "https://example.com/job/1).\n"
    "Пишем на Python.\n"
)


def test_passes_keywords() -> None:
    assert passes_keywords("что угодно", []) is True
    assert passes_keywords("Remote job", ["remote"]) is True
    assert passes_keywords("Офис", ["remote"]) is False
    assert passes_keywords("РЕЛОКАЦИЯ в ЕС", ["релокация"]) is True


def test_extract_telegram_post() -> None:
    fields = extract_telegram_post(POST)
    assert fields.title == "Senior Python"
    assert fields.company == "Acme Corp"
    assert fields.city == "Берлин"
    assert fields.salary_text == "Зарплата: от 200 000 руб."
    assert fields.url == "https://example.com/job/1"
    assert fields.description_raw == POST
    empty = extract_telegram_post("")
    assert empty.title == ""
    assert empty.company is None
    assert empty.url is None
    long_title = extract_telegram_post("Я" * 250)
    assert len(long_title.title) == 200


class _FloodWaitError(Exception):
    def __init__(self, seconds: int) -> None:
        super().__init__(seconds)
        self.seconds = seconds


async def test_flood_wait_backoff_and_fifth_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(telegram_parser, "FloodWaitError", _FloodWaitError)
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    calls = 0

    async def succeed() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise _FloodWaitError(2)
        return "ok"

    assert await call_with_flood_wait(succeed, sleep) == "ok"
    assert slept == [2.0, 4.0]

    slept.clear()

    async def always() -> None:
        raise _FloodWaitError(200)

    with pytest.raises(_FloodWaitError):
        await call_with_flood_wait(always, sleep)
    assert slept == [200.0, 300.0, 300.0, 300.0]


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    data: dict[str, object] = {
        "_env_file": None,
        "telegram_api_id": 1,
        "telegram_api_hash": "hash",
        "telegram_session_name": str(tmp_path / "vacancies"),
        "telegram_rate_limit_seconds": 2.0,
    }
    data.update(overrides)
    return Settings(**data)


class _Entity:
    def __init__(self, username: str | None) -> None:
        self.username = username


class _Message:
    def __init__(self, message_id: int, text: str) -> None:
        self.id = message_id
        self.message = text
        self.date = NOW


class _Client:
    def __init__(
        self, username: str | None = "it_jobs", messages: list[_Message] | None = None
    ) -> None:
        self.username = username
        self.messages = messages if messages is not None else [_Message(7, POST)]
        self.connected = False
        self.disconnected = False
        self.limits: list[int] = []
        self.entities: list[str] = []

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.disconnected = True

    async def get_entity(self, channel: str) -> _Entity:
        self.entities.append(channel)
        return _Entity(self.username)

    async def get_messages(self, _entity: object, limit: int) -> list[_Message]:
        self.limits.append(limit)
        return self.messages


async def test_missing_credentials_do_not_build_client(tmp_path: Path) -> None:
    calls: list[Settings] = []

    def factory(settings: Settings) -> _Client:
        calls.append(settings)
        raise AssertionError("factory")

    parser = TelegramParser(
        slug="tg_live",
        config={"channel": "@it_jobs"},
        settings=Settings(_env_file=None),
        client_factory=factory,
    )
    with pytest.raises(TelegramNotConfigured, match="credentials"):
        await parser.fetch_raw()
    assert calls == []

    session = _settings(tmp_path, telegram_session_name=str(tmp_path / "missing"))
    parser = TelegramParser(
        slug="tg_live",
        config={"channel": "@it_jobs"},
        settings=session,
        client_factory=factory,
    )
    with pytest.raises(TelegramNotConfigured, match="session"):
        await parser.fetch_raw()
    assert calls == []


async def test_fetch_uses_fake_client(tmp_path: Path) -> None:
    (tmp_path / "vacancies.session").write_bytes(b"session")
    client = _Client(
        messages=[
            _Message(7, POST),
            _Message(8, "просто болтовня"),
            _Message(9, ""),
        ]
    )
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    parser = TelegramParser(
        slug="tg_live",
        config={"channel": "@it_jobs", "limit": 900, "keywords_filter": ["python"]},
        settings=_settings(tmp_path),
        client_factory=lambda _settings: client,
        sleep=sleep,
    )
    rows = await parser.fetch_raw()
    assert client.connected is True
    assert client.disconnected is True
    assert client.entities == ["@it_jobs"]
    assert client.limits == [500]
    assert slept == [2.0, 2.0]
    assert len(rows) == 1
    assert rows[0]["external_id"] == "@it_jobs:7"
    assert rows[0]["title"] == "Senior Python"
    assert "skills_hint" not in rows[0]
    raw = dict(rows[0])
    raw["parsed_at"] = NOW
    raw["source"] = "evil"
    vacancy = parser.to_normalized(raw)
    assert vacancy.source == "tg_live"
    assert vacancy.source_type is SourceType.TELEGRAM
    assert vacancy.company == "Acme Corp"
    assert vacancy.external_id == "@it_jobs:7"


async def test_private_channel_does_not_list_dialogs(tmp_path: Path) -> None:
    (tmp_path / "vacancies.session").write_bytes(b"session")
    client = _Client(username=None)

    async def sleep(_seconds: float) -> None:
        return None

    parser = TelegramParser(
        slug="tg_live",
        config={"channel": "@hidden"},
        settings=_settings(tmp_path),
        client_factory=lambda _settings: client,
        sleep=sleep,
    )
    with pytest.raises(RuntimeError, match="не публичный"):
        await parser.fetch_raw()
    assert client.limits == []
    assert client.disconnected is True


async def test_default_limit_is_100(tmp_path: Path) -> None:
    (tmp_path / "vacancies.session").write_bytes(b"session")
    client = _Client(messages=[])

    async def sleep(_seconds: float) -> None:
        return None

    parser = TelegramParser(
        slug="tg_live",
        config={"channel": "@it_jobs"},
        settings=_settings(tmp_path),
        client_factory=lambda _settings: client,
        sleep=sleep,
    )
    assert await parser.fetch_raw() == []
    assert client.limits == [100]


def test_to_normalized_does_not_need_network() -> None:
    parser = TelegramParser(
        slug="tg_live",
        config={"channel": "@it_jobs"},
        settings=Settings(_env_file=None),
    )
    vacancy = parser.to_normalized(
        {
            "external_id": "@it_jobs:1",
            "title": "",
            "company": None,
            "description_raw": "",
            "parsed_at": NOW,
            "source": "other",
        }
    )
    assert vacancy.title == ""
    assert vacancy.company is None
    assert vacancy.source == "tg_live"
