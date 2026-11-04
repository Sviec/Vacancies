"""Жизненный цикл канона: суточное гашение и перепроверка карточек hh.

Чистые правила не ходят в сеть. Запись флага делает вызывающий: задача
коммитит, этот модуль только `flush`. `last_seen_at`, `raw_payload` и
нормализатор перепроверка не меняет.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

import httpx
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Source, UserVacancyAction, Vacancy, VacancyPosting
from app.enums import SourceType, UserAction
from app.utils.errors import ExternalServiceError
from app.utils.logging import get_logger

logger = get_logger(__name__)

_RECHECK_DEFAULT = 400
_STOP_REASONS = frozenset({"missing_token", "missing_user_agent"})
_NAIVE_SEEN = datetime.min.replace(tzinfo=UTC)


class SupportsActive(Protocol):
    """Объект с флагом канона. Им пользуется и ORM `Vacancy`, и офлайн-тест."""

    is_active: bool


@dataclass(frozen=True, slots=True)
class HhRecheckTarget:
    """Одна карточка: один канон в одном источнике."""

    source_id: UUID
    vacancy_id: UUID
    external_id: str
    vacancy: SupportsActive


@dataclass(frozen=True, slots=True)
class _Pick:
    vacancy: Vacancy
    posting: VacancyPosting
    limit: int


def posting_is_stale(last_seen_at: datetime, config: object, now: datetime) -> bool:
    """Публикация устарела только при целом `stale_after_days` >= 1 и строго старом визите.

    Нет ключа, не-int, bool, 0 и отрицательное число публикацию не старят.
    Момент ровно `now - n дней` ещё свежий. Наивный `last_seen_at` не устаревает
    и не роняет прогон. `now` обязан быть timezone-aware.
    """
    _require_aware(now)
    days = _stale_days(config)
    if days is None or not _is_aware(last_seen_at):
        return False
    return last_seen_at < now - timedelta(days=days)


def canon_should_deactivate(
    postings: Sequence[tuple[datetime, object]],
    now: datetime,
) -> bool:
    """Гасить канон, только если публикация есть и устарела каждая.

    Пустой список не гасит. Нет строки `sources` — `config is None`, как отсутствие ключа.
    """
    if not postings:
        return False
    return all(posting_is_stale(seen_at, config, now) for seen_at, config in postings)


def source_config_is_hh(config: object) -> bool:
    """Перепроверять источник: `provider` ровно строка `hh`, и `demo` не `True`."""
    if not isinstance(config, Mapping):
        return False
    if config.get("demo") is True:
        return False
    provider = config.get("provider")
    return isinstance(provider, str) and provider == "hh"


def recheck_limit(value: object) -> int:
    """Как `_whole_int(..., minimum=0, default=400)`: bool и не-int дают 400, 0 — пустая пачка."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return _RECHECK_DEFAULT
    return value


def take_recheck_page(
    vacancy_ids: Sequence[UUID],
    *,
    cursor: UUID | None,
    limit: int,
) -> tuple[list[UUID], UUID | None]:
    """Срез по возрастанию `Vacancy.id`. Хвост этим прогоном не дополняется началом.

    Курсор — последний взятый id. Если взято меньше лимита, курсор сбрасывается.
    Лимит 0 оставляет курсор на месте и ничего не берёт.
    """
    ordered = sorted(set(vacancy_ids))
    if limit <= 0:
        return [], cursor
    pending = [item for item in ordered if cursor is None or item > cursor]
    taken = pending[:limit]
    if len(taken) < limit:
        return taken, None
    return taken, taken[-1]


async def deactivate_stale_canons(session: AsyncSession, now: datetime) -> int:
    """Погасить каноны, которым правило велит погаснуть. Обратно не включает. Без commit."""
    _require_aware(now)
    rows = (
        await session.execute(
            select(Vacancy, VacancyPosting.last_seen_at, Source.config)
            .join(VacancyPosting, VacancyPosting.vacancy_id == Vacancy.id)
            .outerjoin(Source, Source.slug == VacancyPosting.source)
            .order_by(Vacancy.id)
            .execution_options(populate_existing=True)
        )
    ).all()
    grouped: dict[UUID, tuple[Vacancy, list[tuple[datetime, object]]]] = {}
    for vacancy, seen_at, config in rows:
        slot = grouped.get(vacancy.id)
        if slot is None:
            grouped[vacancy.id] = (vacancy, [(seen_at, config)])
        else:
            slot[1].append((seen_at, config))
    changed = 0
    for vacancy, postings in grouped.values():
        if not canon_should_deactivate(postings, now):
            continue
        vacancy.is_active = False
        changed += 1
    await session.flush()
    return changed


async def recheck_saved_hh(
    session: AsyncSession,
    settings: Settings,
    *,
    cursors: Mapping[UUID, UUID | None],
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[UUID, UUID | None]:
    """Перепроверить сохранённые и откликнутые карточки hh. Без commit.

    Кандидат — действие `saved` или `applied` любого пользователя, публикация
    `source_type=api` и источник с тем же slug: `source_type=api`, provider `hh`.
    `demo is True` пропускается. `is_enabled=false` не исключает.
    Лимит пачки — `max_vacancies_per_run` (то же целое, что у обхода hh).
    Один канон в одном источнике — один GET публикации с максимальным `last_seen_at`.
    Курсор наружу: `source_id → uuid | None`.
    """
    grouped = await _group_hh_candidates(session)
    new_cursors: dict[UUID, UUID | None] = {}
    targets: list[HhRecheckTarget] = []
    for source_id in sorted(grouped):
        picks = grouped[source_id]
        ordered = sorted(picks)
        taken, cursor = take_recheck_page(
            ordered,
            cursor=cursors.get(source_id),
            limit=picks[ordered[0]].limit,
        )
        new_cursors[source_id] = cursor
        chosen = set(taken)
        for vacancy_id in ordered:
            if vacancy_id not in chosen:
                continue
            pick = picks[vacancy_id]
            targets.append(
                HhRecheckTarget(
                    source_id=source_id,
                    vacancy_id=vacancy_id,
                    external_id=pick.posting.external_id,
                    vacancy=pick.vacancy,
                )
            )
    if targets:
        stopped = await recheck_cards(targets, settings, transport=transport)
        if stopped:
            for source_id in {item.source_id for item in targets}:
                new_cursors[source_id] = cursors.get(source_id)
    await session.flush()
    return new_cursors


async def recheck_cards(
    targets: Sequence[HhRecheckTarget],
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bool:
    """Вердикт карточек одним `HHClient`. True — пачка остановлена, флаги как были.

    Клиент создаётся только для непустой пачки и только когда заданы токен и User-Agent.
    `httpx.AsyncClient` открывает сам `HHClient._get`.
    """
    if not targets:
        return False
    if not _hh_configured(settings):
        logger.warning("lifecycle_hh_stopped", reason="missing_credentials")
        return True

    from app.adapters.hh import HHClient

    client = HHClient(settings, transport=transport)
    previous: list[tuple[SupportsActive, bool]] = []
    for target in targets:
        try:
            payload = await client.vacancy(target.external_id)
        except ExternalServiceError as exc:
            if _stops_batch(exc):
                _restore(previous)
                logger.warning("lifecycle_hh_stopped", reason=_reason(exc) or "credentials")
                return True
            if _status_code(exc) == 404:
                _assign_active(previous, target.vacancy, active=False)
            continue
        _assign_active(previous, target.vacancy, active=payload.get("archived") is not True)
    return False


async def _group_hh_candidates(session: AsyncSession) -> dict[UUID, dict[UUID, _Pick]]:
    rows = (
        await session.execute(
            select(Vacancy, VacancyPosting, Source)
            .join(VacancyPosting, VacancyPosting.vacancy_id == Vacancy.id)
            .join(Source, Source.slug == VacancyPosting.source)
            .where(
                VacancyPosting.source_type == SourceType.API,
                Source.source_type == SourceType.API,
                # `is_enabled=false` источник не исключает: выключенный hh всё ещё
                # может держать сохранённую карточку.
                exists().where(
                    UserVacancyAction.vacancy_id == Vacancy.id,
                    UserVacancyAction.action.in_((UserAction.SAVED, UserAction.APPLIED)),
                ),
            )
            .order_by(Vacancy.id)
            .execution_options(populate_existing=True)
        )
    ).all()
    grouped: dict[UUID, dict[UUID, _Pick]] = {}
    for vacancy, posting, source in rows:
        if not source_config_is_hh(source.config):
            continue
        per_source = grouped.setdefault(source.id, {})
        current = per_source.get(vacancy.id)
        if current is not None and not _posting_is_newer(posting, current.posting):
            continue
        per_source[vacancy.id] = _Pick(
            vacancy=vacancy,
            posting=posting,
            limit=_batch_limit(source.config),
        )
    return grouped


def _batch_limit(config: object) -> int:
    if not isinstance(config, Mapping):
        return _RECHECK_DEFAULT
    return recheck_limit(config.get("max_vacancies_per_run"))


def _posting_is_newer(candidate: VacancyPosting, current: VacancyPosting) -> bool:
    return _seen_key(candidate) > _seen_key(current)


def _seen_key(posting: VacancyPosting) -> tuple[int, datetime, UUID]:
    seen = posting.last_seen_at
    if not _is_aware(seen):
        return (0, _NAIVE_SEEN, posting.id)
    return (1, seen, posting.id)


def _hh_configured(settings: Settings) -> bool:
    return settings.hh_app_token is not None and settings.hh_user_agent is not None


def _assign_active(
    previous: list[tuple[SupportsActive, bool]],
    vacancy: SupportsActive,
    *,
    active: bool,
) -> None:
    previous.append((vacancy, vacancy.is_active))
    vacancy.is_active = active


def _restore(previous: Sequence[tuple[SupportsActive, bool]]) -> None:
    for vacancy, active in reversed(previous):
        vacancy.is_active = active


def _stops_batch(exc: ExternalServiceError) -> bool:
    return _reason(exc) in _STOP_REASONS


def _reason(exc: ExternalServiceError) -> str | None:
    reason = exc.details.get("reason")
    if isinstance(reason, str):
        return reason
    return None


def _status_code(exc: ExternalServiceError) -> int | None:
    status = exc.details.get("status_code")
    if isinstance(status, bool) or not isinstance(status, int):
        return None
    return status


def _stale_days(config: object) -> int | None:
    if not isinstance(config, Mapping):
        return None
    value = config.get("stale_after_days")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def _require_aware(value: datetime) -> None:
    if not _is_aware(value):
        msg = "now must be timezone-aware"
        raise ValueError(msg)


def _is_aware(value: datetime) -> bool:
    if value.tzinfo is None:
        return False
    return value.utcoffset() is not None
