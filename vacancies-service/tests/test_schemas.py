"""Офлайн-тесты Pydantic-схем этапа 3 (без БД и SQLAlchemy session)."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.enums import (
    EmploymentType,
    ExperienceLevel,
    ParseQuality,
    ResumeOrigin,
    RunStatus,
    SourceType,
    WorkFormat,
)
from app.schemas import (
    ErrorResponse,
    MarketSkillsInfo,
    MatchCriterionBreakdown,
    MatchDetails,
    MatchSkillsBreakdown,
    NormalizedVacancy,
    ParseRunListQuery,
    ParseRunRead,
    RecommendationsQuery,
    ResumeCreate,
    ResumeExperienceCreate,
    ResumeRead,
    ResumeScoreDetails,
    ResumeScoreResponse,
    ResumeSkillCreate,
    ResumeUpdate,
    ScoreCriterionDetail,
    ScoreCriterionKey,
    ScoreIssue,
    SourceListItem,
    VacancyCardRead,
    VacancyDetailRead,
    VacancyFiltersMeta,
    VacancyListItem,
    VacancyListQuery,
    VacancySort,
)
from app.schemas.sources import source_location

VALID_HASH = "a" * 64


def _minimal_normalized(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "external_id": "msg-1",
        "source": "tg_it_jobs",
        "source_type": SourceType.TELEGRAM,
        "title": "Backend Developer",
        "description_raw": "raw",
        "description_clean": "clean",
        "parsed_at": datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
        "content_hash": VALID_HASH,
    }
    data.update(overrides)
    return data


# --- NormalizedVacancy ---


def test_normalized_vacancy_minimal_valid() -> None:
    nv = NormalizedVacancy.model_validate(_minimal_normalized())
    assert nv.parse_quality == ParseQuality.FULL
    assert nv.work_format == WorkFormat.UNKNOWN
    assert nv.skills == []
    assert nv.raw_payload == {}


def test_normalized_vacancy_partial_ok() -> None:
    nv = NormalizedVacancy.model_validate(_minimal_normalized(parse_quality=ParseQuality.PARTIAL))
    assert nv.parse_quality == ParseQuality.PARTIAL


@pytest.mark.parametrize("missing", ["title", "parsed_at", "content_hash"])
def test_normalized_vacancy_required_fields(missing: str) -> None:
    data = _minimal_normalized()
    del data[missing]
    with pytest.raises(ValidationError):
        NormalizedVacancy.model_validate(data)


def test_normalized_vacancy_bad_content_hash() -> None:
    with pytest.raises(ValidationError):
        NormalizedVacancy.model_validate(_minimal_normalized(content_hash="abcd"))
    with pytest.raises(ValidationError):
        NormalizedVacancy.model_validate(_minimal_normalized(content_hash="A" * 64))


def test_normalized_vacancy_salary_range_invalid() -> None:
    with pytest.raises(ValidationError):
        NormalizedVacancy.model_validate(
            _minimal_normalized(salary_min=200_000, salary_max=100_000)
        )


# --- ResumeExperienceCreate ---


def test_experience_end_before_or_equal_start_fails() -> None:
    with pytest.raises(ValidationError):
        ResumeExperienceCreate(
            company="Acme",
            position="Dev",
            start_date=date(2024, 6, 1),
            end_date=date(2024, 6, 1),
        )
    with pytest.raises(ValidationError):
        ResumeExperienceCreate(
            company="Acme",
            position="Dev",
            start_date=date(2024, 6, 1),
            end_date=date(2024, 5, 1),
        )


def test_experience_current_with_end_date_fails() -> None:
    with pytest.raises(ValidationError):
        ResumeExperienceCreate(
            company="Acme",
            position="Dev",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 1),
            is_current=True,
        )


def test_experience_future_date_fails() -> None:
    future = datetime.now(tz=UTC).date() + timedelta(days=30)
    with pytest.raises(ValidationError):
        ResumeExperienceCreate(
            company="Acme",
            position="Dev",
            start_date=future,
        )
    with pytest.raises(ValidationError):
        ResumeExperienceCreate(
            company="Acme",
            position="Dev",
            start_date=date(2020, 1, 1),
            end_date=future,
        )


def test_experience_current_without_end_ok() -> None:
    exp = ResumeExperienceCreate(
        company="Acme",
        position="Dev",
        start_date=date(2024, 1, 1),
        is_current=True,
        end_date=None,
    )
    assert exp.is_current is True
    assert exp.end_date is None


# --- VacancyListQuery ---


def test_vacancy_list_query_page_size_bounds() -> None:
    with pytest.raises(ValidationError):
        VacancyListQuery(page_size=0)
    with pytest.raises(ValidationError):
        VacancyListQuery(page_size=101)
    with pytest.raises(ValidationError):
        VacancyListQuery(page=0)


def test_vacancy_list_query_defaults() -> None:
    q = VacancyListQuery()
    assert q.page == 1
    assert q.page_size == 20
    assert q.exclude_hidden is True
    assert q.sort.value == "relevance"


# --- Enum serialization ---


def test_enum_serializes_as_string() -> None:
    nv = NormalizedVacancy.model_validate(_minimal_normalized(work_format=WorkFormat.REMOTE))
    dumped = nv.model_dump(mode="json")
    assert dumped["work_format"] == "remote"
    assert dumped["source_type"] == "telegram"


# --- from_attributes reads ---


def test_vacancy_card_and_detail_from_attributes() -> None:
    vid = uuid4()
    pid = uuid4()
    now = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)
    posting = SimpleNamespace(
        id=pid,
        source="tg_it_jobs",
        source_type=SourceType.TELEGRAM,
        url="https://t.me/x/1",
        external_id="1",
        published_at=now,
        parse_quality=ParseQuality.FULL,
        raw_payload={"secret": True},
        description_raw="raw",
        content_hash=VALID_HASH,
        parsed_at=now,
    )
    vacancy = SimpleNamespace(
        id=vid,
        title="Backend",
        company="Acme",
        city="Moscow",
        country="RU",
        work_format=WorkFormat.REMOTE,
        salary_min=100_000,
        salary_max=200_000,
        salary_currency="RUB",
        salary_period=None,
        salary_is_gross=True,
        skills=["python"],
        published_at=now,
        source="tg_it_jobs",
        postings_count=1,
        parse_quality=ParseQuality.FULL,
        description_clean="clean text",
        url="https://t.me/x/1",
        relocation_support=False,
        experience_min_years=2,
        experience_level=ExperienceLevel.MIDDLE,
        employment_type=EmploymentType.FULL_TIME,
        education_required=None,
        languages=["en:B2"],
        last_seen_at=now,
        source_type=SourceType.TELEGRAM,
        postings=[posting],
        raw_payload={"should_not_appear": True},
        dedup_key="x",
        search_vector=None,
        is_active=True,
        description_raw="raw",
    )
    card = VacancyCardRead.model_validate(vacancy)
    assert card.title == "Backend"
    assert "dedup_key" not in card.model_dump()

    detail = VacancyDetailRead.model_validate(vacancy)
    dumped = detail.model_dump()
    assert "raw_payload" not in dumped
    assert detail.description_clean == "clean text"
    assert len(detail.postings) == 1
    assert "raw_payload" not in detail.postings[0].model_dump()


def test_resume_read_from_attributes() -> None:
    rid = uuid4()
    uid = uuid4()
    now = datetime(2026, 2, 1, 8, 0, tzinfo=UTC)
    resume = SimpleNamespace(
        id=rid,
        user_id=uid,
        title="Main",
        is_primary=True,
        origin=ResumeOrigin.MANUAL,
        target_position="Backend",
        desired_salary_min=150_000,
        desired_salary_currency="RUB",
        desired_country="RU",
        desired_city="Moscow",
        desired_work_format=WorkFormat.REMOTE,
        summary="About me",
        contacts={},
        score=7.5,
        score_details={"completeness": 1.5},
        created_at=now,
        updated_at=now,
        experience=[],
        education=[],
        skills=[],
        courses=[],
        languages=[],
    )
    read = ResumeRead.model_validate(resume)
    assert read.score == 7.5
    assert read.contacts.email is None
    assert read.score_details == {"completeness": 1.5}


def test_source_and_parse_run_from_attributes() -> None:
    sid = uuid4()
    now = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
    source = SimpleNamespace(
        id=sid,
        slug="tg_it_jobs",
        source_type=SourceType.TELEGRAM,
        is_enabled=True,
        last_run_at=now,
        last_run_status=RunStatus.SUCCESS,
        last_error=None,
        config={"channel": "@secret"},
    )
    item = SourceListItem.model_validate(source)
    dumped = item.model_dump()
    assert "config" not in dumped
    # `location` заполняет роутер по белому списку, не from_attributes.
    assert dumped["location"] is None
    assert dumped["last_run_items_found"] is None
    assert dumped["last_run_items_new"] is None

    run = SimpleNamespace(
        id=uuid4(),
        source_id=sid,
        started_at=now,
        finished_at=now,
        status=RunStatus.SUCCESS,
        items_found=10,
        items_new=3,
        error_text=None,
    )
    parsed = ParseRunRead.model_validate(run)
    assert parsed.items_new == 3


# --- ResumeSkillCreate ---


def test_skill_accepts_any_case() -> None:
    # К канону навык приводит сервис (normalize_skills), не схема.
    assert ResumeSkillCreate(skill="Python").skill == "Python"
    with pytest.raises(ValidationError):
        ResumeSkillCreate(skill="")
    with pytest.raises(ValidationError):
        ResumeSkillCreate(skill="x" * 101)


# --- ResumeCreate / ResumeUpdate ---


def test_resume_update_rejects_null_for_required_fields() -> None:
    with pytest.raises(ValidationError):
        ResumeUpdate(title=None)
    with pytest.raises(ValidationError):
        ResumeUpdate.model_validate({"skills": None})
    assert ResumeUpdate(summary=None).model_dump(exclude_unset=True) == {"summary": None}


def test_resume_title_length_and_blank() -> None:
    with pytest.raises(ValidationError):
        ResumeCreate(title="x" * 256)
    with pytest.raises(ValidationError):
        ResumeCreate(title="   ")
    with pytest.raises(ValidationError):
        ResumeUpdate(title="")
    assert ResumeCreate(title="  Backend  ").title == "Backend"


def test_resume_duplicate_language_fails() -> None:
    languages = [
        {"language": "English", "level": "B2"},
        {"language": " english ", "level": "C1"},
    ]
    with pytest.raises(ValidationError):
        ResumeCreate.model_validate({"title": "CV", "languages": languages})
    with pytest.raises(ValidationError):
        ResumeUpdate.model_validate({"languages": languages})


def test_resume_create_forbids_user_id_and_origin() -> None:
    with pytest.raises(ValidationError):
        ResumeCreate.model_validate({"title": "CV", "user_id": str(uuid4())})
    with pytest.raises(ValidationError):
        ResumeCreate.model_validate({"title": "CV", "origin": "generated"})
    with pytest.raises(ValidationError):
        ResumeUpdate.model_validate({"origin": "generated"})


def test_resume_salary_int4_bound() -> None:
    with pytest.raises(ValidationError):
        ResumeCreate(title="CV", desired_salary_min=2_147_483_648)
    assert ResumeCreate(title="CV", desired_salary_min=2_147_483_647).desired_salary_min


# --- VacancyListQuery (этап 5) ---


def test_vacancy_list_query_blank_strings_to_none() -> None:
    query = VacancyListQuery(q="  ", country=" ", city="")
    assert query.q is None
    assert query.country is None
    assert query.city is None


def test_vacancy_list_query_has_no_skills_filter() -> None:
    with pytest.raises(ValidationError):
        VacancyListQuery.model_validate({"skills": ["python"]})


def test_vacancy_list_query_salary_without_currency_ok() -> None:
    query = VacancyListQuery(salary_min=100)
    assert query.salary_min == 100
    assert query.salary_currency is None


def test_vacancy_list_query_naive_published_after_is_utc() -> None:
    query = VacancyListQuery.model_validate({"published_after": "2026-09-01T10:00:00"})
    assert query.published_after == datetime(2026, 9, 1, 10, tzinfo=UTC)
    date_only = VacancyListQuery.model_validate({"published_after": "2026-09-01"})
    assert date_only.published_after == datetime(2026, 9, 1, tzinfo=UTC)


def test_vacancy_list_query_sources_cleaned() -> None:
    assert VacancyListQuery(source=[" a ", "", "b"]).source == ["a", "b"]
    assert VacancyListQuery(source=["  "]).source is None
    with pytest.raises(ValidationError):
        VacancyListQuery(source=[f"s{i}" for i in range(21)])


def test_vacancy_filters_meta_has_no_top_skills() -> None:
    assert "top_skills" not in VacancyFiltersMeta.model_fields
    assert "currencies" in VacancyFiltersMeta.model_fields


def test_skill_level_bounds() -> None:
    with pytest.raises(ValidationError):
        ResumeSkillCreate(skill="python", level=0)
    with pytest.raises(ValidationError):
        ResumeSkillCreate(skill="python", level=6)


# --- Scoring ---


def test_resume_score_response_upper_bound() -> None:
    with pytest.raises(ValidationError):
        ResumeScoreResponse(score=10.1, recommendations=[], score_details=[])


def test_match_details_zero_points() -> None:
    details = MatchDetails(
        skills=MatchSkillsBreakdown(matched=[], missing=["python"], points=0, reason="ratio"),
        level=MatchCriterionBreakdown(points=0, max_points=20, reason="gap"),
        salary=MatchCriterionBreakdown(points=0, max_points=15, reason="below"),
        location=MatchCriterionBreakdown(points=0, max_points=12, reason="mismatch"),
        freshness=MatchCriterionBreakdown(points=0, max_points=8, reason="older"),
    )
    assert details.skills.points == 0
    assert details.level.points == 0
    assert details.level.context == {}


def test_match_breakdown_requires_reason() -> None:
    with pytest.raises(ValidationError):
        MatchCriterionBreakdown.model_validate({"points": 0, "max_points": 8})


def _criteria(keys: list[ScoreCriterionKey]) -> list[ScoreCriterionDetail]:
    return [ScoreCriterionDetail(key=key, name=key.value, weight=1, points=0) for key in keys]


def _score_details(keys: list[ScoreCriterionKey]) -> dict[str, object]:
    return {
        "version": 1,
        "score": 0,
        "criteria": _criteria(keys),
        "recommendations": [],
        "market": {"basis": "none", "sample_size": 0, "top_skills": []},
    }


def test_resume_score_details_requires_all_eight_criteria() -> None:
    keys = list(ScoreCriterionKey)
    assert ResumeScoreDetails.model_validate(_score_details(keys)).version == 1
    with pytest.raises(ValidationError):
        ResumeScoreDetails.model_validate(_score_details(keys[:7]))
    with pytest.raises(ValidationError):
        ResumeScoreDetails.model_validate(_score_details(keys[::-1]))


def test_score_criterion_detail_without_issues_is_valid() -> None:
    detail = ScoreCriterionDetail(
        key=ScoreCriterionKey.LANGUAGES, name="Языки", weight=0.5, points=0.5
    )
    assert detail.issues == []
    assert detail.recommendation is None
    issue = ScoreIssue(code="gap", context={"months": 10, "trailing": False, "from": "2021-03"})
    assert issue.context["trailing"] is False
    assert MarketSkillsInfo(basis="none", sample_size=0, top_skills=[]).top_skills == []


def test_recommendations_query_bounds() -> None:
    query = RecommendationsQuery()
    assert query.resume_id is None
    assert query.exclude_hidden is True
    assert query.limit == 50
    assert RecommendationsQuery(limit=200).limit == 200
    for bad in (0, 201):
        with pytest.raises(ValidationError):
            RecommendationsQuery(limit=bad)
    with pytest.raises(ValidationError):
        RecommendationsQuery.model_validate({"page": 1})


# --- Лента с матчем и источники (этап 8) ---


def test_sort_match_requires_resume_id() -> None:
    with pytest.raises(ValidationError, match="sort=match requires resume_id"):
        VacancyListQuery(sort=VacancySort.MATCH)
    query = VacancyListQuery(sort=VacancySort.MATCH, resume_id=uuid4())
    assert query.sort == VacancySort.MATCH
    assert VacancyListQuery(resume_id=uuid4()).sort == VacancySort.RELEVANCE


def test_vacancy_list_item_defaults() -> None:
    fields = VacancyListItem.model_fields
    assert {"sources", "match_score", "match_details"} <= fields.keys()
    for bad in (-1, 101):
        with pytest.raises(ValidationError):
            VacancyListItem.model_validate(
                {
                    "id": uuid4(),
                    "title": "t",
                    "company": None,
                    "city": None,
                    "country": None,
                    "work_format": WorkFormat.REMOTE,
                    "salary_min": None,
                    "salary_max": None,
                    "salary_currency": None,
                    "salary_period": None,
                    "salary_is_gross": None,
                    "skills": [],
                    "published_at": None,
                    "source": "tg_it_jobs",
                    "postings_count": 1,
                    "parse_quality": ParseQuality.FULL,
                    "match_score": bad,
                }
            )


def test_parse_run_list_query_bounds() -> None:
    query = ParseRunListQuery()
    assert (query.source_id, query.status, query.limit) == (None, None, 50)
    assert ParseRunListQuery(limit=200).limit == 200
    for bad in (0, 201):
        with pytest.raises(ValidationError):
            ParseRunListQuery(limit=bad)
    with pytest.raises(ValidationError):
        ParseRunListQuery.model_validate({"page": 1})


@pytest.mark.parametrize(
    ("source_type", "config", "expected"),
    [
        (SourceType.TELEGRAM, {"channel": "@jobs", "url": "https://x"}, "@jobs"),
        (SourceType.HTML, {"url": "https://x", "channel": "@jobs"}, "https://x"),
        (SourceType.HTML, {"url": 42}, None),
        (SourceType.HTML, {"url": ""}, None),
        (SourceType.TELEGRAM, {}, None),
        (SourceType.API, {"url": "https://api"}, None),
    ],
)
def test_source_location_whitelist(
    source_type: SourceType, config: dict[str, object], expected: str | None
) -> None:
    assert source_location(source_type, config) == expected


# --- ErrorResponse ---


def test_error_response_parses_envelope() -> None:
    payload = {
        "error": {
            "code": "NOT_FOUND",
            "message": "Requested resource was not found",
            "details": {},
        }
    }
    err = ErrorResponse.model_validate(payload)
    assert err.error.code == "NOT_FOUND"
    assert err.error.details == {}
