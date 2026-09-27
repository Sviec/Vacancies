"""Запись публикаций в живой PostgreSQL: склейка, повторы, правки, батч."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Vacancy, VacancyPosting
from app.enums import ParseQuality
from app.schemas.normalized import NormalizedVacancy
from app.services.ingest import (
    _CANONICAL_FIELDS,
    IngestStatus,
    ingest_batch,
    ingest_vacancy,
)
from factories import PARSED_AT, make_normalized

pytestmark = pytest.mark.integration

DAY = timedelta(days=1)
EARLY = datetime(2026, 8, 1, 9, tzinfo=UTC)
LATE = datetime(2026, 8, 20, 9, tzinfo=UTC)
LONG_DESCRIPTION = (
    "Ищем сильного Python-разработчика в команду поиска Яндекса.\n"
    "Стек: FastAPI, PostgreSQL, Kafka, Docker, Kubernetes.\n"
    "Задачи: проектирование сервисов, код-ревью, менторство.\n"
    "Удалёнка, полная занятость."
)


async def _counts(session: AsyncSession) -> tuple[int, int]:
    vacancies = await session.scalar(select(func.count()).select_from(Vacancy))
    postings = await session.scalar(select(func.count()).select_from(VacancyPosting))
    return int(vacancies or 0), int(postings or 0)


async def _canon(session: AsyncSession, vacancy_id: uuid.UUID) -> Vacancy:
    stmt = select(Vacancy).where(Vacancy.id == vacancy_id)
    return (await session.execute(stmt.execution_options(populate_existing=True))).scalar_one()


async def _posting(session: AsyncSession, posting_id: uuid.UUID) -> VacancyPosting:
    stmt = select(VacancyPosting).where(VacancyPosting.id == posting_id)
    return (await session.execute(stmt.execution_options(populate_existing=True))).scalar_one()


def _other_channel(**overrides: Any) -> NormalizedVacancy:
    defaults: dict[str, Any] = {
        "source": "tg_other_jobs",
        "external_id": "555",
        "url": "https://t.me/other_jobs/555",
    }
    return make_normalized(**{**defaults, **overrides})


async def test_new_vacancy_creates_canon(db_session: AsyncSession) -> None:
    vacancy = make_normalized()
    result = await ingest_vacancy(db_session, vacancy)

    assert result.status == IngestStatus.CREATED_VACANCY
    assert result.is_new
    assert await _counts(db_session) == (1, 1)
    canon = await _canon(db_session, result.vacancy_id)
    assert canon.postings_count == 1
    assert canon.dedup_key is not None
    assert len(canon.dedup_key) == 64
    assert int(canon.dedup_key, 16) >= 0
    assert canon.dedup_key_raw == "яндекс|senior python developer|москва"
    for name in _CANONICAL_FIELDS:
        assert getattr(canon, name) == getattr(vacancy, name), name
    assert canon.last_seen_at == PARSED_AT
    posting = await _posting(db_session, result.posting_id)
    assert posting.content_hash == vacancy.content_hash
    assert posting.last_seen_at == PARSED_AT


async def test_same_posting_seen_again(db_session: AsyncSession) -> None:
    vacancy = make_normalized()
    first = await ingest_vacancy(db_session, vacancy)

    again = await ingest_vacancy(db_session, vacancy, seen_at=PARSED_AT + DAY)
    assert again.status == IngestStatus.POSTING_SEEN_AGAIN
    assert not again.is_new
    assert (again.vacancy_id, again.posting_id) == (first.vacancy_id, first.posting_id)
    assert await _counts(db_session) == (1, 1)
    assert (await _posting(db_session, first.posting_id)).last_seen_at == PARSED_AT + DAY
    assert (await _canon(db_session, first.vacancy_id)).last_seen_at == PARSED_AT + DAY

    await ingest_vacancy(db_session, vacancy, seen_at=PARSED_AT - DAY)
    assert (await _posting(db_session, first.posting_id)).last_seen_at == PARSED_AT + DAY
    assert (await _canon(db_session, first.vacancy_id)).last_seen_at == PARSED_AT + DAY


async def test_rewritten_posting_from_other_channel_merges(db_session: AsyncSession) -> None:
    first = make_normalized(published_at=EARLY)
    second = _other_channel(description_raw=LONG_DESCRIPTION, published_at=LATE)
    created = await ingest_vacancy(db_session, first)

    merged = await ingest_vacancy(db_session, second)
    assert merged.status == IngestStatus.MERGED_INTO_EXISTING
    assert merged.is_new
    assert merged.vacancy_id == created.vacancy_id
    assert await _counts(db_session) == (1, 2)
    canon = await _canon(db_session, created.vacancy_id)
    assert canon.postings_count == 2
    assert canon.published_at == EARLY
    assert canon.description_clean == second.description_clean
    assert canon.source == "tg_other_jobs"
    assert canon.url == "https://t.me/other_jobs/555"


async def test_partial_does_not_displace_full(db_session: AsyncSession) -> None:
    full = make_normalized()
    partial = _other_channel().model_copy(
        update={
            "parse_quality": ParseQuality.PARTIAL,
            "description_clean": "x" * 5000,
            "content_hash": "f" * 64,
        }
    )
    created = await ingest_vacancy(db_session, full)
    merged = await ingest_vacancy(db_session, partial)

    assert merged.status == IngestStatus.MERGED_INTO_EXISTING
    canon = await _canon(db_session, created.vacancy_id)
    assert canon.description_clean == full.description_clean
    assert canon.parse_quality == ParseQuality.FULL
    assert canon.postings_count == 2


async def test_without_company_never_merges(db_session: AsyncSession) -> None:
    first = await ingest_vacancy(db_session, make_normalized(company=None))
    second = await ingest_vacancy(db_session, _other_channel(company=None))

    assert first.status == second.status == IngestStatus.CREATED_VACANCY
    assert first.vacancy_id != second.vacancy_id
    keys = (await db_session.execute(select(Vacancy.dedup_key, Vacancy.dedup_key_raw))).all()
    assert [tuple(row) for row in keys] == [(None, None), (None, None)]


async def test_repost_with_same_content_in_same_source(db_session: AsyncSession) -> None:
    original = make_normalized()
    created = await ingest_vacancy(db_session, original)
    repost = make_normalized(external_id="101", url="https://t.me/python_jobs/101")
    assert repost.content_hash == original.content_hash

    result = await ingest_vacancy(db_session, repost, seen_at=PARSED_AT + DAY)
    assert result.status == IngestStatus.DUPLICATE_CONTENT
    assert result.posting_id == created.posting_id
    assert await _counts(db_session) == (1, 1)
    assert (await _posting(db_session, created.posting_id)).last_seen_at == PARSED_AT + DAY
    assert (await _canon(db_session, created.vacancy_id)).last_seen_at == PARSED_AT + DAY


async def test_batch_survives_broken_item(db_session: AsyncSession) -> None:
    good = make_normalized(external_id="1")
    broken = make_normalized(external_id="2", company="Другая").model_copy(
        update={"title": "x" * 600}
    )
    third = make_normalized(external_id="3", company="Третья")

    batch = await ingest_batch(db_session, [good, broken, third])
    assert batch.items_found == 3
    assert batch.items_new == 2
    assert len(batch.results) == 2
    assert len(batch.errors) == 1
    error = batch.errors[0]
    assert (error.index, error.source, error.external_id) == (1, good.source, "2")
    assert error.error_type
    assert await _counts(db_session) == (2, 2)

    # Сессия и объекты identity map пригодны после отката SAVEPOINT.
    again = await ingest_vacancy(db_session, good, seen_at=PARSED_AT + DAY)
    assert again.status == IngestStatus.POSTING_SEEN_AGAIN


async def _snapshot(session: AsyncSession) -> dict[str, Any]:
    rows = (
        (await session.execute(select(Vacancy).execution_options(populate_existing=True)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    canon = rows[0]
    names = (
        *_CANONICAL_FIELDS,
        "published_at",
        "last_seen_at",
        "postings_count",
        "dedup_key",
        "dedup_key_raw",
    )
    return {name: getattr(canon, name) for name in names}


async def test_ingest_order_does_not_matter(db_session: AsyncSession) -> None:
    a = make_normalized(published_at=EARLY)
    b = _other_channel(description_raw=LONG_DESCRIPTION, published_at=LATE)

    async def run(order: list[NormalizedVacancy]) -> dict[str, Any]:
        savepoint = await db_session.begin_nested()
        for vacancy in order:
            await ingest_vacancy(db_session, vacancy)
        snapshot = await _snapshot(db_session)
        await savepoint.rollback()
        assert await _counts(db_session) == (0, 0)
        return snapshot

    assert await run([a, b]) == await run([b, a])


async def test_edited_posting_updates_canon(db_session: AsyncSession) -> None:
    created = await ingest_vacancy(db_session, make_normalized())
    edited = make_normalized(description_raw=LONG_DESCRIPTION, raw_payload={"edited": True})

    result = await ingest_vacancy(db_session, edited)
    assert result.status == IngestStatus.POSTING_UPDATED
    assert not result.is_new
    assert await _counts(db_session) == (1, 1)
    posting = await _posting(db_session, created.posting_id)
    assert posting.content_hash == edited.content_hash
    assert posting.description_raw == LONG_DESCRIPTION
    assert posting.raw_payload == {"edited": True}
    canon = await _canon(db_session, created.vacancy_id)
    assert canon.description_clean == edited.description_clean
    assert canon.skills == edited.skills


async def test_edit_changing_company_is_ignored(db_session: AsyncSession) -> None:
    original = make_normalized()
    created = await ingest_vacancy(db_session, original)
    edited = make_normalized(company="Совсем другая компания", description_raw=LONG_DESCRIPTION)

    result = await ingest_vacancy(db_session, edited, seen_at=PARSED_AT + DAY)
    assert result.status == IngestStatus.POSTING_EDIT_IGNORED
    posting = await _posting(db_session, created.posting_id)
    assert posting.content_hash == original.content_hash
    assert posting.company == original.company
    assert posting.description_raw == original.description_raw
    assert posting.last_seen_at == PARSED_AT + DAY


async def test_edit_colliding_with_other_posting_text_is_ignored(db_session: AsyncSession) -> None:
    first = make_normalized(external_id="1")
    second = make_normalized(external_id="2", description_raw=LONG_DESCRIPTION)
    await ingest_vacancy(db_session, first)
    await ingest_vacancy(db_session, second)

    edited_first = make_normalized(external_id="1", description_raw=LONG_DESCRIPTION)
    result = await ingest_vacancy(db_session, edited_first)
    assert result.status == IngestStatus.POSTING_EDIT_IGNORED


async def test_demoted_winner_renormalizes_new_winner(db_session: AsyncSession) -> None:
    long_a = make_normalized(description_raw=LONG_DESCRIPTION)
    short_b = _other_channel(description_raw="Python, FastAPI, офис")
    created = await ingest_vacancy(db_session, long_a)
    await ingest_vacancy(db_session, short_b)
    canon = await _canon(db_session, created.vacancy_id)
    assert canon.description_clean == long_a.description_clean

    demoted_a = make_normalized(description_raw="🔥")
    assert demoted_a.parse_quality == ParseQuality.PARTIAL
    result = await ingest_vacancy(db_session, demoted_a)

    assert result.status == IngestStatus.POSTING_UPDATED
    canon = await _canon(db_session, created.vacancy_id)
    assert canon.description_clean == short_b.description_clean
    assert canon.source == short_b.source
    assert canon.skills == short_b.skills
    assert canon.parse_quality == ParseQuality.FULL
    assert (canon.city, canon.country) == ("Москва", "Россия")
    assert canon.postings_count == 2


async def test_naive_seen_at_rejected(db_session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        await ingest_vacancy(
            db_session,
            make_normalized(),
            seen_at=datetime(2026, 9, 1),  # noqa: DTZ001
        )
