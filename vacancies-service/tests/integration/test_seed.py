"""Сид демо-данных на реальной БД: отчёт, запуски, оценки, идемпотентность, сброс."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import (
    ParseRun,
    Resume,
    Source,
    UserVacancyAction,
    Vacancy,
    VacancyMatch,
    VacancyPosting,
)
from app.enums import RunStatus
from app.schemas.resumes import ResumeCreate
from app.services.resumes import create_resume
from app.services.seed import SeedOptions, SeedReport, run_seed
from app.services.seed_data import load_seed_dataset

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("no_app_engine")]

FIXED_NOW = datetime(2026, 9, 28, 12, tzinfo=UTC)

EXPECTED_RUNS: dict[str, list[tuple[int, int]]] = {
    "tg_it_jobs": [(7, 7), (6, 6), (17, 4)],
    "tg_relocate_remote": [(11, 11), (7, 7), (18, 0)],
    "html_careerhub": [(10, 10), (8, 8)],
    "html_jobboard": [(12, 12), (7, 7), (0, 0)],
}
EXPECTED_ACTIONS = sum(len(item.actions) for item in load_seed_dataset().vacancies)

_TABLES = (Source, ParseRun, Vacancy, VacancyPosting, VacancyMatch, UserVacancyAction, Resume)


def _demo_user() -> uuid.UUID:
    return get_settings().demo_user_id


async def _row_counts(session: AsyncSession) -> dict[str, int]:
    counts: dict[str, int] = {}
    for model in _TABLES:
        counts[model.__tablename__] = int(
            await session.scalar(select(func.count()).select_from(model)) or 0
        )
    return counts


def _assert_full_report(report: SeedReport) -> None:
    assert len(report.sources_created) == 4
    assert report.sources_skipped == ()
    assert report.runs_created == 11
    assert report.postings_new == 72
    assert report.vacancies_total == 64
    assert report.merged_offers == 8
    assert report.partial_vacancies == 4
    assert [r.created for r in report.resumes] == [True, True, True]
    assert report.actions_created == EXPECTED_ACTIONS


async def test_seed_report_matches_tables(seeded: SeedReport, db_session: AsyncSession) -> None:
    _assert_full_report(seeded)
    assert seeded.postings_found == sum(f for runs in EXPECTED_RUNS.values() for f, _ in runs)
    counts = await _row_counts(db_session)
    assert counts["sources"] == 4
    assert counts["parse_runs"] == 11
    assert counts["vacancies"] == 64
    assert counts["vacancy_postings"] == 72
    assert counts["resumes"] == 3
    assert counts["user_vacancy_actions"] == EXPECTED_ACTIONS
    assert EXPECTED_ACTIONS == 12
    assert set(seeded.preview) == {"strong", "medium", "weak"}
    assert all(len(items) == 3 for items in seeded.preview.values())


async def test_parse_runs_follow_ingest(seeded: SeedReport, db_session: AsyncSession) -> None:
    dataset = load_seed_dataset()
    rows = (
        await db_session.execute(
            select(Source.slug, ParseRun)
            .join(ParseRun, ParseRun.source_id == Source.id)
            .order_by(ParseRun.started_at)
        )
    ).all()
    actual: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for slug, run in rows:
        actual[slug].append((run.items_found, run.items_new))
        assert run.finished_at is not None
        assert run.finished_at > run.started_at
    assert dict(actual) == EXPECTED_RUNS

    for source in dataset.sources:
        own = sum(1 for item in dataset.vacancies if item.source == source.slug)
        assert sum(new for _, new in actual[source.slug]) == own

    sources = {s.slug: s for s in (await db_session.scalars(select(Source))).all()}
    jobboard = sources["html_jobboard"]
    assert jobboard.last_run_status == RunStatus.FAILED
    assert jobboard.last_error == dataset.source("html_jobboard").runs[-1].error_text
    for slug in ("tg_it_jobs", "tg_relocate_remote", "html_careerhub"):
        assert sources[slug].last_run_status == RunStatus.SUCCESS
        assert sources[slug].last_error is None
    last_runs = {slug: runs[-1] for slug, runs in actual.items()}
    assert last_runs["tg_relocate_remote"] == (18, 0)
    for row in sources.values():
        latest = max(run.started_at for slug, run in rows if slug == row.slug)
        assert row.last_run_at == latest


async def test_resume_scores_on_seed_market(seeded: SeedReport, db_session: AsyncSession) -> None:
    by_key = {r.key: r for r in seeded.resumes}
    for result in seeded.resumes:
        low, high = result.expected
        assert result.score is not None
        assert low <= result.score <= high, result
    strong, medium, weak = (by_key[k].score or 0.0 for k in ("strong", "medium", "weak"))
    assert strong > medium > weak
    assert by_key["strong"].basis == "target_position"
    assert by_key["medium"].basis == "target_position"
    assert by_key["weak"].basis == "all_vacancies"

    primary = (
        await db_session.scalars(
            select(Resume).where(Resume.user_id == _demo_user(), Resume.is_primary.is_(True))
        )
    ).all()
    assert [r.title for r in primary] == [by_key["strong"].title]


async def test_second_run_is_noop(seeded: SeedReport, db_session: AsyncSession) -> None:
    before = await _row_counts(db_session)
    again = await run_seed(db_session, SeedOptions(now=seeded.now, user_id=_demo_user()))
    assert again.sources_created == ()
    assert len(again.sources_skipped) == 4
    assert again.runs_created == 0
    assert again.postings_found == 0
    assert [r.created for r in again.resumes] == [False, False, False]
    assert again.actions_created == 0
    assert [(r.key, r.score, r.basis) for r in again.resumes] == [
        (r.key, r.score, r.basis) for r in seeded.resumes
    ]
    assert await _row_counts(db_session) == before


async def test_reset_restores_seed_and_keeps_other_users(
    seeded: SeedReport, db_session: AsyncSession
) -> None:
    after_seed = await _row_counts(db_session)
    stranger = uuid.uuid4()
    foreign = await create_resume(db_session, stranger, ResumeCreate(title="Foreign resume"))
    await create_resume(db_session, _demo_user(), ResumeCreate(title="Extra demo resume"))

    report = await run_seed(
        db_session, SeedOptions(now=seeded.now, user_id=_demo_user(), reset=True)
    )
    assert report.reset is not None
    assert report.reset.vacancies == 64
    assert report.reset.sources == 4
    assert report.reset.resumes == 4
    _assert_full_report(report)

    counts = await _row_counts(db_session)
    assert counts == {**after_seed, "resumes": after_seed["resumes"] + 1}
    titles = (
        await db_session.scalars(select(Resume.title).where(Resume.user_id == _demo_user()))
    ).all()
    assert sorted(titles) == sorted(r.title for r in seeded.resumes)
    kept = await db_session.scalar(select(Resume.id).where(Resume.user_id == stranger))
    assert kept == foreign.id


async def _snapshot(session: AsyncSession) -> dict[str, Any]:
    vacancies = sorted(
        (
            v.dedup_key_raw or f"{v.title}|{v.company}",
            tuple(v.skills),
            v.salary_min,
            v.salary_max,
            v.salary_currency,
            v.salary_period,
            v.published_at,
            v.postings_count,
            v.parse_quality,
            v.title,
            v.work_format,
            v.experience_level,
        )
        for v in (
            await session.scalars(select(Vacancy).execution_options(populate_existing=True))
        ).all()
    )
    postings = sorted(
        (p.source, p.external_id, p.content_hash, p.published_at, p.parse_quality, p.title)
        for p in (await session.scalars(select(VacancyPosting))).all()
    )
    runs = sorted(
        (slug, run.started_at, run.finished_at, run.status, run.items_found, run.items_new)
        for slug, run in (
            await session.execute(
                select(Source.slug, ParseRun).join(ParseRun, ParseRun.source_id == Source.id)
            )
        ).all()
    )
    resumes = sorted(
        (r.title, r.score, repr(r.score_details), r.is_primary)
        for r in (
            await session.scalars(
                select(Resume)
                .where(Resume.user_id == _demo_user())
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    return {"vacancies": vacancies, "postings": postings, "runs": runs, "resumes": resumes}


async def test_seed_is_deterministic_for_fixed_now(db_session: AsyncSession) -> None:
    first = await run_seed(db_session, SeedOptions(now=FIXED_NOW, user_id=_demo_user()))
    _assert_full_report(first)
    before = await _snapshot(db_session)

    second = await run_seed(
        db_session, SeedOptions(now=FIXED_NOW, user_id=_demo_user(), reset=True)
    )
    _assert_full_report(second)
    assert await _snapshot(db_session) == before
    assert [(r.key, r.score, r.basis) for r in second.resumes] == [
        (r.key, r.score, r.basis) for r in first.resumes
    ]
    assert second.preview == first.preview


async def test_without_actions_and_preview(db_session: AsyncSession) -> None:
    report = await run_seed(
        db_session,
        SeedOptions(now=FIXED_NOW, user_id=_demo_user(), with_actions=False, preview_top=0),
    )
    assert report.actions_created == 0
    assert report.preview == {}
    assert await db_session.scalar(select(func.count()).select_from(UserVacancyAction)) == 0
