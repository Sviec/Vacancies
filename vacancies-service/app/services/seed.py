"""Сид демо-данных (этап 7, раздел 10 ТЗ): источники, запуски, вакансии, резюме, действия.

Вакансии идут тем же путём, что у парсеров: `RawVacancy` → `normalize_vacancy`
→ `ingest_batch`, отдельно для каждого синтетического запуска. Прямых INSERT в
`vacancies` и `vacancy_postings` нет.

Модуль только `flush`-ит: границу транзакции задаёт вызывающий (CLI
`scripts/seed.py` коммитит или откатывает при `--dry-run`). Ни engine, ни
настроек здесь нет — сессия и `user_id` приходят параметрами.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, cast
from uuid import UUID

from sqlalchemy import ColumnElement, CursorResult, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ParseRun,
    Resume,
    Source,
    UserVacancyAction,
    Vacancy,
    VacancyMatch,
    VacancyPosting,
)
from app.enums import ParseQuality, RunStatus, UserAction
from app.schemas.recommendations import RecommendationsQuery
from app.services.ingest import ingest_batch
from app.services.normalizer import normalize_vacancy
from app.services.recommendations import get_recommendations
from app.services.resumes import create_resume
from app.services.seed_data import (
    RESUME_KEYS,
    RunBatch,
    SeedDataset,
    SeedVacancy,
    build_run_batches,
    load_seed_dataset,
)
from app.services.user_actions import add_action

EXIT_DATA_ERROR: Final = 1
EXIT_SCORE_OUT_OF_RANGE: Final = 2

# Порядок постановки действий внутри одной публикации.
_ACTION_ORDER: Final = (UserAction.VIEWED, UserAction.APPLIED, UserAction.SAVED, UserAction.HIDDEN)

# TODO: возраст публикаций отсчитывается от `now` запуска; повторный сид без
# --reset даты не освежает — ingest не меняет `published_at` у той же публикации.


@dataclass(frozen=True, slots=True, kw_only=True)
class SeedOptions:
    """Параметры сида; `now` — tz-aware «сейчас», от которого считаются все даты."""

    now: datetime
    user_id: UUID
    reset: bool = False
    with_actions: bool = True
    check_scores: bool = True
    preview_top: int = 3


@dataclass(frozen=True, slots=True)
class ResetReport:
    """Сколько строк удалил `--reset`."""

    vacancies: int
    sources: int
    resumes: int


@dataclass(frozen=True, slots=True)
class ResumeSeedResult:
    """Эталонное резюме: создано ли в этом запуске и его оценка."""

    key: str
    title: str
    created: bool
    score: float | None
    basis: str | None
    expected: tuple[float, float]


@dataclass(frozen=True, slots=True)
class SeedReport:
    """Итог сида для CLI и тестов."""

    now: datetime
    reset: ResetReport | None
    sources_created: tuple[str, ...]
    sources_skipped: tuple[str, ...]
    runs_created: int
    postings_found: int
    postings_new: int
    vacancies_total: int
    merged_offers: int
    partial_vacancies: int
    resumes: tuple[ResumeSeedResult, ...]
    actions_created: int
    # key резюме → топ рекомендаций (title, company, score).
    preview: Mapping[str, tuple[tuple[str, str | None, float], ...]]


class SeedError(Exception):
    """Сид не может завершиться: вызывающий обязан откатить транзакцию."""

    def __init__(
        self, message: str, *, exit_code: int = EXIT_DATA_ERROR, details: Sequence[str] = ()
    ) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code
        self.details = tuple(details)


def _require_aware(now: datetime) -> None:
    if now.tzinfo is None or now.utcoffset() is None:
        msg = "SeedOptions.now must be timezone-aware"
        raise ValueError(msg)


async def _delete_count(session: AsyncSession, statement: Any) -> int:
    result = cast("CursorResult[Any]", await session.execute(statement))
    return int(result.rowcount or 0)


async def reset_demo_data(session: AsyncSession, user_id: UUID) -> ResetReport:
    """Очистить домен вакансий целиком и резюме `user_id`. Не коммитит."""
    # TODO: --reset удаляет все вакансии, публикации, матчи, действия,
    # источники и запуски (всех пользователей), а резюме — только user_id.
    await _delete_count(session, delete(UserVacancyAction))
    await _delete_count(session, delete(VacancyMatch))
    await _delete_count(session, delete(VacancyPosting))
    vacancies = await _delete_count(session, delete(Vacancy))
    await _delete_count(session, delete(ParseRun))
    sources = await _delete_count(session, delete(Source))
    # Секции резюме уходят по FK ON DELETE CASCADE.
    resumes = await _delete_count(session, delete(Resume).where(Resume.user_id == user_id))
    await session.flush()
    # Удалённые Core-запросом строки могли остаться в identity map.
    session.expunge_all()
    return ResetReport(vacancies=vacancies, sources=sources, resumes=resumes)


async def _count(session: AsyncSession, *conditions: ColumnElement[bool]) -> int:
    stmt = select(func.count()).select_from(Vacancy).where(*conditions)
    return int(await session.scalar(stmt) or 0)


async def _create_sources(session: AsyncSession, dataset: SeedDataset) -> dict[str, Source]:
    # TODO: единица идемпотентности — источник: существующий slug пропускается
    # вместе со всеми своими запусками и публикациями.
    slugs = [source.slug for source in dataset.sources]
    existing = set((await session.scalars(select(Source.slug).where(Source.slug.in_(slugs)))).all())
    created: dict[str, Source] = {}
    for spec in dataset.sources:
        if spec.slug in existing:
            continue
        source = Source(
            slug=spec.slug,
            source_type=spec.source_type,
            config=dict(spec.config),
            is_enabled=spec.is_enabled,
        )
        session.add(source)
        created[spec.slug] = source
    await session.flush()
    return created


async def _ingest_run(session: AsyncSession, batch: RunBatch) -> tuple[int, int]:
    try:
        normalized = [normalize_vacancy(raw) for raw in batch.raws]
    except ValueError as exc:
        msg = f"seed posting of {batch.source.slug} failed normalization: {exc}"
        raise SeedError(msg) from exc
    result = await ingest_batch(session, normalized, seen_at=batch.finished_at)
    if result.errors:
        raise SeedError(
            f"ingest failed for {len(result.errors)} posting(s) of {batch.source.slug}",
            details=[
                f"{error.source}/{error.external_id}: {error.error_type}: {error.message}"
                for error in result.errors
            ],
        )
    return result.items_found, result.items_new


async def _seed_runs(
    session: AsyncSession, batches: Sequence[RunBatch], created: Mapping[str, Source]
) -> tuple[int, int, int]:
    """Запуски только созданных источников; счётчики — факт `ingest_batch`."""
    # TODO: parse_runs синтетические по времени, но items_found/items_new —
    # фактический результат ingest_batch по батчу запуска.
    runs = found = new = 0
    last: dict[str, RunBatch] = {}
    for batch in batches:
        source = created.get(batch.source.slug)
        if source is None:
            continue
        items_found = items_new = 0
        if batch.run.status != RunStatus.FAILED:
            items_found, items_new = await _ingest_run(session, batch)
        session.add(
            ParseRun(
                source_id=source.id,
                started_at=batch.started_at,
                finished_at=batch.finished_at,
                status=batch.run.status,
                items_found=items_found,
                items_new=items_new,
                error_text=batch.run.error_text,
            )
        )
        runs += 1
        found += items_found
        new += items_new
        last[batch.source.slug] = batch

    # TODO: last_run_at — started_at последнего запуска источника.
    for slug, batch in last.items():
        source = created[slug]
        source.last_run_at = batch.started_at
        source.last_run_status = batch.run.status
        source.last_error = batch.run.error_text
    await session.flush()
    return runs, found, new


def _basis(resume: Resume) -> str | None:
    market = (resume.score_details or {}).get("market")
    if isinstance(market, Mapping):
        basis = market.get("basis")
        return basis if isinstance(basis, str) else None
    return None


async def _seed_resumes(
    session: AsyncSession, dataset: SeedDataset, options: SeedOptions
) -> list[tuple[ResumeSeedResult, Resume]]:
    # TODO: эталонное резюме опознаётся по title у user_id; собственное резюме
    # пользователя с тем же названием заблокирует создание эталонного.
    stmt = (
        select(Resume)
        .where(Resume.user_id == options.user_id)
        .order_by(Resume.created_at, Resume.id)
        .execution_options(populate_existing=True)
    )
    existing: dict[str, Resume] = {}
    for resume in (await session.scalars(stmt)).all():
        existing.setdefault(resume.title, resume)

    results: list[tuple[ResumeSeedResult, Resume]] = []
    for key in RESUME_KEYS:
        entry = dataset.resume(key)
        found = existing.get(entry.payload.title)
        created = found is None
        resume = (
            found
            if found is not None
            else await create_resume(
                session, options.user_id, entry.payload, today=options.now.date()
            )
        )
        result = ResumeSeedResult(
            key=key,
            title=resume.title,
            created=created,
            score=resume.score,
            basis=_basis(resume),
            expected=(entry.expected.min, entry.expected.max),
        )
        results.append((result, resume))
    return results


def _check_scores(results: Sequence[tuple[ResumeSeedResult, Resume]]) -> None:
    # TODO: оценка вне ожидаемого диапазона — ошибка и откат всего сида;
    # проверяются только резюме, созданные в этом запуске.
    failures: list[str] = []
    for result, resume in results:
        if not result.created:
            continue
        low, high = result.expected
        if result.score is None or not low <= result.score <= high:
            market = (resume.score_details or {}).get("market") or {}
            failures.append(
                f"{result.key}: score={result.score} expected [{low}, {high}], "
                f"basis={result.basis}, top_skills={market.get('top_skills')}"
            )
    if failures:
        raise SeedError(
            "resume scores are out of the expected range",
            exit_code=EXIT_SCORE_OUT_OF_RANGE,
            details=failures,
        )


async def _seed_actions(session: AsyncSession, dataset: SeedDataset, user_id: UUID) -> int:
    # TODO: действия сидируются, только если у пользователя нет ни одного.
    has_any = await session.scalar(
        select(UserVacancyAction.id).where(UserVacancyAction.user_id == user_id).limit(1)
    )
    if has_any is not None:
        return 0
    created = 0
    items: list[SeedVacancy] = sorted(
        (item for item in dataset.vacancies if item.actions), key=lambda item: item.key
    )
    for item in items:
        vacancy_id = await session.scalar(
            select(VacancyPosting.vacancy_id).where(
                VacancyPosting.source == item.source,
                VacancyPosting.external_id == item.external_id,
            )
        )
        if vacancy_id is None:
            msg = f"posting {item.source}/{item.external_id} for seed actions was not found"
            raise SeedError(msg)
        for action in _ACTION_ORDER:
            if action in item.actions:
                await add_action(session, user_id, vacancy_id, action)
                created += 1
    return created


async def _preview(
    session: AsyncSession,
    results: Sequence[tuple[ResumeSeedResult, Resume]],
    options: SeedOptions,
) -> dict[str, tuple[tuple[str, str | None, float], ...]]:
    # TODO: vacancy_matches заранее не считаются; превью идёт через
    # get_recommendations (путь UI) и заполняет кэш со временем now сида.
    preview: dict[str, tuple[tuple[str, str | None, float], ...]] = {}
    for result, resume in results:
        recommendations = await get_recommendations(
            session,
            options.user_id,
            RecommendationsQuery(resume_id=resume.id, limit=options.preview_top),
            now=options.now,
        )
        preview[result.key] = tuple(
            (item.vacancy.title, item.vacancy.company, item.result.score)
            for item in recommendations.items
        )
    return preview


async def run_seed(
    session: AsyncSession, options: SeedOptions, *, dataset: SeedDataset | None = None
) -> SeedReport:
    """Наполнить БД демо-данными; идемпотентно. Только flush, без commit."""
    _require_aware(options.now)
    data = dataset if dataset is not None else load_seed_dataset()
    reset = await reset_demo_data(session, options.user_id) if options.reset else None

    created = await _create_sources(session, data)
    batches = [
        batch for batch in build_run_batches(data, options.now) if batch.source.slug in created
    ]
    runs, found, new = await _seed_runs(session, batches, created)

    resumes = await _seed_resumes(session, data, options)
    if options.check_scores:
        _check_scores(resumes)

    actions = await _seed_actions(session, data, options.user_id) if options.with_actions else 0
    preview = await _preview(session, resumes, options) if options.preview_top > 0 else {}

    await session.flush()
    return SeedReport(
        now=options.now,
        reset=reset,
        sources_created=tuple(created),
        sources_skipped=tuple(s.slug for s in data.sources if s.slug not in created),
        runs_created=runs,
        postings_found=found,
        postings_new=new,
        vacancies_total=await _count(session),
        merged_offers=await _count(session, Vacancy.postings_count > 1),
        partial_vacancies=await _count(session, Vacancy.parse_quality == ParseQuality.PARTIAL),
        resumes=tuple(result for result, _ in resumes),
        actions_created=actions,
        preview=preview,
    )


def format_report(report: SeedReport) -> str:
    """Многострочный отчёт для CLI."""
    lines: list[str] = []
    if report.reset is not None:
        lines.append(
            f"reset: deleted {report.reset.vacancies} vacancies, "
            f"{report.reset.sources} sources, {report.reset.resumes} resumes"
        )
    lines.append(
        f"sources: created {len(report.sources_created)} "
        f"({', '.join(report.sources_created) or '-'}), "
        f"skipped {len(report.sources_skipped)} ({', '.join(report.sources_skipped) or '-'})"
    )
    lines.append(
        f"parse runs: {report.runs_created} created, "
        f"postings found {report.postings_found}, new {report.postings_new}"
    )
    lines.append(
        f"vacancies in DB: {report.vacancies_total} "
        f"(merged from 2+ sources: {report.merged_offers}, partial: {report.partial_vacancies})"
    )
    lines.append("resumes:")
    for resume in report.resumes:
        state = "created" if resume.created else "skipped (exists)"
        low, high = resume.expected
        lines.append(
            f"  {resume.key:<6} {state:<16} score={resume.score} "
            f"expected=[{low}, {high}] basis={resume.basis} title={resume.title!r}"
        )
    lines.append(f"user actions created: {report.actions_created}")
    for key, items in report.preview.items():
        lines.append(f"top recommendations for {key}:")
        lines.extend(
            f"  {score:6.2f}  {title} — {company or '(no company)'}"
            for title, company, score in items
        )
    return "\n".join(lines)
