"""Запись нормализованных публикаций в БД: upsert публикации и склейка в канон.

Граница транзакции — не здесь. Модуль только `flush`-ит, каждая запись идёт в
собственном SAVEPOINT (`session.begin_nested()`), поэтому битая запись
откатывается одна, а батч продолжается. `commit` делает оркестратор: задача
парсинга источника (этап 11) или seed (этап 7).

Идентичность публикации — `(source, external_id)` и `(source, content_hash)`;
склейка публикаций в каноническую вакансию — по `dedup_key` (sha256
нормализованной тройки company|title|city). Канон — плоская проекция
публикации-победителя плюс агрегаты (`published_at` = MIN, `last_seen_at` = MAX,
`postings_count`).

Все чтения — явные SELECT с `populate_existing`: после отката SAVEPOINT объекты
в identity map могут оказаться expired, а ленивая дозагрузка атрибута в
async-сессии падает с MissingGreenlet.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Vacancy, VacancyPosting
from app.schemas.normalized import NormalizedVacancy
from app.services.normalizer import (
    RawVacancy,
    WinnerCandidate,
    compute_dedup_key,
    normalize_vacancy,
    pick_winner,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

# TODO: ingest не коммитит — см. docstring модуля; забытый commit у вызывающего
# означает потерю всего батча при закрытии сессии.

# TODO: гонка двух воркеров по одному (source, external_id) не закрыта:
# IntegrityError второго уходит в errors батча. Держится на правиле «одно
# RQ-задание на источник»; гонка по dedup_key закрыта ON CONFLICT + FOR UPDATE.

_CANONICAL_FIELDS = (
    "title",
    "company",
    "description_clean",
    "url",
    "source",
    "source_type",
    "country",
    "city",
    "work_format",
    "relocation_support",
    "salary_min",
    "salary_max",
    "salary_currency",
    "salary_period",
    "salary_is_gross",
    "skills",
    "experience_min_years",
    "experience_level",
    "employment_type",
    "education_required",
    "languages",
    "parse_quality",
)


class IngestStatus(StrEnum):
    """Что произошло с публикацией при записи."""

    CREATED_VACANCY = "created_vacancy"
    MERGED_INTO_EXISTING = "merged_into_existing"
    POSTING_SEEN_AGAIN = "posting_seen_again"
    POSTING_UPDATED = "posting_updated"
    POSTING_EDIT_IGNORED = "posting_edit_ignored"
    DUPLICATE_CONTENT = "duplicate_content"


@dataclass(frozen=True, slots=True)
class IngestResult:
    """Итог записи одной публикации."""

    vacancy_id: uuid.UUID
    posting_id: uuid.UUID
    status: IngestStatus

    @property
    def is_new(self) -> bool:
        """Появилась новая публикация (для `parse_runs.items_new`)."""
        return self.status in (IngestStatus.CREATED_VACANCY, IngestStatus.MERGED_INTO_EXISTING)


@dataclass(frozen=True, slots=True)
class IngestError:
    """Публикация, запись которой откатилась; батч при этом продолжился."""

    index: int
    source: str
    external_id: str
    error_type: str
    message: str


@dataclass(frozen=True, slots=True)
class BatchIngestResult:
    """Итог батча; `items_found`/`items_new` — ровно поля `parse_runs`."""

    results: tuple[IngestResult, ...]
    errors: tuple[IngestError, ...]
    items_found: int
    items_new: int


def _canonical_values(vacancy: NormalizedVacancy) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for name in _CANONICAL_FIELDS:
        value = getattr(vacancy, name)
        values[name] = list(value) if isinstance(value, list) else value
    return values


def _apply_canonical(canon: Vacancy, vacancy: NormalizedVacancy) -> None:
    for name, value in _canonical_values(vacancy).items():
        setattr(canon, name, value)


def _candidate(item: VacancyPosting | NormalizedVacancy) -> WinnerCandidate:
    return WinnerCandidate(
        source=item.source,
        external_id=item.external_id,
        parse_quality=item.parse_quality,
        description_length=len(item.description_clean),
        published_at=item.published_at,
    )


def _same_posting(left: WinnerCandidate, right: WinnerCandidate) -> bool:
    return (left.source, left.external_id) == (right.source, right.external_id)


def _later(current: datetime, seen_at: datetime) -> datetime:
    return max(current, seen_at)


def _new_posting(
    vacancy_id: uuid.UUID, vacancy: NormalizedVacancy, seen_at: datetime
) -> VacancyPosting:
    return VacancyPosting(
        id=uuid.uuid4(),
        vacancy_id=vacancy_id,
        source=vacancy.source,
        source_type=vacancy.source_type,
        external_id=vacancy.external_id,
        url=vacancy.url,
        title=vacancy.title,
        company=vacancy.company,
        description_raw=vacancy.description_raw,
        description_clean=vacancy.description_clean,
        published_at=vacancy.published_at,
        parsed_at=vacancy.parsed_at,
        parse_quality=vacancy.parse_quality,
        content_hash=vacancy.content_hash,
        raw_payload=dict(vacancy.raw_payload),
        last_seen_at=seen_at,
    )


def _update_posting(posting: VacancyPosting, vacancy: NormalizedVacancy) -> None:
    posting.title = vacancy.title
    posting.company = vacancy.company
    posting.description_raw = vacancy.description_raw
    posting.description_clean = vacancy.description_clean
    posting.published_at = vacancy.published_at
    posting.parsed_at = vacancy.parsed_at
    posting.parse_quality = vacancy.parse_quality
    posting.content_hash = vacancy.content_hash
    # Новый dict, а не правка на месте: изменение JSONB на месте ORM не видит.
    posting.raw_payload = dict(vacancy.raw_payload)
    posting.url = vacancy.url


def _raw_from_posting(posting: VacancyPosting, canon: Vacancy) -> RawVacancy:
    # Город и страна берутся из канона: у всех публикаций канона один
    # нормализованный город (он входит в dedup_key), а в публикации его нет.
    return RawVacancy(
        external_id=posting.external_id,
        source=posting.source,
        source_type=posting.source_type,
        title=posting.title,
        description_raw=posting.description_raw,
        parsed_at=posting.parsed_at,
        url=posting.url,
        company=posting.company,
        city=canon.city,
        country=canon.country,
        published_at=posting.published_at,
        raw_payload=dict(posting.raw_payload),
    )


async def _lock_posting(
    session: AsyncSession,
    source: str,
    *,
    external_id: str | None = None,
    content_hash: str | None = None,
) -> VacancyPosting | None:
    stmt = select(VacancyPosting).where(VacancyPosting.source == source)
    if external_id is not None:
        stmt = stmt.where(VacancyPosting.external_id == external_id)
    if content_hash is not None:
        stmt = stmt.where(VacancyPosting.content_hash == content_hash)
    stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return (await session.execute(stmt)).scalar_one_or_none()


async def _lock_canon_by_id(session: AsyncSession, vacancy_id: uuid.UUID) -> Vacancy:
    stmt = (
        select(Vacancy)
        .where(Vacancy.id == vacancy_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return (await session.execute(stmt)).scalar_one()


async def _lock_canon_by_key(session: AsyncSession, dedup_key: str) -> Vacancy:
    stmt = (
        select(Vacancy)
        .where(Vacancy.dedup_key == dedup_key)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return (await session.execute(stmt)).scalar_one()


async def _content_hash_taken(
    session: AsyncSession, source: str, content_hash: str, exclude_id: uuid.UUID
) -> bool:
    stmt = select(VacancyPosting.id).where(
        VacancyPosting.source == source,
        VacancyPosting.content_hash == content_hash,
        VacancyPosting.id != exclude_id,
    )
    return (await session.execute(stmt.limit(1))).scalar_one_or_none() is not None


async def _recompute_canon(
    session: AsyncSession,
    canon: Vacancy,
    *,
    incoming: NormalizedVacancy,
    incoming_posting: VacancyPosting,
    previous: WinnerCandidate | None,
) -> None:
    """Пересчитать агрегаты канона и, если сменился победитель, его поля.

    `previous` — состояние отредактированной публикации до правки; `None` для
    новой публикации. `dedup_key` канона не меняется никогда.
    """
    stmt = (
        select(VacancyPosting)
        .where(VacancyPosting.vacancy_id == canon.id)
        .order_by(VacancyPosting.source, VacancyPosting.external_id)
        .execution_options(populate_existing=True)
    )
    postings = list((await session.execute(stmt)).scalars().all())
    candidates = [_candidate(posting) for posting in postings]
    new_winner = pick_winner(candidates)

    canon.postings_count = len(postings)
    dates = [posting.published_at for posting in postings if posting.published_at is not None]
    canon.published_at = min(dates) if dates else None
    canon.last_seen_at = max([canon.last_seen_at, *(posting.last_seen_at for posting in postings)])

    incoming_candidate = _candidate(incoming_posting)
    if _same_posting(new_winner, incoming_candidate):
        _apply_canonical(canon, incoming)
    elif previous is not None:
        others = [c for c in candidates if not _same_posting(c, incoming_candidate)]
        previous_winner = pick_winner([*others, previous])
        if not _same_posting(previous_winner, new_winner):
            # TODO: отредактированный победитель перестал им быть — канон
            # перенормализуется из сохранённых входов нового победителя; явные
            # структурные поля источника (зарплата, навыки из API) теряются.
            winner_posting = next(
                posting
                for posting, candidate in zip(postings, candidates, strict=True)
                if _same_posting(candidate, new_winner)
            )
            _apply_canonical(canon, normalize_vacancy(_raw_from_posting(winner_posting, canon)))
    await session.flush()


async def _ingest_one(
    session: AsyncSession, vacancy: NormalizedVacancy, seen_at: datetime
) -> IngestResult:
    dedup_key, dedup_key_raw = compute_dedup_key(vacancy.company, vacancy.title, vacancy.city)

    existing = await _lock_posting(session, vacancy.source, external_id=vacancy.external_id)
    if existing is not None:
        canon = await _lock_canon_by_id(session, existing.vacancy_id)
        existing.last_seen_at = _later(existing.last_seen_at, seen_at)
        canon.last_seen_at = _later(canon.last_seen_at, seen_at)

        if existing.content_hash == vacancy.content_hash:
            await session.flush()
            return IngestResult(canon.id, existing.id, IngestStatus.POSTING_SEEN_AGAIN)

        if dedup_key != canon.dedup_key or await _content_hash_taken(
            session, vacancy.source, vacancy.content_hash, existing.id
        ):
            # TODO: правка, сменившая ключ склейки или совпавшая по тексту с
            # другой публикацией источника, не применяется — только last_seen_at;
            # перенос публикации между канонами не реализован.
            logger.warning(
                "posting_edit_ignored",
                source=vacancy.source,
                external_id=vacancy.external_id,
                key_changed=dedup_key != canon.dedup_key,
            )
            await session.flush()
            return IngestResult(canon.id, existing.id, IngestStatus.POSTING_EDIT_IGNORED)

        previous = _candidate(existing)
        _update_posting(existing, vacancy)
        await session.flush()
        await _recompute_canon(
            session, canon, incoming=vacancy, incoming_posting=existing, previous=previous
        )
        return IngestResult(canon.id, existing.id, IngestStatus.POSTING_UPDATED)

    duplicate = await _lock_posting(session, vacancy.source, content_hash=vacancy.content_hash)
    if duplicate is not None:
        canon = await _lock_canon_by_id(session, duplicate.vacancy_id)
        duplicate.last_seen_at = _later(duplicate.last_seen_at, seen_at)
        canon.last_seen_at = _later(canon.last_seen_at, seen_at)
        await session.flush()
        return IngestResult(canon.id, duplicate.id, IngestStatus.DUPLICATE_CONTENT)

    insert_stmt = (
        pg_insert(Vacancy)
        .values(
            id=uuid.uuid4(),
            dedup_key=dedup_key,
            dedup_key_raw=dedup_key_raw,
            **_canonical_values(vacancy),
            published_at=vacancy.published_at,
            last_seen_at=seen_at,
            postings_count=1,
        )
        .on_conflict_do_nothing(index_elements=["dedup_key"])
        .returning(Vacancy.id)
    )
    new_id = (await session.execute(insert_stmt)).scalar_one_or_none()
    if new_id is not None:
        posting = _new_posting(new_id, vacancy, seen_at)
        session.add(posting)
        await session.flush()
        return IngestResult(new_id, posting.id, IngestStatus.CREATED_VACANCY)

    if dedup_key is None:
        msg = "ON CONFLICT on a NULL dedup_key is impossible: NULLs never conflict"
        raise RuntimeError(msg)
    canon = await _lock_canon_by_key(session, dedup_key)
    posting = _new_posting(canon.id, vacancy, seen_at)
    session.add(posting)
    await session.flush()
    await _recompute_canon(
        session, canon, incoming=vacancy, incoming_posting=posting, previous=None
    )
    return IngestResult(canon.id, posting.id, IngestStatus.MERGED_INTO_EXISTING)


async def ingest_vacancy(
    session: AsyncSession, vacancy: NormalizedVacancy, *, seen_at: datetime | None = None
) -> IngestResult:
    """Записать одну публикацию в собственном SAVEPOINT. Не коммитит.

    `seen_at` по умолчанию — `vacancy.parsed_at`.
    """
    # TODO: ingest не перенормализует переданный NormalizedVacancy: seed и
    # парсеры обязаны строить его через RawVacancy → normalize_vacancy.
    moment = seen_at or vacancy.parsed_at
    if moment.tzinfo is None or moment.utcoffset() is None:
        msg = "seen_at must be timezone-aware"
        raise ValueError(msg)
    async with session.begin_nested():
        return await _ingest_one(session, vacancy, moment)


async def ingest_batch(
    session: AsyncSession,
    vacancies: Sequence[NormalizedVacancy],
    *,
    seen_at: datetime | None = None,
) -> BatchIngestResult:
    """Записать батч; ошибка одной публикации откатывает только её SAVEPOINT."""
    results: list[IngestResult] = []
    errors: list[IngestError] = []
    for index, vacancy in enumerate(vacancies):
        try:
            results.append(await ingest_vacancy(session, vacancy, seen_at=seen_at))
        except Exception as exc:
            error = IngestError(
                index=index,
                source=vacancy.source,
                external_id=vacancy.external_id,
                error_type=type(exc).__name__,
                message=str(exc)[:500],
            )
            errors.append(error)
            logger.warning(
                "ingest_failed",
                index=index,
                source=error.source,
                external_id=error.external_id,
                error_type=error.error_type,
            )
    return BatchIngestResult(
        results=tuple(results),
        errors=tuple(errors),
        items_found=len(vacancies),
        items_new=sum(1 for result in results if result.is_new),
    )
