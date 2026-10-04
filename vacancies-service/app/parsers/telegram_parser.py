"""Telegram-парсер публичных каналов через Telethon.

# TODO: LLM-обогащение partial не вызывается. parse_quality считает нормализатор.
# TODO: нет интерактивного логина. Нет файла сессии — failed parse_run, воркер жив.
"""

import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, cast

from telethon.errors import FloodWaitError

from app.config import Settings
from app.enums import SourceType
from app.parsers.base import BaseParser, raw_vacancy
from app.parsers.registry import register
from app.services.normalizer import RawVacancy

Sleep = Callable[[float], Awaitable[None]]
ClientFactory = Callable[[Settings], Any]

_DEFAULT_LIMIT = 100
_MAX_LIMIT = 500
_FLOOD_ATTEMPTS = 5

_COMPANY = re.compile(
    r"^(?:компания|company|работодатель)\s*[:\-—]\s*(.+)$",
    re.IGNORECASE,
)
_CITY = re.compile(
    r"^(?:город|city|локация|location)\s*[:\-—]\s*(.+)$",
    re.IGNORECASE,
)
_SALARY = re.compile(
    r"зарплат|з/п|\bзп\b|salary|₽|руб|usd|eur|\$|€",
    re.IGNORECASE,
)
_URL = re.compile(r"https?://\S+")


class TelegramNotConfigured(Exception):  # noqa: N818 — имя из контракта этапа 11
    """Нет api_id/api_hash или файла сессии. До connect() и без интерактивного логина."""


@dataclass(frozen=True, slots=True)
class TelegramFields:
    """Поля, вытащенные регулярками из текста поста."""

    title: str
    company: str | None
    city: str | None
    salary_text: str | None
    url: str | None
    description_raw: str


def passes_keywords(text: str, keywords: Sequence[str]) -> bool:
    """Пустой список пропускает всё. Иначе достаточно одного вхождения, без регистра."""
    if not keywords:
        return True
    folded = text.casefold()
    return any(keyword.casefold() in folded for keyword in keywords)


def extract_telegram_post(text: str) -> TelegramFields:
    """Заголовок, компания, город, зарплата строкой и первая ссылка. Текст поста не меняется."""
    lines = text.splitlines()
    title = ""
    for line in lines:
        stripped = line.strip()
        if stripped:
            title = stripped[:200]
            break
    company: str | None = None
    city: str | None = None
    salary: str | None = None
    for line in lines:
        stripped = line.strip()
        if company is None:
            company_match = _COMPANY.match(stripped)
            if company_match is not None:
                company = company_match.group(1).strip() or None
        if city is None:
            city_match = _CITY.match(stripped)
            if city_match is not None:
                city = city_match.group(1).strip() or None
        if salary is None and _SALARY.search(stripped):
            salary = stripped or None
    url_match = _URL.search(text)
    url = url_match.group(0).rstrip(").,;>\"'") if url_match is not None else None
    return TelegramFields(
        title=title,
        company=company,
        city=city,
        salary_text=salary,
        url=url,
        description_raw=text,
    )


def message_limit(config: Mapping[str, Any]) -> int:
    """Нет ключа — 100, сверху 500."""
    raw = config.get("limit", _DEFAULT_LIMIT)
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        return _DEFAULT_LIMIT
    limit = int(raw)
    if limit < 1:
        return _DEFAULT_LIMIT
    return min(_MAX_LIMIT, limit)


def _flood_delay(exc: BaseException, attempt: int) -> float:
    raw = getattr(exc, "seconds", 1)
    # type() отличает bool от int: пауза считается из числа секунд FloodWait.
    base = float(raw) if type(raw) is int or type(raw) is float else 1.0
    base = max(1.0, base)
    return min(300.0, base * float(2 ** (attempt - 1)))


def _is_flood_wait(exc: BaseException) -> bool:
    """Класс ошибки читается в момент except: тест подменяет `FloodWaitError` в модуле."""
    return isinstance(exc, cast(type[BaseException], FloodWaitError))


async def call_with_flood_wait[T](op: Callable[[], Awaitable[T]], sleep: Sleep) -> T:
    """До 5 попыток. Пауза `min(300, max(1, seconds) * 2**(attempt-1))`, на 5-й проброс."""
    for attempt in range(1, _FLOOD_ATTEMPTS):
        try:
            return await op()
        except BaseException as exc:
            if not _is_flood_wait(exc):
                raise
            await sleep(_flood_delay(exc, attempt))
    return await op()


def default_client_factory(settings: Settings) -> Any:
    """Клиент Telethon по уже существующему файлу сессии. `start()` не вызывается."""
    from telethon import TelegramClient

    api_hash = settings.telegram_api_hash
    api_id = settings.telegram_api_id
    if api_hash is None or api_id is None:
        msg = "Telegram API credentials are missing"
        raise TelegramNotConfigured(msg)
    return TelegramClient(
        settings.telegram_session_name,
        api_id,
        api_hash.get_secret_value(),
    )


def _session_file(settings: Settings) -> Path:
    return Path(f"{settings.telegram_session_name}.session")


def _keywords(config: Mapping[str, Any]) -> tuple[str, ...]:
    raw = config.get("keywords_filter", ())
    if not isinstance(raw, list | tuple):
        return ()
    return tuple(item.strip() for item in raw if isinstance(item, str) and item.strip())


def _channel(config: Mapping[str, Any]) -> str:
    channel = config.get("channel")
    if not isinstance(channel, str) or not channel.strip():
        msg = "telegram source config requires channel"
        raise ValueError(msg)
    return channel.strip()


def _message_text(message: Any) -> str:
    text = getattr(message, "message", None)
    if not isinstance(text, str):
        text = getattr(message, "text", None)
    return text if isinstance(text, str) else ""


def _published(message: Any) -> datetime | None:
    date = getattr(message, "date", None)
    if not isinstance(date, datetime) or date.tzinfo is None or date.utcoffset() is None:
        return None
    return date


@register
class TelegramParser(BaseParser):
    """Публичный канал. Медиа не скачиваются, диалоги не обходятся."""

    source_type: ClassVar[SourceType] = SourceType.TELEGRAM

    def __init__(
        self,
        *,
        slug: str,
        config: Mapping[str, Any],
        settings: Settings,
        client_factory: ClientFactory | None = None,
        sleep: Sleep | None = None,
    ) -> None:
        super().__init__(slug=slug, config=config, settings=settings)
        self._client_factory = client_factory or default_client_factory
        self._sleep = sleep

    async def fetch_raw(self) -> list[dict[str, Any]]:
        self._require_configured()
        channel = _channel(self.config)
        # Фабрика только после проверок: нет ключей или файла — клиент не создаётся.
        client = self._client_factory(self.settings)
        sleep = self._sleep or _default_sleep
        try:
            await client.connect()
            return await self._read_channel(client, channel, sleep)
        finally:
            await client.disconnect()

    def to_normalized(self, raw: dict[str, Any]) -> RawVacancy:
        return raw_vacancy(self, raw)

    def _require_configured(self) -> None:
        if self.settings.telegram_api_id is None or self.settings.telegram_api_hash is None:
            msg = "Telegram API credentials are missing"
            raise TelegramNotConfigured(msg)
        if not _session_file(self.settings).is_file():
            msg = "Telegram session file is missing"
            raise TelegramNotConfigured(msg)

    async def _rpc[T](self, op: Callable[[], Awaitable[T]], sleep: Sleep) -> T:
        # Пауза FloodWait считается внутри call_with_flood_wait и сюда не дублируется.
        await sleep(self.settings.telegram_rate_limit_seconds)
        return await call_with_flood_wait(op, sleep)

    async def _read_channel(self, client: Any, channel: str, sleep: Sleep) -> list[dict[str, Any]]:
        entity = await self._rpc(lambda: client.get_entity(channel), sleep)
        username = getattr(entity, "username", None)
        if not isinstance(username, str) or not username.strip():
            msg = "канал не публичный"
            raise RuntimeError(msg)
        limit = message_limit(self.config)
        messages = await self._rpc(lambda: client.get_messages(entity, limit=limit), sleep)
        keywords = _keywords(self.config)
        rows: list[dict[str, Any]] = []
        for message in _as_messages(messages):
            text = _message_text(message)
            if not text.strip() or not passes_keywords(text, keywords):
                continue
            message_id = getattr(message, "id", None)
            if isinstance(message_id, bool) or not isinstance(message_id, int):
                continue
            fields = extract_telegram_post(text)
            rows.append(
                {
                    "external_id": f"{channel}:{message_id}",
                    "title": fields.title,
                    "company": fields.company,
                    "city": fields.city,
                    "salary_text": fields.salary_text,
                    "description_raw": fields.description_raw,
                    "url": fields.url,
                    "published_at": _published(message),
                    "channel": channel,
                    "message_id": message_id,
                }
            )
        return rows


def _as_messages(messages: Any) -> list[Any]:
    if messages is None:
        return []
    if isinstance(messages, list):
        return list(messages)
    return [messages]


async def _default_sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
