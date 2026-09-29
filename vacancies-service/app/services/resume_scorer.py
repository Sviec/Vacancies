"""Детерминированная оценка резюме по 8 критериям п. 5.4 ТЗ (0–10).

Чистый модуль: ни БД, ни часов, ни LLM. «Сегодня» и частотные навыки рынка —
параметры, поэтому один и тот же вход всегда даёт побайтно одинаковый выход.

Числа считаются точно: доли — `Fraction`, каждая компонента округляется в
`Decimal` до 0.01 (ROUND_HALF_UP), итог — точная сумма округлённых компонент.
`float` появляется только на выходе.
"""

import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal

from app.enums import LanguageLevel, WorkFormat
from app.schemas.scoring import (
    MarketSkillsInfo,
    ResumeScoreDetails,
    ScoreCriterionDetail,
    ScoreCriterionKey,
    ScoreIssue,
)
from app.services.normalizer import normalize_skills
from app.services.timeline import ExperienceLike, find_gaps, position_spans

if TYPE_CHECKING:
    from app.db.models import Resume

Key = ScoreCriterionKey

# TODO: компоненты округляются до 0.01 (ROUND_HALF_UP), итог — точная сумма
# округлённых компонент; `score` резюме хранится с двумя знаками.
CRITERIA_WEIGHTS: Final[Mapping[ScoreCriterionKey, Fraction]] = MappingProxyType(
    {
        Key.COMPLETENESS: Fraction(2),
        Key.EXPERIENCE_QUALITY: Fraction(2),
        Key.MEASURABLE_ACHIEVEMENTS: Fraction(3, 2),
        Key.SKILLS_RELEVANCE: Fraction(3, 2),
        Key.CHRONOLOGY: Fraction(1),
        Key.EDUCATION_COURSES: Fraction(1),
        Key.LANGUAGES: Fraction(1, 2),
        Key.GOALS_SPECIFICITY: Fraction(1, 2),
    }
)

CRITERIA_NAMES: Final[Mapping[ScoreCriterionKey, str]] = MappingProxyType(
    {
        Key.COMPLETENESS: "Полнота заполнения",
        Key.EXPERIENCE_QUALITY: "Качество описания опыта",
        Key.MEASURABLE_ACHIEVEMENTS: "Измеримые достижения",
        Key.SKILLS_RELEVANCE: "Релевантность навыков",
        Key.CHRONOLOGY: "Хронология",
        Key.EDUCATION_COURSES: "Образование и курсы",
        Key.LANGUAGES: "Языки",
        Key.GOALS_SPECIFICITY: "Конкретность целей",
    }
)

RECOMMENDATION_THRESHOLD: Final = Fraction(7, 10)

MarketBasis = Literal["target_position", "all_vacancies", "none"]

_HALF = Fraction(1, 2)
_ONE = Fraction(1)
_ZERO = Fraction(0)

# TODO: длина описания — только `description`; частичные баллы за 100–199
# и 1501–3000 символов.
_DESC_PRESENT = Fraction(2, 5)
_ACH_PRESENT = Fraction(3, 10)
_LENGTH_FULL = Fraction(3, 10)
_LENGTH_PARTIAL = Fraction(3, 20)
_LENGTH_SHORT = 100
_LENGTH_OK_MIN = 200
_LENGTH_OK_MAX = 1500
_LENGTH_LONG_MAX = 3000

# TODO: оптимум навыков 8–15, больше 15 — половина баллов за количество.
_SKILLS_OPTIMUM_MIN = 8
_SKILLS_OPTIMUM_MAX = 15
_MARKET_TARGET = 10
_MISSING_MARKET_SHOWN = 5

_GAPS_WEIGHT = Fraction(7, 10)
_CONSISTENCY_WEIGHT = Fraction(3, 10)
_EDUCATION_WEIGHT = Fraction(3, 5)
_COURSES_WEIGHT = Fraction(2, 5)

_NAMED_POSITIONS = 2

# TODO: метрика — регулярка (%, кратность, k/млн, число из ≥2 цифр кроме
# годов и версий); ложные срабатывания вроде «команда из 12 человек» допустимы.
METRIC_RE: Final = re.compile(
    r"\d+(?:[.,]\d+)?\s*%"
    r"|\d+(?:[.,]\d+)?\s*(?:x|х|раза?)\b"
    r"|\b[xх]\s?\d+\b"
    r"|\d+(?:[.,]\d+)?\s*(?:k|к|тыс\.?|млн|mln|m|млрд)(?!\w)"
    r"|(?<![\w.,])(?!(?:19|20)\d{2}(?!\d))\d{2,}(?![.,]?\d)",
    re.IGNORECASE,
)


def _filled(value: str | None) -> bool:
    # TODO: «непустое» — `strip() != ""`; контакты заполнены, если есть
    # хотя бы одно непустое значение.
    return value is not None and value.strip() != ""


def _text_length(value: str | None) -> int:
    return len(value.strip()) if value is not None else 0


def q2(value: Fraction) -> Decimal:
    """Округлить до 0.01 по ROUND_HALF_UP точно: floor(value·100 + ½) / 100."""
    return Decimal(math.floor(value * 100 + _HALF)).scaleb(-2)


@dataclass(frozen=True, slots=True)
class MarketSkills:
    """Частотные навыки рынка, на которых считается половина критерия навыков."""

    basis: MarketBasis
    sample_size: int
    top_skills: tuple[str, ...]


EMPTY_MARKET: Final = MarketSkills(basis="none", sample_size=0, top_skills=())


@dataclass(frozen=True, slots=True)
class ResumeSnapshot:
    """Всё, что нужно скореру, без ORM-сессии."""

    target_position: str | None
    desired_salary_min: int | None
    desired_salary_currency: str | None
    desired_country: str | None
    desired_city: str | None
    desired_work_format: WorkFormat | None
    summary: str | None
    contacts: Mapping[str, str | None]
    experience: tuple[ExperienceLike, ...]
    education_count: int
    course_count: int
    skills: tuple[str, ...]
    language_levels: tuple[LanguageLevel, ...]

    @classmethod
    def from_resume(cls, resume: "Resume") -> "ResumeSnapshot":
        return cls(
            target_position=resume.target_position,
            desired_salary_min=resume.desired_salary_min,
            desired_salary_currency=resume.desired_salary_currency,
            desired_country=resume.desired_country,
            desired_city=resume.desired_city,
            desired_work_format=resume.desired_work_format,
            summary=resume.summary,
            contacts=dict(resume.contacts or {}),
            experience=tuple(resume.experience),
            education_count=len(resume.education),
            course_count=len(resume.courses),
            skills=canonical_skills(skill.skill for skill in resume.skills),
            language_levels=tuple(sorted(language.level for language in resume.languages)),
        )


def canonical_skills(skills: Iterable[str]) -> tuple[str, ...]:
    """Канонизированные навыки без повторов, по алфавиту."""
    return tuple(sorted(normalize_skills(skills)))


@dataclass(frozen=True, slots=True)
class ScoreResult:
    """Итог оценки: балл, 8 критериев, рекомендации и срез рынка."""

    score: float
    criteria: list[ScoreCriterionDetail]
    recommendations: list[str]
    market: MarketSkills

    def to_details(self) -> dict[str, Any]:
        """Форма JSONB `resumes.score_details`."""
        return ResumeScoreDetails(
            version=1,
            score=self.score,
            criteria=self.criteria,
            recommendations=self.recommendations,
            market=MarketSkillsInfo(
                basis=self.market.basis,
                sample_size=self.market.sample_size,
                top_skills=list(self.market.top_skills),
            ),
        ).model_dump(mode="json")


@dataclass(frozen=True, slots=True)
class _Criterion:
    ratio: Fraction
    issues: list[ScoreIssue]


def _issue(code: str, **context: str | int | bool) -> ScoreIssue:
    return ScoreIssue(code=code, context=context)


def _position_context(item: ExperienceLike) -> dict[str, str | int | bool]:
    return {"company": item.company, "position": item.position}


def _ordered_positions(experience: Sequence[ExperienceLike]) -> list[ExperienceLike]:
    """Стабильный порядок `(start_date DESC, company, position)` с полным разрывом ничьих."""
    return sorted(
        experience,
        key=lambda e: (
            -e.start_date.toordinal(),
            e.company,
            e.position,
            -(e.end_date.toordinal() if e.end_date is not None else 0),
            e.is_current,
            e.description or "",
            e.achievements or "",
        ),
    )


# --- Критерии ---


def _completeness(resume: ResumeSnapshot) -> _Criterion:
    blocks = {
        "experience": bool(resume.experience),
        "education": resume.education_count > 0,
        "skills": bool(resume.skills),
        "summary": _filled(resume.summary),
        "contacts": any(_filled(value) for value in resume.contacts.values()),
    }
    issues = [_issue("missing_block", block=name) for name, ok in blocks.items() if not ok]
    return _Criterion(Fraction(sum(blocks.values()), len(blocks)), issues)


def _length_share(length: int) -> Fraction:
    if length < _LENGTH_SHORT:
        return _ZERO
    if length < _LENGTH_OK_MIN:
        return _LENGTH_PARTIAL
    if length <= _LENGTH_OK_MAX:
        return _LENGTH_FULL
    if length <= _LENGTH_LONG_MAX:
        return _LENGTH_PARTIAL
    return _ZERO


def _experience_quality(positions: Sequence[ExperienceLike]) -> _Criterion:
    if not positions:
        return _Criterion(_ZERO, [_issue("no_experience")])
    issues: list[ScoreIssue] = []
    total = _ZERO
    for item in positions:
        length = _text_length(item.description)
        has_desc = _filled(item.description)
        has_ach = _filled(item.achievements)
        total += (
            (_DESC_PRESENT if has_desc else _ZERO)
            + _length_share(length)
            + (_ACH_PRESENT if has_ach else _ZERO)
        )
        context = _position_context(item)
        if not has_desc:
            issues.append(_issue("no_description", **context))
        elif length < _LENGTH_OK_MIN:
            issues.append(_issue("description_too_short", **context, length=length))
        elif length > _LENGTH_OK_MAX:
            issues.append(_issue("description_too_long", **context, length=length))
        if not has_ach:
            issues.append(_issue("no_achievements", **context))
    return _Criterion(total / len(positions), issues)


def has_metric(text: str) -> bool:
    """Есть ли в тексте измеримый результат (процент, кратность, масштаб, число)."""
    return METRIC_RE.search(text) is not None


def _measurable(positions: Sequence[ExperienceLike]) -> _Criterion:
    if not positions:
        return _Criterion(_ZERO, [_issue("no_experience")])
    issues: list[ScoreIssue] = []
    with_metric = 0
    for item in positions:
        text = f"{item.description or ''}\n{item.achievements or ''}"
        if has_metric(text):
            with_metric += 1
        else:
            issues.append(_issue("no_metrics", **_position_context(item)))
    return _Criterion(Fraction(with_metric, len(positions)), issues)


def _count_ratio(count: int) -> Fraction:
    if count == 0:
        return _ZERO
    if count < _SKILLS_OPTIMUM_MIN:
        return Fraction(count, _SKILLS_OPTIMUM_MIN)
    if count <= _SKILLS_OPTIMUM_MAX:
        return _ONE
    return _HALF


def _skills_relevance(resume: ResumeSnapshot, market: MarketSkills) -> _Criterion:
    skills = set(resume.skills)
    count = len(skills)
    count_ratio = _count_ratio(count)
    issues: list[ScoreIssue] = []
    if count < _SKILLS_OPTIMUM_MIN:
        issues.append(_issue("too_few_skills", count=count))
    elif count > _SKILLS_OPTIMUM_MAX:
        issues.append(_issue("too_many_skills", count=count))

    # TODO: пустой рынок — критерий навыков только по количеству.
    if market.basis == "none" or not market.top_skills:
        return _Criterion(count_ratio, issues)

    matched = sum(1 for skill in market.top_skills if skill in skills)
    target = min(_MARKET_TARGET, len(market.top_skills))
    market_ratio = min(_ONE, Fraction(matched, target))
    missing = [skill for skill in market.top_skills if skill not in skills]
    if missing:
        issues.append(
            _issue(
                "missing_market_skills",
                skills=", ".join(missing[:_MISSING_MARKET_SHOWN]),
                basis=market.basis,
            )
        )
    return _Criterion(count_ratio / 2 + market_ratio / 2, issues)


def _chronology(resume: ResumeSnapshot, today: date) -> _Criterion:
    if not resume.experience:
        return _Criterion(_ZERO, [_issue("no_experience")])
    spans = position_spans(resume.experience, today)
    gaps = find_gaps(spans, today)
    issues = [
        ScoreIssue(
            code="gap",
            context={
                "from": gap.start.strftime("%Y-%m"),
                "to": gap.end.strftime("%Y-%m"),
                "months": gap.months,
                "trailing": gap.trailing,
            },
        )
        for gap in gaps
    ]
    missing_end = [
        item
        for item in _ordered_positions(resume.experience)
        if item.end_date is None and not item.is_current
    ]
    issues.extend(_issue("missing_end_date", **_position_context(item)) for item in missing_end)
    gaps_ratio = _ONE if not gaps else _HALF if len(gaps) == 1 else _ZERO
    consistency = _ZERO if missing_end else _ONE
    return _Criterion(_GAPS_WEIGHT * gaps_ratio + _CONSISTENCY_WEIGHT * consistency, issues)


def _education_courses(resume: ResumeSnapshot) -> _Criterion:
    issues: list[ScoreIssue] = []
    ratio = _ZERO
    if resume.education_count > 0:
        ratio += _EDUCATION_WEIGHT
    else:
        issues.append(_issue("missing_education"))
    if resume.course_count > 0:
        ratio += _COURSES_WEIGHT
    else:
        issues.append(_issue("missing_courses"))
    return _Criterion(ratio, issues)


def _languages(resume: ResumeSnapshot) -> _Criterion:
    if resume.language_levels:
        return _Criterion(_ONE, [])
    return _Criterion(_ZERO, [_issue("missing_languages")])


def _goals(resume: ResumeSnapshot) -> _Criterion:
    # TODO: зарплата в цели заполнена только вместе с валютой;
    # `desired_work_format=unknown` — заполнено.
    goals = {
        "target_position": _filled(resume.target_position),
        "salary": resume.desired_salary_min is not None
        and resume.desired_salary_currency is not None,
        "location": _filled(resume.desired_city) or _filled(resume.desired_country),
        "work_format": resume.desired_work_format is not None,
    }
    issues = [_issue("missing_goal", field=name) for name, ok in goals.items() if not ok]
    return _Criterion(Fraction(sum(goals.values()), len(goals)), issues)


# --- Рекомендации ---

_BLOCK_NAMES: Final = MappingProxyType(
    {
        "experience": "опыт работы",
        "education": "образование",
        "skills": "навыки",
        "summary": "раздел «О себе»",
        "contacts": "контакты",
    }
)
_GOAL_NAMES: Final = MappingProxyType(
    {
        "target_position": "желаемую должность",
        "salary": "желаемую зарплату с валютой",
        "location": "город или страну",
        "work_format": "формат работы",
    }
)


def _with_rest(names: Sequence[str]) -> str:
    """До двух названий и суффикс «и ещё N»."""
    shown = ", ".join(names[:_NAMED_POSITIONS])
    rest = len(names) - _NAMED_POSITIONS
    return f"{shown} и ещё {rest}" if rest > 0 else shown


def _positions(issues: Sequence[ScoreIssue], codes: frozenset[str]) -> list[str]:
    """«Позиция» в компании X — без повторов, в порядке `issues`."""
    result: list[str] = []
    for issue in issues:
        if issue.code not in codes:
            continue
        label = f"«{issue.context['position']}» в компании {issue.context['company']}"
        if label not in result:
            result.append(label)
    return result


def _codes(issues: Sequence[ScoreIssue]) -> set[str]:
    return {issue.code for issue in issues}


def _render_completeness(issues: Sequence[ScoreIssue]) -> str | None:
    missing = [_BLOCK_NAMES[str(i.context["block"])] for i in issues if i.code == "missing_block"]
    if not missing:
        return None
    return f"Заполните недостающие разделы резюме: {', '.join(missing)}"


def _render_experience_quality(issues: Sequence[ScoreIssue]) -> str | None:
    if "no_experience" in _codes(issues):
        return "Добавьте опыт работы: компанию, должность, период, обязанности и достижения"
    positions = _positions(
        issues,
        frozenset(
            {"no_description", "description_too_short", "description_too_long", "no_achievements"}
        ),
    )
    if not positions:
        return None
    word = "позиции" if len(positions) == 1 else "позиций"
    return (
        f"Улучшите описание {word} {_with_rest(positions)} — опишите задачи, стек и "
        f"зону ответственности (200–1500 символов) и отдельно перечислите достижения"
    )


def _render_measurable(issues: Sequence[ScoreIssue]) -> str | None:
    if "no_experience" in _codes(issues):
        return "Добавьте опыт работы с измеримыми результатами: проценты, сроки, масштаб"
    positions = _positions(issues, frozenset({"no_metrics"}))
    if not positions:
        return None
    word = "позиции" if len(positions) == 1 else "позиций"
    return (
        f"Добавьте измеримые результаты в описание {word} {_with_rest(positions)} — например, "
        f"на сколько % выросла метрика или во сколько раз ускорился процесс"
    )


def _render_skills(issues: Sequence[ScoreIssue]) -> str | None:
    parts: list[str] = []
    for issue in issues:
        if issue.code == "missing_market_skills":
            scope = "по вашей позиции" if issue.context["basis"] == "target_position" else "рынка"
            parts.append(f"Добавьте навыки, частые в вакансиях {scope}: {issue.context['skills']}")
        elif issue.code == "too_few_skills":
            parts.append(
                f"Укажите больше ключевых навыков: сейчас {issue.context['count']}, "
                f"оптимально {_SKILLS_OPTIMUM_MIN}–{_SKILLS_OPTIMUM_MAX}"
            )
        elif issue.code == "too_many_skills":
            parts.append(
                f"Сократите список навыков до {_SKILLS_OPTIMUM_MIN}–{_SKILLS_OPTIMUM_MAX} "
                f"самых важных: сейчас {issue.context['count']}"
            )
    return "; ".join(parts) or None


def _render_chronology(issues: Sequence[ScoreIssue]) -> str | None:
    if "no_experience" in _codes(issues):
        return "Добавьте опыт работы с датами начала и окончания"
    parts: list[str] = []
    gaps = [
        f"с {i.context['from']} по {i.context['to']} ({i.context['months']} мес.)"
        for i in issues
        if i.code == "gap"
    ]
    if gaps:
        word = "пробел" if len(gaps) == 1 else "пробелы"
        parts.append(
            f"Заполните {word} {_with_rest(gaps)} — укажите, чем занимались: "
            f"курсы, фриланс, пет-проекты"
        )
    missing_end = _positions(issues, frozenset({"missing_end_date"}))
    if missing_end:
        word = "позиции" if len(missing_end) == 1 else "позиций"
        parts.append(
            f"Укажите дату окончания {word} {_with_rest(missing_end)} "
            f"или отметьте её как текущую работу"
        )
    return "; ".join(parts) or None


def _render_education(issues: Sequence[ScoreIssue]) -> str | None:
    codes = _codes(issues)
    if {"missing_education", "missing_courses"} <= codes:
        return "Добавьте образование и пройденные курсы или сертификаты по профилю"
    if "missing_education" in codes:
        return "Добавьте образование: учебное заведение, специальность и годы обучения"
    if "missing_courses" in codes:
        return "Добавьте пройденные курсы или сертификаты по профилю"
    return None


def _render_languages(issues: Sequence[ScoreIssue]) -> str | None:
    if "missing_languages" in _codes(issues):
        return "Укажите языки, которыми владеете, с уровнем — например, English B2"
    return None


def _render_goals(issues: Sequence[ScoreIssue]) -> str | None:
    missing = [_GOAL_NAMES[str(i.context["field"])] for i in issues if i.code == "missing_goal"]
    if not missing:
        return None
    return f"Уточните цели поиска: укажите {', '.join(missing)}"


_RENDERERS: Final[Mapping[ScoreCriterionKey, Callable[[Sequence[ScoreIssue]], str | None]]] = (
    MappingProxyType(
        {
            Key.COMPLETENESS: _render_completeness,
            Key.EXPERIENCE_QUALITY: _render_experience_quality,
            Key.MEASURABLE_ACHIEVEMENTS: _render_measurable,
            Key.SKILLS_RELEVANCE: _render_skills,
            Key.CHRONOLOGY: _render_chronology,
            Key.EDUCATION_COURSES: _render_education,
            Key.LANGUAGES: _render_languages,
            Key.GOALS_SPECIFICITY: _render_goals,
        }
    )
)


def render_recommendation(key: ScoreCriterionKey, issues: Sequence[ScoreIssue]) -> str | None:
    """Одна строка рекомендации по проблемам критерия (русский шаблон)."""
    # TODO: рекомендации — русские шаблоны по `issues`; на этапе 10 формулировку
    # делает LLM-адаптер по тем же `issues`, шаблон остаётся запасным. Числа
    # LLM не трогает.
    return _RENDERERS[key](issues)


# --- Итог ---


def score_resume(resume: ResumeSnapshot, market: MarketSkills, today: date) -> ScoreResult:
    """Оценка 0–10 по 8 критериям; рекомендации — у критериев с долей < 0.7."""
    positions = _ordered_positions(resume.experience)
    computed: dict[ScoreCriterionKey, _Criterion] = {
        Key.COMPLETENESS: _completeness(resume),
        Key.EXPERIENCE_QUALITY: _experience_quality(positions),
        Key.MEASURABLE_ACHIEVEMENTS: _measurable(positions),
        Key.SKILLS_RELEVANCE: _skills_relevance(resume, market),
        Key.CHRONOLOGY: _chronology(resume, today),
        Key.EDUCATION_COURSES: _education_courses(resume),
        Key.LANGUAGES: _languages(resume),
        Key.GOALS_SPECIFICITY: _goals(resume),
    }

    criteria: list[ScoreCriterionDetail] = []
    total = Decimal(0)
    losses: list[tuple[Decimal, int, str]] = []
    for index, key in enumerate(ScoreCriterionKey):
        item = computed[key]
        weight = CRITERIA_WEIGHTS[key]
        points = q2(weight * item.ratio)
        total += points
        recommendation = (
            render_recommendation(key, item.issues)
            if item.ratio < RECOMMENDATION_THRESHOLD
            else None
        )
        if recommendation is not None:
            losses.append((q2(weight) - points, index, recommendation))
        criteria.append(
            ScoreCriterionDetail(
                key=key,
                name=CRITERIA_NAMES[key],
                weight=float(weight),
                points=float(points),
                issues=item.issues,
                recommendation=recommendation,
            )
        )

    losses.sort(key=lambda loss: (-loss[0], loss[1]))
    return ScoreResult(
        score=float(total),
        criteria=criteria,
        recommendations=[text for _, _, text in losses],
        market=market,
    )
