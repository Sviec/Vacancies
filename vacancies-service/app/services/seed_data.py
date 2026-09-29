"""Данные сида (этап 7, раздел 10 ТЗ): загрузка, проверка и сборка батчей запусков.

Чистый модуль: ни БД, ни сети, ни часов. «Сейчас» приходит параметром, все
даты сида считаются от него (`age_hours`, `started_ago_hours`), поэтому один и
тот же `now` всегда даёт одинаковые батчи.

Данные — `app/data/seed_sources.json`, `seed_vacancies.json` и
`demo_resumes.json`; здесь только их схема и перекрёстные проверки.
"""

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.enums import (
    EmploymentType,
    ExperienceLevel,
    ParseQuality,
    RunStatus,
    SalaryPeriod,
    SourceType,
    UserAction,
    WorkFormat,
)
from app.schemas.common import CurrencyCode
from app.schemas.resumes import ResumeCreate
from app.services.normalizer import RawVacancy
from app.utils.skills_dict import DATA_DIR

SEED_SOURCES_FILE: Final = DATA_DIR / "seed_sources.json"
SEED_VACANCIES_FILE: Final = DATA_DIR / "seed_vacancies.json"
DEMO_RESUMES_FILE: Final = DATA_DIR / "demo_resumes.json"

# Порядок создания резюме: первое созданное становится основным.
RESUME_KEYS: Final = ("strong", "medium", "weak")

SEED_SOURCE_TYPES: Final = frozenset({SourceType.TELEGRAM, SourceType.HTML})

Profession = Literal[
    "backend", "frontend", "data", "devops", "qa", "mobile", "design", "product", "other"
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SeedRun(_Strict):
    """Синтетический запуск парсера; время — смещение от `now` сида."""

    started_ago_hours: int = Field(ge=1)
    duration_seconds: int = Field(ge=1)
    status: RunStatus
    error_text: str | None = None
    # TODO: `resee_previous` повторно подаёт в батч все прошлые публикации
    # источника — так `items_found > items_new`, как у настоящего парсера.
    resee_previous: bool = False

    @model_validator(mode="after")
    def _check_status(self) -> Self:
        if self.status == RunStatus.RUNNING:
            msg = "seed runs must be finished: status 'running' is not allowed"
            raise ValueError(msg)
        failed = self.status == RunStatus.FAILED
        if failed != (self.error_text is not None and self.error_text.strip() != ""):
            msg = "error_text is required for failed runs and forbidden otherwise"
            raise ValueError(msg)
        if failed and self.resee_previous:
            msg = "a failed run cannot resee previous postings"
            raise ValueError(msg)
        return self


class SeedSource(_Strict):
    """Источник вакансий сида и история его запусков."""

    slug: str = Field(min_length=1, max_length=64)
    source_type: SourceType
    is_enabled: bool = True
    config: dict[str, Any]
    runs: tuple[SeedRun, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_source(self) -> Self:
        if self.source_type not in SEED_SOURCE_TYPES:
            msg = f"source {self.slug}: only telegram and html sources are seeded"
            raise ValueError(msg)
        offsets = [run.started_ago_hours for run in self.runs]
        if any(later >= earlier for earlier, later in pairwise(offsets)):
            msg = f"source {self.slug}: runs must be chronological (started_ago_hours decreasing)"
            raise ValueError(msg)
        return self


class SeedStructured(_Strict):
    """Структурные поля HTML-карточки — имитация разметки сайта."""

    work_format: WorkFormat | None = None
    employment_type: EmploymentType | None = None
    experience_level: ExperienceLevel | None = None
    experience_min_years: int | None = Field(default=None, ge=0, le=60)
    relocation_support: bool | None = None
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    salary_currency: CurrencyCode | None = None
    salary_period: SalaryPeriod | None = None
    salary_is_gross: bool | None = None
    skills: tuple[str, ...] | None = None
    education_required: str | None = None
    languages: tuple[str, ...] | None = None


class SeedExpect(_Strict):
    """Ожидаемый результат нормализации; проверяются только заданные ключи."""

    level: ExperienceLevel | None = None
    work_format: WorkFormat | None = None
    employment_type: EmploymentType | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_period: SalaryPeriod | None = None
    relocation: bool | None = None
    parse_quality: ParseQuality | None = None
    skills_include: tuple[str, ...] = ()
    skills_exclude: tuple[str, ...] = ()


class SeedVacancy(_Strict):
    """Одна публикация сида: запись → `RawVacancy` → нормализатор → ingest."""

    key: str = Field(min_length=1)
    offer: str = Field(min_length=1)
    profession: Profession
    source: str
    run: int = Field(ge=0)
    external_id: str = Field(min_length=1, max_length=255)
    age_hours: int | None = Field(ge=0)
    title: str = Field(min_length=1)
    company: str | None
    city: str | None
    country: str | None = None
    url: str
    text: str
    salary_text: str | None = None
    structured: SeedStructured | None = None
    actions: tuple[UserAction, ...] = ()
    expect: SeedExpect | None = None

    @model_validator(mode="after")
    def _check_actions(self) -> Self:
        if len(set(self.actions)) != len(self.actions):
            msg = f"{self.key}: duplicate actions"
            raise ValueError(msg)
        if {UserAction.SAVED, UserAction.HIDDEN} <= set(self.actions):
            msg = f"{self.key}: 'saved' and 'hidden' are mutually exclusive"
            raise ValueError(msg)
        return self


class SeedResumeExpected(_Strict):
    """Допустимый диапазон оценки эталонного резюме."""

    min: float = Field(ge=0, le=10)
    max: float = Field(ge=0, le=10)

    @model_validator(mode="after")
    def _check_range(self) -> Self:
        if self.min > self.max:
            msg = "expected.min must not exceed expected.max"
            raise ValueError(msg)
        return self


class SeedResume(_Strict):
    """Эталонное резюме демо-пользователя."""

    key: str
    expected: SeedResumeExpected
    payload: ResumeCreate


def _dataset_errors(dataset: "SeedDataset") -> list[str]:
    errors: list[str] = []
    sources = {source.slug: source for source in dataset.sources}
    if len(sources) != len(dataset.sources):
        errors.append("duplicate source slug")

    keys: set[str] = set()
    ids: set[tuple[str, str]] = set()
    offers_with_actions: dict[str, str] = {}
    for item in dataset.vacancies:
        where = f"vacancy {item.key}"
        if item.key in keys:
            errors.append(f"{where}: duplicate key")
        keys.add(item.key)
        if (item.source, item.external_id) in ids:
            errors.append(f"{where}: duplicate (source, external_id)")
        ids.add((item.source, item.external_id))

        source = sources.get(item.source)
        if source is None:
            errors.append(f"{where}: unknown source {item.source!r}")
            continue
        if item.run >= len(source.runs):
            errors.append(f"{where}: run {item.run} is out of range for {item.source}")
            continue
        run = source.runs[item.run]
        if run.status == RunStatus.FAILED:
            errors.append(f"{where}: run {item.run} of {item.source} is failed")
        if item.age_hours is not None and item.age_hours < run.started_ago_hours:
            errors.append(f"{where}: published after the run started")

        telegram = source.source_type == SourceType.TELEGRAM
        if telegram and item.structured is not None:
            errors.append(f"{where}: telegram postings have no structured fields")
        if telegram and item.age_hours is None:
            errors.append(f"{where}: telegram postings always have a date")
        if telegram and not item.external_id.isdigit():
            errors.append(f"{where}: telegram external_id must be a message id")

        if item.actions:
            previous = offers_with_actions.get(item.offer)
            if previous is not None:
                errors.append(f"{where}: actions of offer {item.offer} already set on {previous}")
            offers_with_actions[item.offer] = item.key

    resume_keys = [resume.key for resume in dataset.resumes]
    if sorted(resume_keys) != sorted(RESUME_KEYS):
        errors.append(f"resume keys must be exactly {', '.join(RESUME_KEYS)}")
    return errors


class SeedDataset(_Strict):
    """Все данные сида с перекрёстными проверками."""

    sources: tuple[SeedSource, ...]
    vacancies: tuple[SeedVacancy, ...]
    resumes: tuple[SeedResume, ...]

    @model_validator(mode="after")
    def _cross_check(self) -> Self:
        errors = _dataset_errors(self)
        if errors:
            raise ValueError("; ".join(errors))
        return self

    def source(self, slug: str) -> SeedSource:
        """Источник по slug; неизвестный — `KeyError`."""
        for source in self.sources:
            if source.slug == slug:
                return source
        raise KeyError(slug)

    def resume(self, key: str) -> SeedResume:
        """Эталонное резюме по ключу; неизвестное — `KeyError`."""
        for resume in self.resumes:
            if resume.key == key:
                return resume
        raise KeyError(key)


@dataclass(frozen=True, slots=True)
class RunBatch:
    """Запуск парсера и публикации, которые он «нашёл»."""

    source: SeedSource
    run_index: int
    run: SeedRun
    started_at: datetime
    finished_at: datetime
    raws: tuple[RawVacancy, ...]


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def load_seed_dataset(data_dir: Path = DATA_DIR) -> SeedDataset:
    """Прочитать и проверить данные сида; ошибка данных — `ValidationError`."""
    return SeedDataset.model_validate(
        {
            "sources": _read_json(data_dir / SEED_SOURCES_FILE.name),
            "vacancies": _read_json(data_dir / SEED_VACANCIES_FILE.name),
            "resumes": _read_json(data_dir / DEMO_RESUMES_FILE.name),
        }
    )


def _require_aware(now: datetime) -> None:
    if now.tzinfo is None or now.utcoffset() is None:
        msg = "now must be timezone-aware"
        raise ValueError(msg)


def _salary_label(structured: SeedStructured | None) -> str | None:
    if structured is None or (structured.salary_min is None and structured.salary_max is None):
        return None
    bounds = "–".join(
        str(value) for value in (structured.salary_min, structured.salary_max) if value is not None
    )
    return " ".join(part for part in (bounds, structured.salary_currency) if part)


def _raw_payload(
    item: SeedVacancy, source: SeedSource, published_at: datetime | None
) -> dict[str, Any]:
    # TODO: raw_payload сида имитирует формат `fetch_raw` будущих парсеров
    # этапа 11: telegram — сообщение канала, html — поля карточки по селекторам.
    date = published_at.isoformat() if published_at is not None else None
    if source.source_type == SourceType.TELEGRAM:
        return {
            "channel": source.config.get("channel"),
            "message_id": int(item.external_id),
            "date": date,
            "text": item.text,
        }
    skills = item.structured.skills if item.structured is not None else None
    return {
        "page_url": source.config.get("url"),
        "fields": {
            "title": item.title,
            "company": item.company,
            "city": item.city,
            "salary": item.salary_text or _salary_label(item.structured),
            "description": item.text,
            "url": item.url,
            "published_at": date,
            "skills": list(skills or ()),
        },
    }


def to_raw(
    item: SeedVacancy, source: SeedSource, *, parsed_at: datetime, now: datetime
) -> RawVacancy:
    """Запись сида → сырой вход нормализатора, как его отдал бы парсер."""
    # TODO: telegram-записи без структурных полей (всё извлекает нормализатор
    # из текста), но title/company/city заданы явно — как если бы их выделил
    # парсер; html-записи несут структурные поля разметки.
    _require_aware(now)
    published_at = None if item.age_hours is None else now - timedelta(hours=item.age_hours)
    structured = item.structured or SeedStructured()
    return RawVacancy(
        external_id=item.external_id,
        source=source.slug,
        source_type=source.source_type,
        title=item.title,
        description_raw=item.text,
        parsed_at=parsed_at,
        url=item.url,
        company=item.company,
        city=item.city,
        country=item.country,
        salary_text=item.salary_text,
        skills_hint=structured.skills,
        published_at=published_at,
        raw_payload=_raw_payload(item, source, published_at),
        work_format=structured.work_format,
        employment_type=structured.employment_type,
        experience_level=structured.experience_level,
        experience_min_years=structured.experience_min_years,
        relocation_support=structured.relocation_support,
        salary_min=structured.salary_min,
        salary_max=structured.salary_max,
        salary_currency=structured.salary_currency,
        salary_period=structured.salary_period,
        salary_is_gross=structured.salary_is_gross,
        education_required=structured.education_required,
        languages=structured.languages,
    )


def build_run_batches(dataset: SeedDataset, now: datetime) -> list[RunBatch]:
    """Батчи всех запусков по `(started_at, slug)`; внутри батча — по `key`."""
    _require_aware(now)
    by_run: dict[tuple[str, int], list[SeedVacancy]] = defaultdict(list)
    for item in dataset.vacancies:
        by_run[(item.source, item.run)].append(item)

    batches: list[RunBatch] = []
    for source in dataset.sources:
        previous: list[SeedVacancy] = []
        for index, run in enumerate(source.runs):
            started_at = now - timedelta(hours=run.started_ago_hours)
            finished_at = started_at + timedelta(seconds=run.duration_seconds)
            own = sorted(by_run.get((source.slug, index), []), key=lambda v: v.key)
            if run.status == RunStatus.FAILED:
                items: list[SeedVacancy] = []
            elif run.resee_previous:
                items = [*sorted(previous, key=lambda v: v.key), *own]
            else:
                items = own
            raws = tuple(to_raw(item, source, parsed_at=finished_at, now=now) for item in items)
            batches.append(RunBatch(source, index, run, started_at, finished_at, raws))
            previous.extend(own)
    batches.sort(key=lambda batch: (batch.started_at, batch.source.slug))
    return batches
