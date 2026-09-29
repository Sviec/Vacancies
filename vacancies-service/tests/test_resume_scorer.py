"""Оценка резюме п. 5.4: таблицы по критериям, инварианты, рекомендации."""

import json
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Any

import pytest

from app.enums import LanguageLevel, WorkFormat
from app.schemas.scoring import ResumeScoreDetails, ScoreCriterionDetail, ScoreCriterionKey
from app.services.resume_scorer import (
    CRITERIA_NAMES,
    CRITERIA_WEIGHTS,
    EMPTY_MARKET,
    MarketSkills,
    ResumeSnapshot,
    ScoreResult,
    canonical_skills,
    has_metric,
    q2,
    render_recommendation,
    score_resume,
)

Key = ScoreCriterionKey
TODAY = date(2026, 9, 28)

MARKET_20 = MarketSkills(
    basis="target_position",
    sample_size=40,
    top_skills=tuple(f"m{i:02d}" for i in range(20)),
)


@dataclass(frozen=True)
class Exp:
    company: str
    position: str
    start_date: date
    end_date: date | None = None
    is_current: bool = False
    description: str | None = None
    achievements: str | None = None


def snap(**overrides: Any) -> ResumeSnapshot:
    base: dict[str, Any] = {
        "target_position": None,
        "desired_salary_min": None,
        "desired_salary_currency": None,
        "desired_country": None,
        "desired_city": None,
        "desired_work_format": None,
        "summary": None,
        "contacts": {},
        "experience": (),
        "education_count": 0,
        "course_count": 0,
        "skills": (),
        "language_levels": (),
    }
    base.update(overrides)
    return ResumeSnapshot(**base)


def current(**overrides: Any) -> Exp:
    fields: dict[str, Any] = {
        "company": "Яндекс",
        "position": "Backend-разработчик",
        "start_date": date(2022, 1, 1),
        "is_current": True,
    }
    fields.update(overrides)
    return Exp(**fields)


def criterion(result: ScoreResult, key: ScoreCriterionKey) -> ScoreCriterionDetail:
    return next(item for item in result.criteria if item.key == key)


def points(
    resume: ResumeSnapshot, key: ScoreCriterionKey, market: MarketSkills = EMPTY_MARKET
) -> float:
    return criterion(score_resume(resume, market, TODAY), key).points


def skills(n: int, prefix: str = "s") -> tuple[str, ...]:
    return tuple(f"{prefix}{i:02d}" for i in range(n))


def full_resume() -> ResumeSnapshot:
    text = "Разрабатывал сервисы поиска на Python и FastAPI, " * 5
    return snap(
        target_position="Senior Python Developer",
        desired_salary_min=300_000,
        desired_salary_currency="RUB",
        desired_city="Москва",
        desired_work_format=WorkFormat.REMOTE,
        summary="Бэкенд на Python",
        contacts={"email": "a@b.c"},
        experience=(
            current(description=text, achievements="Ускорил выдачу на 30%"),
            Exp(
                "Ozon",
                "Python Developer",
                date(2019, 1, 1),
                date(2022, 1, 1),
                description=text,
                achievements="Снизил задержку в 2 раза",
            ),
        ),
        education_count=1,
        course_count=1,
        skills=tuple(sorted(MARKET_20.top_skills[:10])),
        language_levels=(LanguageLevel.B2,),
    )


# --- q2 и константы ---


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Fraction(0), Decimal("0.00")),
        (Fraction(1125, 1000), Decimal("1.13")),
        (Fraction(21, 16), Decimal("1.31")),
        (Fraction(2, 3), Decimal("0.67")),
        (Fraction(1, 3), Decimal("0.33")),
        (Fraction(45, 2), Decimal("22.50")),
        (Fraction(5, 1000), Decimal("0.01")),
    ],
)
def test_q2_rounds_half_up(value: Fraction, expected: Decimal) -> None:
    assert q2(value) == expected


def test_weights_sum_to_ten_and_names() -> None:
    assert sum(CRITERIA_WEIGHTS.values()) == 10
    assert list(CRITERIA_WEIGHTS) == list(ScoreCriterionKey)
    assert set(CRITERIA_NAMES) == set(ScoreCriterionKey)


# --- 1. Полнота ---


@pytest.mark.parametrize(
    ("overrides", "expected", "recommended"),
    [
        ({}, 0.0, True),
        ({"experience": (current(),)}, 0.4, True),
        ({"experience": (current(),), "education_count": 1, "skills": ("python",)}, 1.2, True),
        (
            {
                "experience": (current(),),
                "education_count": 1,
                "skills": ("python",),
                "summary": "О себе",
            },
            1.6,
            False,
        ),
        (
            {
                "experience": (current(),),
                "education_count": 1,
                "skills": ("python",),
                "summary": "О себе",
                "contacts": {"email": "a@b.c", "phone": None},
            },
            2.0,
            False,
        ),
        ({"summary": "   ", "contacts": {"email": "  ", "phone": None}}, 0.0, True),
    ],
)
def test_completeness(overrides: dict[str, Any], expected: float, recommended: bool) -> None:
    detail = criterion(score_resume(snap(**overrides), EMPTY_MARKET, TODAY), Key.COMPLETENESS)
    assert detail.points == expected
    assert (detail.recommendation is not None) is recommended


def test_completeness_issues_name_blocks() -> None:
    detail = criterion(
        score_resume(snap(experience=(current(),)), EMPTY_MARKET, TODAY), Key.COMPLETENESS
    )
    assert [i.context["block"] for i in detail.issues] == [
        "education",
        "skills",
        "summary",
        "contacts",
    ]
    assert detail.recommendation is not None
    assert "образование" in detail.recommendation
    assert "контакты" in detail.recommendation


# --- 2. Качество опыта ---


@pytest.mark.parametrize(
    ("length", "with_achievements", "expected"),
    [
        (99, False, 0.8),
        (100, False, 1.1),
        (199, False, 1.1),
        (200, False, 1.4),
        (1500, False, 1.4),
        (1501, False, 1.1),
        (3000, False, 1.1),
        (3001, False, 0.8),
        (200, True, 2.0),
        (0, True, 0.6),
        (0, False, 0.0),
    ],
)
def test_experience_quality_single_position(
    length: int, with_achievements: bool, expected: float
) -> None:
    description = "a" * length if length else None
    achievements = "Запустил сервис" if with_achievements else None
    resume = snap(experience=(current(description=description, achievements=achievements),))
    assert points(resume, Key.EXPERIENCE_QUALITY) == expected


def test_experience_quality_average_and_issues() -> None:
    resume = snap(
        experience=(
            current(description="a" * 300, achievements="Сделал"),
            Exp("Ozon", "Dev", date(2019, 1, 1), date(2021, 12, 1), description="коротко"),
        )
    )
    detail = criterion(score_resume(resume, EMPTY_MARKET, TODAY), Key.EXPERIENCE_QUALITY)
    # (1 + 2/5) / 2 = 7/10 → 1.4; ровно 0.7 — без рекомендации.
    assert detail.points == 1.4
    assert detail.recommendation is None
    assert [(i.code, i.context.get("length")) for i in detail.issues] == [
        ("description_too_short", 7),
        ("no_achievements", None),
    ]


def test_experience_quality_without_experience() -> None:
    detail = criterion(score_resume(snap(), EMPTY_MARKET, TODAY), Key.EXPERIENCE_QUALITY)
    assert detail.points == 0
    assert [i.code for i in detail.issues] == ["no_experience"]
    assert detail.recommendation is not None


def test_experience_quality_too_long_issue() -> None:
    resume = snap(experience=(current(description="a" * 1600, achievements="x"),))
    detail = criterion(score_resume(resume, EMPTY_MARKET, TODAY), Key.EXPERIENCE_QUALITY)
    assert detail.issues[0].code == "description_too_long"
    assert detail.issues[0].context["length"] == 1600


# --- 3. Измеримые достижения ---


@pytest.mark.parametrize(
    "text",
    [
        "Ускорил выдачу на 30%",
        "Рост конверсии на 12,5 %",
        "Сократил время сборки в 2 раза",
        "Ускорение x3",
        "Производительность выросла в 4х",
        "Держит 10k RPS",
        "Обработка 1,5 млн событий в сутки",
        "Бюджет 300 тыс. рублей",
        "Сократил деплой на 40 минут",
        "Команда из 12 человек",
        "Выручка 2M в год",
    ],
)
def test_metric_regex_matches(text: str) -> None:
    assert has_metric(text)


@pytest.mark.parametrize(
    "text",
    [
        "Работал в 2019–2021",
        "Python 3.11",
        "Работаю с 2020 года",
        "1 проект",
        "Версия 12.3 сервиса",
        "",
        "Разрабатывал API",
        "1 команда",
    ],
)
def test_metric_regex_rejects(text: str) -> None:
    assert not has_metric(text)


@pytest.mark.parametrize(
    ("achievements", "expected"),
    [
        (("на 30%", "в 2 раза"), 1.5),
        (("на 30%", "без цифр"), 0.75),
        (("без цифр", "тоже без"), 0.0),
    ],
)
def test_measurable_achievements(achievements: tuple[str, str], expected: float) -> None:
    first, second = achievements
    resume = snap(
        experience=(
            current(achievements=first),
            Exp("Ozon", "Dev", date(2019, 1, 1), date(2021, 12, 1), description=second),
        )
    )
    assert points(resume, Key.MEASURABLE_ACHIEVEMENTS) == expected


def test_measurable_recommendation_names_position() -> None:
    resume = snap(experience=(current(description="Писал код"),))
    detail = criterion(score_resume(resume, EMPTY_MARKET, TODAY), Key.MEASURABLE_ACHIEVEMENTS)
    assert detail.recommendation == (
        "Добавьте измеримые результаты в описание позиции «Backend-разработчик» "
        "в компании Яндекс — например, на сколько % выросла метрика или во сколько "
        "раз ускорился процесс"
    )
    empty = criterion(score_resume(snap(), EMPTY_MARKET, TODAY), Key.MEASURABLE_ACHIEVEMENTS)
    assert [i.code for i in empty.issues] == ["no_experience"]


def test_recommendation_names_two_positions_and_rest() -> None:
    experience = tuple(
        Exp(f"Company{i}", f"Dev{i}", date(2010 + i, 1, 1), date(2010 + i, 12, 1)) for i in range(4)
    )
    detail = criterion(
        score_resume(snap(experience=experience), EMPTY_MARKET, TODAY),
        Key.MEASURABLE_ACHIEVEMENTS,
    )
    assert detail.recommendation is not None
    # Свежие позиции первыми.
    assert "«Dev3» в компании Company3, «Dev2» в компании Company2 и ещё 2" in (
        detail.recommendation
    )


# --- 4. Релевантность навыков ---


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, 0.0), (1, 0.19), (7, 1.31), (8, 1.5), (15, 1.5), (16, 0.75)],
)
def test_skills_count_without_market(count: int, expected: float) -> None:
    assert points(snap(skills=skills(count)), Key.SKILLS_RELEVANCE) == expected


@pytest.mark.parametrize(("matched", "expected"), [(0, 0.75), (5, 1.13), (10, 1.5), (12, 1.5)])
def test_skills_market_share(matched: int, expected: float) -> None:
    resume_skills = MARKET_20.top_skills[:matched] + skills(12 - matched)
    resume = snap(skills=tuple(sorted(resume_skills)))
    assert points(resume, Key.SKILLS_RELEVANCE, MARKET_20) == expected


def test_small_market_targets_its_size() -> None:
    market = MarketSkills(basis="all_vacancies", sample_size=3, top_skills=("a", "b", "c"))
    all_three = snap(skills=tuple(sorted(("a", "b", "c", *skills(5)))))
    one = snap(skills=tuple(sorted(("a", *skills(7)))))
    assert points(all_three, Key.SKILLS_RELEVANCE, market) == 1.5
    # 1/2 + (1/3)/2 = 2/3 → 1.0
    assert points(one, Key.SKILLS_RELEVANCE, market) == 1.0


def test_empty_market_uses_count_only() -> None:
    market = MarketSkills(basis="all_vacancies", sample_size=0, top_skills=())
    assert points(snap(skills=skills(8)), Key.SKILLS_RELEVANCE, market) == 1.5


def test_skills_issues_and_recommendation() -> None:
    resume = snap(skills=("m00", "python"))
    detail = criterion(score_resume(resume, MARKET_20, TODAY), Key.SKILLS_RELEVANCE)
    assert [i.code for i in detail.issues] == ["too_few_skills", "missing_market_skills"]
    assert detail.issues[1].context == {
        "skills": "m01, m02, m03, m04, m05",
        "basis": "target_position",
    }
    assert detail.recommendation is not None
    assert "Добавьте навыки, частые в вакансиях по вашей позиции: m01, m02" in (
        detail.recommendation
    )
    many = criterion(
        score_resume(snap(skills=skills(16)), EMPTY_MARKET, TODAY), Key.SKILLS_RELEVANCE
    )
    assert many.issues[0].code == "too_many_skills"
    assert many.recommendation is not None
    assert "Сократите" in many.recommendation


def test_skills_all_vacancies_wording() -> None:
    market = replace(MARKET_20, basis="all_vacancies")
    detail = criterion(score_resume(snap(), market, TODAY), Key.SKILLS_RELEVANCE)
    assert detail.recommendation is not None
    assert "частые в вакансиях рынка: m00" in detail.recommendation


# --- 5. Хронология ---


@pytest.mark.parametrize(
    ("experience", "expected"),
    [
        ((), 0.0),
        ((current(),), 1.0),
        (
            (
                current(start_date=date(2020, 7, 1)),
                Exp("A", "Dev", date(2019, 1, 1), date(2020, 1, 1)),
            ),
            1.0,
        ),
        (
            (
                current(start_date=date(2020, 7, 2)),
                Exp("A", "Dev", date(2019, 1, 1), date(2020, 1, 1)),
            ),
            0.65,
        ),
        (
            (
                current(start_date=date(2023, 1, 1)),
                Exp("A", "Dev", date(2019, 1, 1), date(2020, 1, 1)),
                Exp("B", "Dev", date(2021, 1, 1), date(2022, 1, 1)),
            ),
            0.3,
        ),
        ((current(), Exp("A", "Dev", date(2022, 5, 1))), 0.7),
        ((Exp("A", "Dev", date(2019, 1, 1), date(2025, 1, 1)),), 0.65),
    ],
)
def test_chronology(experience: tuple[Exp, ...], expected: float) -> None:
    assert points(snap(experience=experience), Key.CHRONOLOGY) == expected


def test_chronology_gap_recommendation() -> None:
    resume = snap(
        experience=(
            current(start_date=date(2022, 1, 1)),
            Exp("A", "Dev", date(2019, 1, 1), date(2021, 3, 1)),
        )
    )
    detail = criterion(score_resume(resume, EMPTY_MARKET, TODAY), Key.CHRONOLOGY)
    assert detail.issues[0].model_dump() == {
        "code": "gap",
        "context": {"from": "2021-03", "to": "2022-01", "months": 10, "trailing": False},
    }
    assert detail.recommendation == (
        "Заполните пробел с 2021-03 по 2022-01 (10 мес.) — укажите, чем занимались: "
        "курсы, фриланс, пет-проекты"
    )


def test_chronology_missing_end_is_issue_without_recommendation() -> None:
    resume = snap(experience=(current(), Exp("A", "Dev", date(2022, 5, 1))))
    detail = criterion(score_resume(resume, EMPTY_MARKET, TODAY), Key.CHRONOLOGY)
    assert [i.code for i in detail.issues] == ["missing_end_date"]
    assert detail.recommendation is None


def test_chronology_missing_end_recommendation() -> None:
    resume = snap(
        experience=(
            Exp("A", "Dev", date(2025, 5, 1)),
            Exp("B", "QA", date(2018, 1, 1), date(2019, 1, 1)),
        )
    )
    detail = criterion(score_resume(resume, EMPTY_MARKET, TODAY), Key.CHRONOLOGY)
    # Пробел между позициями и хвостовой: у позиции без даты окончания длина 0.
    assert [i.code for i in detail.issues] == ["gap", "gap", "missing_end_date"]
    assert [i.context.get("trailing") for i in detail.issues[:2]] == [False, True]
    assert detail.points == 0
    assert detail.recommendation is not None
    assert "Заполните пробелы с 2019-01 по 2025-05" in detail.recommendation
    assert "Укажите дату окончания позиции «Dev» в компании A" in detail.recommendation


# --- 6–8. Образование, языки, цели ---


@pytest.mark.parametrize(
    ("education", "courses", "expected", "codes"),
    [
        (0, 0, 0.0, ["missing_education", "missing_courses"]),
        (1, 0, 0.6, ["missing_courses"]),
        (0, 2, 0.4, ["missing_education"]),
        (1, 1, 1.0, []),
    ],
)
def test_education_courses(education: int, courses: int, expected: float, codes: list[str]) -> None:
    resume = snap(education_count=education, course_count=courses)
    detail = criterion(score_resume(resume, EMPTY_MARKET, TODAY), Key.EDUCATION_COURSES)
    assert detail.points == expected
    assert [i.code for i in detail.issues] == codes


def test_education_recommendations() -> None:
    texts = [
        render_recommendation(
            Key.EDUCATION_COURSES,
            criterion(
                score_resume(snap(education_count=e, course_count=c), EMPTY_MARKET, TODAY),
                Key.EDUCATION_COURSES,
            ).issues,
        )
        for e, c in ((0, 0), (0, 1), (1, 0), (1, 1))
    ]
    assert texts[0] is not None
    assert "образование и пройденные курсы" in texts[0]
    assert texts[1] is not None
    assert texts[1].startswith("Добавьте образование:")
    assert texts[2] is not None
    assert "курсы" in texts[2]
    assert texts[3] is None


@pytest.mark.parametrize(
    ("levels", "expected"),
    [((), 0.0), ((LanguageLevel.A1,), 0.5), ((LanguageLevel.NATIVE, LanguageLevel.B2), 0.5)],
)
def test_languages(levels: tuple[LanguageLevel, ...], expected: float) -> None:
    assert points(snap(language_levels=levels), Key.LANGUAGES) == expected


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, 0.0),
        ({"target_position": "Python Developer"}, 0.13),
        ({"desired_salary_min": 100}, 0.0),
        ({"desired_salary_min": 100, "desired_salary_currency": "RUB"}, 0.13),
        ({"desired_city": "  ", "desired_country": "Россия"}, 0.13),
        ({"desired_work_format": WorkFormat.UNKNOWN}, 0.13),
        (
            {
                "target_position": "Dev",
                "desired_salary_min": 1,
                "desired_salary_currency": "USD",
                "desired_city": "Москва",
                "desired_work_format": WorkFormat.REMOTE,
            },
            0.5,
        ),
    ],
)
def test_goals(overrides: dict[str, Any], expected: float) -> None:
    assert points(snap(**overrides), Key.GOALS_SPECIFICITY) == expected


def test_goals_recommendation_lists_missing_fields() -> None:
    detail = criterion(
        score_resume(snap(target_position="Dev"), EMPTY_MARKET, TODAY), Key.GOALS_SPECIFICITY
    )
    assert [i.context["field"] for i in detail.issues] == ["salary", "location", "work_format"]
    assert detail.recommendation == (
        "Уточните цели поиска: укажите желаемую зарплату с валютой, город или страну, формат работы"
    )


# --- Инварианты ---


def _decimal_sum(result: ScoreResult) -> Decimal:
    return sum((Decimal(str(c.points)) for c in result.criteria), Decimal(0))


@pytest.mark.parametrize("resume", [snap(), full_resume()], ids=["empty", "full"])
def test_invariants(resume: ResumeSnapshot) -> None:
    result = score_resume(resume, MARKET_20, TODAY)
    assert [c.key for c in result.criteria] == list(ScoreCriterionKey)
    for detail in result.criteria:
        assert 0 <= detail.points <= detail.weight
        assert detail.weight == float(CRITERIA_WEIGHTS[detail.key])
    assert 0 <= result.score <= 10
    assert Decimal(str(result.score)) == _decimal_sum(result)
    ResumeScoreDetails.model_validate(result.to_details())


def test_empty_resume_scores_zero() -> None:
    result = score_resume(snap(), EMPTY_MARKET, TODAY)
    assert result.score == 0.0
    assert len(result.criteria) == 8
    assert len(result.recommendations) == 8


def test_full_resume_scores_ten_without_recommendations() -> None:
    result = score_resume(full_resume(), MARKET_20, TODAY)
    assert result.score == 10.0
    assert result.recommendations == []
    # Проблема записана и у прошедшего критерия.
    skills_detail = criterion(result, Key.SKILLS_RELEVANCE)
    assert [i.code for i in skills_detail.issues] == ["missing_market_skills"]
    assert skills_detail.recommendation is None


def _dump(result: ScoreResult) -> str:
    return json.dumps(result.to_details(), sort_keys=True, ensure_ascii=False)


def test_repeated_runs_are_byte_identical() -> None:
    resume = replace(full_resume(), summary=None, course_count=0)
    assert _dump(score_resume(resume, MARKET_20, TODAY)) == _dump(
        score_resume(resume, MARKET_20, TODAY)
    )


def test_permutation_of_experience_and_skills_does_not_change_result() -> None:
    base = snap(
        experience=(
            current(description="Писал код", achievements=None),
            Exp("Ozon", "Dev", date(2019, 1, 1), date(2020, 1, 1)),
            Exp("Avito", "Dev", date(2016, 1, 1), date(2017, 1, 1), description="на 30%"),
            Exp("Avito", "Dev", date(2016, 1, 1)),
        ),
        skills=canonical_skills(["Python", "JS", "docker", "m03"]),
    )
    shuffled = replace(
        base,
        experience=tuple(base.experience[i] for i in (2, 0, 3, 1)),
        skills=canonical_skills(["m03", "Docker", "javascript", "python", "js"]),
    )
    assert base.skills == shuffled.skills == ("docker", "javascript", "m03", "python")
    assert _dump(score_resume(base, MARKET_20, TODAY)) == _dump(
        score_resume(shuffled, MARKET_20, TODAY)
    )


# --- Рекомендации ---


def test_recommendations_only_below_threshold_and_ordered_by_loss() -> None:
    resume = replace(
        full_resume(),
        experience=(current(description="a" * 300, achievements="Сделал"),),
        course_count=0,
        language_levels=(),
        summary=None,
        contacts={},
    )
    result = score_resume(resume, MARKET_20, TODAY)
    with_rec = [c.key for c in result.criteria if c.recommendation is not None]
    # Полнота 3/5 (потеря 0.8), достижения 0 (1.5), образование 3/5 (0.4), языки 0 (0.5).
    assert with_rec == [
        Key.COMPLETENESS,
        Key.MEASURABLE_ACHIEVEMENTS,
        Key.EDUCATION_COURSES,
        Key.LANGUAGES,
    ]
    by_key = {c.key: c.recommendation for c in result.criteria}
    assert result.recommendations == [
        by_key[Key.MEASURABLE_ACHIEVEMENTS],
        by_key[Key.COMPLETENESS],
        by_key[Key.LANGUAGES],
        by_key[Key.EDUCATION_COURSES],
    ]


def test_equal_losses_keep_enum_order() -> None:
    result = score_resume(snap(), EMPTY_MARKET, TODAY)
    keys = [
        next(c.key for c in result.criteria if c.recommendation == text)
        for text in result.recommendations
    ]
    assert keys == [
        Key.COMPLETENESS,
        Key.EXPERIENCE_QUALITY,
        Key.MEASURABLE_ACHIEVEMENTS,
        Key.SKILLS_RELEVANCE,
        Key.CHRONOLOGY,
        Key.EDUCATION_COURSES,
        Key.LANGUAGES,
        Key.GOALS_SPECIFICITY,
    ]


@pytest.mark.parametrize("key", list(ScoreCriterionKey))
def test_render_without_issues_is_none(key: ScoreCriterionKey) -> None:
    assert render_recommendation(key, []) is None
