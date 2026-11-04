"""Каталог публикаций hh в `vacancy_postings`. Без HTTP и без нормализатора.

Курсор обхода — максимальный `published_at` источника. Отпечаток известной
карточки — `name`, `salary_range` и `employer` (только `id` и `name`) из
`raw_payload`. Сравнение отпечатка каноническим JSON делает парсер.
"""

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, TypedDict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Vacancy, VacancyPosting


class HhListing(TypedDict):
    """Поля выдачи, по которым решаем, качать ли карточку заново."""

    name: str | None
    salary_range: Any
    employer: dict[str, Any] | None


def employer_view(value: object) -> dict[str, Any] | None:
    """Из работодателя оставить только `id` и `name`."""
    if not isinstance(value, Mapping):
        return None
    return {"id": value.get("id"), "name": value.get("name")}


def canonical_json(value: object) -> str:
    """Стабильная JSON-строка: порядок ключей не влияет на сравнение."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def listing_from_payload(payload: object) -> HhListing:
    """Отпечаток из `raw_payload` карточки. Чужой JSON не роняет загрузку."""
    data = payload if isinstance(payload, Mapping) else {}
    name = data.get("name")
    return {
        "name": name if isinstance(name, str) else None,
        "salary_range": data.get("salary_range"),
        "employer": employer_view(data.get("employer")),
    }


def same_hh_listing(item: Mapping[str, Any], known: Mapping[str, Any]) -> bool:
    """Выдача совпала с каталогом: имя — строка, зарплата и работодатель — JSON."""
    name = item.get("name")
    if not isinstance(name, str) or name != known.get("name"):
        return False
    if canonical_json(item.get("salary_range")) != canonical_json(known.get("salary_range")):
        return False
    return canonical_json(employer_view(item.get("employer"))) == canonical_json(
        employer_view(known.get("employer"))
    )


def _json_default(value: object) -> str:
    return str(value)


async def load_hh_postings(
    session: AsyncSession, slug: str
) -> tuple[datetime | None, dict[str, HhListing]]:
    """Курсор и известные `external_id` источника. Чужие slug не читаются."""
    cursor = await session.scalar(
        select(func.max(VacancyPosting.published_at)).where(VacancyPosting.source == slug)
    )
    published_at = cursor if isinstance(cursor, datetime) else None
    rows = (
        await session.execute(
            select(VacancyPosting.external_id, VacancyPosting.raw_payload).where(
                VacancyPosting.source == slug
            )
        )
    ).all()
    known: dict[str, HhListing] = {}
    for external_id, payload in rows:
        known[str(external_id)] = listing_from_payload(payload)
    return published_at, known


async def touch_hh_seen(
    session: AsyncSession,
    slug: str,
    external_ids: Sequence[str],
    seen_at: datetime,
) -> int:
    """Поднять `last_seen_at` публикации и канона до `seen_at` и включить канон.

    `content_hash`, `raw_payload` и текст не меняются, нормализатор не вызывается.
    Возвращает число найденных публикаций. Без commit.
    """
    unique = list(dict.fromkeys(external_ids))
    if not unique:
        return 0
    rows = (
        await session.execute(
            select(VacancyPosting, Vacancy)
            .join(Vacancy, Vacancy.id == VacancyPosting.vacancy_id)
            .where(
                VacancyPosting.source == slug,
                VacancyPosting.external_id.in_(unique),
            )
        )
    ).all()
    for posting, canon in rows:
        posting.last_seen_at = max(posting.last_seen_at, seen_at)
        canon.last_seen_at = max(canon.last_seen_at, seen_at)
        canon.is_active = True
    await session.flush()
    return len(rows)
