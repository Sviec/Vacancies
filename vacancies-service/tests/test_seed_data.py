"""Офлайн-проверки данных сида: нормализатор реальный, БД нет."""

import re
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import pytest

from app.enums import (
    EmploymentType,
    ExperienceLevel,
    ParseQuality,
    RunStatus,
    SalaryPeriod,
    SourceType,
    WorkFormat,
)
from app.schemas.normalized import NormalizedVacancy
from app.services.normalizer import (
    WinnerCandidate,
    compute_dedup_key,
    normalize_skills,
    normalize_vacancy,
    pick_winner,
)
from app.services.seed_data import (
    RESUME_KEYS,
    SeedDataset,
    SeedVacancy,
    build_run_batches,
    load_seed_dataset,
    to_raw,
)

NOW = datetime(2026, 9, 28, 12, tzinfo=UTC)
INT4_MAX = 2**31 - 1

# Ожидаемые (found, new) по запускам — таблица шага 2 плана.
EXPECTED_RUNS: dict[str, list[tuple[int, int]]] = {
    "tg_it_jobs": [(7, 7), (6, 6), (17, 4)],
    "tg_relocate_remote": [(11, 11), (7, 7), (18, 0)],
    "html_careerhub": [(10, 10), (8, 8)],
    "html_jobboard": [(12, 12), (7, 7), (0, 0)],
}


@dataclass(frozen=True, slots=True)
class Posting:
    item: SeedVacancy
    normalized: NormalizedVacancy


@dataclass(frozen=True, slots=True)
class Canon:
    offer: str
    postings: tuple[Posting, ...]
    winner: Posting

    @property
    def vacancy(self) -> NormalizedVacancy:
        return self.winner.normalized

    @property
    def published_at(self) -> datetime | None:
        dates = [p.normalized.published_at for p in self.postings if p.normalized.published_at]
        return min(dates) if dates else None


@pytest.fixture(scope="module")
def dataset() -> SeedDataset:
    return load_seed_dataset()


@pytest.fixture(scope="module")
def postings(dataset: SeedDataset) -> list[Posting]:
    result: list[Posting] = []
    for item in dataset.vacancies:
        source = dataset.source(item.source)
        raw = to_raw(item, source, parsed_at=NOW, now=NOW)
        result.append(Posting(item, normalize_vacancy(raw)))
    return result


def _candidate(posting: Posting) -> WinnerCandidate:
    vacancy = posting.normalized
    return WinnerCandidate(
        source=vacancy.source,
        external_id=vacancy.external_id,
        parse_quality=vacancy.parse_quality,
        description_length=len(vacancy.description_clean),
        published_at=vacancy.published_at,
    )


def _dedup_key(posting: Posting) -> str | None:
    vacancy = posting.normalized
    return compute_dedup_key(vacancy.company, vacancy.title, vacancy.city)[0]


@pytest.fixture(scope="module")
def groups(postings: list[Posting]) -> list[list[Posting]]:
    """Моделирование склейки ingest: по dedup_key, без ключа — отдельная вакансия."""
    by_key: dict[str, list[Posting]] = defaultdict(list)
    alone: list[list[Posting]] = []
    for posting in postings:
        key = _dedup_key(posting)
        if key is None:
            alone.append([posting])
        else:
            by_key[key].append(posting)
    return [*by_key.values(), *alone]


@pytest.fixture(scope="module")
def canons(groups: list[list[Posting]]) -> list[Canon]:
    result: list[Canon] = []
    for group in groups:
        winner_id = pick_winner([_candidate(p) for p in group])
        winner = next(p for p in group if _candidate(p) == winner_id)
        result.append(Canon(group[0].item.offer, tuple(group), winner))
    return result


def _count(canons: list[Canon], predicate: Callable[[Canon], bool]) -> int:
    return sum(1 for canon in canons if predicate(canon))


def _text(vacancy: NormalizedVacancy) -> str:
    return f"{vacancy.title} {vacancy.description_clean}".lower()


def test_dataset_loads_with_expected_shape(dataset: SeedDataset) -> None:
    types = Counter(source.source_type for source in dataset.sources)
    assert types == {SourceType.TELEGRAM: 2, SourceType.HTML: 2}
    assert len(dataset.vacancies) >= 70
    per_source = Counter(item.source for item in dataset.vacancies)
    assert set(per_source) == {source.slug for source in dataset.sources}
    assert min(per_source.values()) >= 12
    assert tuple(sorted(r.key for r in dataset.resumes)) == tuple(sorted(RESUME_KEYS))


def test_run_batches_are_chronological(dataset: SeedDataset) -> None:
    batches = build_run_batches(dataset, NOW)
    assert len(batches) == 11
    starts = [batch.started_at for batch in batches]
    assert starts == sorted(starts)
    for batch in batches:
        assert batch.finished_at > batch.started_at
        assert batch.started_at < NOW
        if batch.run.status == RunStatus.FAILED:
            assert batch.raws == ()
        assert all(raw.parsed_at == batch.finished_at for raw in batch.raws)


def test_run_batches_are_deterministic(dataset: SeedDataset) -> None:
    first = build_run_batches(dataset, NOW)
    second = build_run_batches(dataset, NOW)
    assert [(b.source.slug, b.run_index, b.raws) for b in first] == [
        (b.source.slug, b.run_index, b.raws) for b in second
    ]


def test_build_run_batches_rejects_naive_now(dataset: SeedDataset) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        build_run_batches(dataset, NOW.replace(tzinfo=None))


def test_expected_run_counters(dataset: SeedDataset) -> None:
    """Чистый расчёт items_found/items_new: новая — публикация, не встреченная раньше."""
    seen: set[tuple[str, str]] = set()
    actual: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for batch in build_run_batches(dataset, NOW):
        ids = [(raw.source, raw.external_id) for raw in batch.raws]
        new = sum(1 for posting_id in ids if posting_id not in seen)
        seen.update(ids)
        actual[batch.source.slug].append((len(ids), new))
    assert dict(actual) == EXPECTED_RUNS


def test_every_expectation_holds(postings: list[Posting]) -> None:
    failures: list[str] = []
    for posting in postings:
        expect = posting.item.expect
        if expect is None:
            continue
        vacancy = posting.normalized
        actual = {
            "level": vacancy.experience_level,
            "work_format": vacancy.work_format,
            "employment_type": vacancy.employment_type,
            "salary_min": vacancy.salary_min,
            "salary_max": vacancy.salary_max,
            "salary_currency": vacancy.salary_currency,
            "salary_period": vacancy.salary_period,
            "relocation": vacancy.relocation_support,
            "parse_quality": vacancy.parse_quality,
        }
        for name in expect.model_fields_set & actual.keys():
            if getattr(expect, name) != actual[name]:
                failures.append(
                    f"{posting.item.key}.{name}: want {getattr(expect, name)}, got {actual[name]}"
                )
        missing = set(expect.skills_include) - set(vacancy.skills)
        forbidden = set(expect.skills_exclude) & set(vacancy.skills)
        if missing:
            failures.append(f"{posting.item.key}: missing skills {sorted(missing)}")
        if forbidden:
            failures.append(f"{posting.item.key}: forbidden skills {sorted(forbidden)}")
    assert failures == []


def test_dedup_partition_equals_offers(groups: list[list[Posting]]) -> None:
    by_offer: dict[str, set[str]] = defaultdict(set)
    for posting in (p for group in groups for p in group):
        by_offer[posting.item.offer].add(posting.item.key)
    dedup_partition = sorted(sorted(p.item.key for p in group) for group in groups)
    offer_partition = sorted(sorted(keys) for keys in by_offer.values())
    assert dedup_partition == offer_partition


def test_partial_without_company_has_no_key(postings: list[Posting]) -> None:
    offers = Counter(p.item.offer for p in postings)
    for posting in postings:
        if posting.normalized.company is None:
            assert _dedup_key(posting) is None
            assert offers[posting.item.offer] == 1


def test_merges(groups: list[list[Posting]]) -> None:
    merged = [group for group in groups if len(group) > 1]
    assert len(merged) == 8
    assert all(len(group) == 2 for group in merged)
    kinds: Counter[tuple[str, ...]] = Counter()
    for group in merged:
        assert len({p.item.source for p in group}) == 2
        kinds[tuple(sorted(p.normalized.source_type.value for p in group))] += 1
    assert kinds[("telegram", "telegram")] >= 1
    assert kinds[("html", "telegram")] >= 1
    assert kinds[("html", "html")] >= 1


def test_volume(canons: list[Canon], postings: list[Posting]) -> None:
    assert len(canons) >= 60
    assert len(postings) >= 70


def test_partial_minimums(canons: list[Canon], postings: list[Posting]) -> None:
    assert _count(canons, lambda c: c.vacancy.parse_quality == ParseQuality.PARTIAL) >= 4
    partial_postings = [p for p in postings if p.normalized.parse_quality == ParseQuality.PARTIAL]
    assert len(partial_postings) >= 6


def test_level_minimums(canons: list[Canon]) -> None:
    levels = Counter(canon.vacancy.experience_level for canon in canons)
    for level in ExperienceLevel:
        assert levels[level] >= 3, level


def test_format_and_employment_minimums(canons: list[Canon]) -> None:
    formats = Counter(canon.vacancy.work_format for canon in canons)
    assert formats[WorkFormat.REMOTE] >= 12
    assert formats[WorkFormat.HYBRID] >= 8
    assert formats[WorkFormat.OFFICE] >= 10
    employment = Counter(canon.vacancy.employment_type for canon in canons)
    assert employment[EmploymentType.INTERNSHIP] >= 2
    assert employment[EmploymentType.PART_TIME] >= 2
    assert employment[EmploymentType.CONTRACT] >= 3


def test_salary_minimums(canons: list[Canon]) -> None:
    currencies = Counter(canon.vacancy.salary_currency for canon in canons)
    assert currencies["RUB"] >= 25
    assert currencies["USD"] >= 6
    assert currencies["EUR"] >= 3
    assert currencies["KZT"] >= 1
    assert currencies["GBP"] >= 1
    no_salary = _count(
        canons, lambda c: c.vacancy.salary_min is None and c.vacancy.salary_max is None
    )
    assert no_salary >= 8
    periods = Counter(canon.vacancy.salary_period for canon in canons)
    assert periods[SalaryPeriod.YEAR] >= 1
    assert periods[SalaryPeriod.HOUR] >= 1


def test_location_minimums(canons: list[Canon]) -> None:
    assert _count(canons, lambda c: c.vacancy.relocation_support is True) >= 5
    assert len({c.vacancy.country for c in canons if c.vacancy.country}) >= 7
    assert len({c.vacancy.city for c in canons if c.vacancy.city}) >= 12
    remote_no_city = _count(
        canons, lambda c: c.vacancy.work_format == WorkFormat.REMOTE and c.vacancy.city is None
    )
    assert remote_no_city >= 6


def test_age_minimums(canons: list[Canon]) -> None:
    buckets: Counter[str] = Counter()
    for canon in canons:
        published = canon.published_at
        if published is None:
            buckets["none"] += 1
            continue
        age = NOW - published
        if age <= timedelta(days=3):
            buckets["0-3"] += 1
        elif age <= timedelta(days=7):
            buckets["4-7"] += 1
        elif age <= timedelta(days=14):
            buckets["8-14"] += 1
        elif age <= timedelta(days=30):
            buckets["15-30"] += 1
        else:
            buckets[">30"] += 1
    assert buckets["0-3"] >= 8
    assert buckets["4-7"] >= 6
    assert buckets["8-14"] >= 6
    assert buckets["15-30"] >= 8
    assert buckets[">30"] >= 5
    assert buckets["none"] >= 1


def test_profession_minimums(canons: list[Canon]) -> None:
    professions: Counter[str] = Counter(canon.winner.item.profession for canon in canons)
    minimums = {
        "backend": 18,
        "frontend": 6,
        "data": 8,
        "devops": 5,
        "qa": 5,
        "mobile": 2,
        "design": 3,
        "product": 3,
    }
    for profession, minimum in minimums.items():
        assert professions[profession] >= minimum, profession


def _word(pattern: str) -> re.Pattern[str]:
    # Слеш вплотную делает из слов один токен-путь для парсера Postgres.
    return re.compile(rf"(?<![/\w]){pattern}(?![/\w])")


SENIOR = _word("senior")
PYTHON = _word("python")
DEVELOP = _word(r"develop\w*")
PYTHON_DEV = re.compile(r"python-разработчик\w*")
MEDIUM_FORBIDDEN = {"html", "css", "javascript", "bash"}


def test_strong_market_approximation(canons: list[Canon]) -> None:
    matching = _count(
        canons,
        lambda c: all(p.search(_text(c.vacancy)) for p in (SENIOR, PYTHON, DEVELOP)),
    )
    assert matching >= 5


def test_medium_market_approximation(canons: list[Canon], postings: list[Posting]) -> None:
    assert _count(canons, lambda c: PYTHON_DEV.search(_text(c.vacancy)) is not None) >= 5
    offenders = [
        p.item.key
        for p in postings
        if PYTHON_DEV.search(_text(p.normalized)) and MEDIUM_FORBIDDEN & set(p.normalized.skills)
    ]
    assert offenders == []


def test_resume_targets(canons: list[Canon], dataset: SeedDataset) -> None:
    weak_skills = {"python", "sql", "excel"}
    weak = _count(
        canons,
        lambda c: (
            c.vacancy.work_format == WorkFormat.REMOTE
            and c.vacancy.experience_level in {ExperienceLevel.JUNIOR, ExperienceLevel.INTERN}
            and len(weak_skills & set(c.vacancy.skills)) >= 2
        ),
    )
    assert weak >= 3

    strong_skills = set(
        normalize_skills(skill.skill for skill in dataset.resume("strong").payload.skills)
    )
    strong = _count(
        canons,
        lambda c: (
            c.vacancy.experience_level == ExperienceLevel.SENIOR
            and len(strong_skills & set(c.vacancy.skills)) >= 3
        ),
    )
    assert strong >= 5


def test_content_hash_unique_per_source(postings: list[Posting]) -> None:
    hashes = Counter((p.normalized.source, p.normalized.content_hash) for p in postings)
    assert [key for key, count in hashes.items() if count > 1] == []


def test_salaries_fit_int4(postings: list[Posting]) -> None:
    for posting in postings:
        for value in (posting.normalized.salary_min, posting.normalized.salary_max):
            assert value is None or 0 <= value <= INT4_MAX


def test_urls_are_fictional(dataset: SeedDataset) -> None:
    for item in dataset.vacancies:
        parts = urlsplit(item.url)
        host = parts.hostname or ""
        telegram = host == "t.me" and parts.path.startswith("/demo_")
        fictional = host.endswith((".example.com", ".example.org"))
        assert parts.scheme == "https", item.key
        assert telegram or fictional, item.key


def test_dataset_rejects_inconsistent_records(dataset: SeedDataset) -> None:
    payload = dataset.model_dump(mode="json")
    payload["vacancies"][1]["key"] = payload["vacancies"][0]["key"]
    payload["vacancies"][2]["source"] = "unknown_source"
    with pytest.raises(ValueError, match="duplicate key") as info:
        SeedDataset.model_validate(payload)
    assert "unknown source" in str(info.value)


def test_dataset_rejects_postings_in_failed_runs(dataset: SeedDataset) -> None:
    payload = dataset.model_dump(mode="json")
    record = next(v for v in payload["vacancies"] if v["source"] == "html_jobboard")
    record["run"] = 2
    with pytest.raises(ValueError, match="is failed"):
        SeedDataset.model_validate(payload)
