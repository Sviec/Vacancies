"""Сборка SQL-условий и сортировки ленты вакансий (офлайн, только компиляция)."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import ColumnElement
from sqlalchemy.dialects import postgresql

from app.enums import EmploymentType, ExperienceLevel, WorkFormat
from app.schemas.common import VacancySort
from app.schemas.vacancies import VacancyListQuery
from app.services.vacancy_filters import (
    build_conditions,
    build_order_by,
    build_tsquery,
    normalize_query_text,
    rank_expression,
)

USER_ID = uuid4()


def _sql(clause: ColumnElement[Any], *, literal: bool = True) -> str:
    compiled = clause.compile(
        dialect=postgresql.dialect(),  # type: ignore[no-untyped-call]
        compile_kwargs={"literal_binds": literal},
    )
    return str(compiled)


def _extra(query: VacancyListQuery) -> list[str]:
    """SQL условий сверх базовых (`is_active` и `NOT EXISTS hidden`)."""
    base = VacancyListQuery(exclude_hidden=False)
    tsq = build_tsquery(query.q) if query.q else None
    conditions = build_conditions(query.model_copy(update={"exclude_hidden": False}), USER_ID, tsq)
    assert len(build_conditions(base, USER_ID, None)) == 1
    return [_sql(c, literal=False) for c in conditions[1:]]


def test_empty_query_has_only_is_active() -> None:
    conditions = build_conditions(VacancyListQuery(exclude_hidden=False), USER_ID, None)
    assert len(conditions) == 1
    assert "is_active IS true" in _sql(conditions[0])


def test_default_query_excludes_hidden() -> None:
    conditions = build_conditions(VacancyListQuery(), USER_ID, None)
    assert len(conditions) == 2
    sql = _sql(conditions[1], literal=False)
    assert sql.startswith("NOT (EXISTS")
    assert "user_vacancy_actions" in sql


@pytest.mark.parametrize(
    ("params", "fragment"),
    [
        ({"experience_level": [ExperienceLevel.JUNIOR, ExperienceLevel.MIDDLE]}, " IN "),
        ({"employment_type": [EmploymentType.FULL_TIME]}, "employment_type IN"),
        ({"work_format": [WorkFormat.REMOTE]}, "work_format IN"),
        ({"country": "Россия"}, "lower(vacancies.country)"),
        ({"city": "Москва"}, "lower(vacancies.city)"),
        ({"salary_min": 100_000}, "coalesce(vacancies.salary_max, vacancies.salary_min)"),
        ({"salary_currency": "USD"}, "vacancies.salary_currency ="),
        ({"has_salary": True}, "IS NOT NULL OR"),
        ({"has_salary": False}, "IS NULL AND"),
        ({"source": ["tg_a", "tg_b"]}, "EXISTS (SELECT"),
        ({"published_after": datetime(2026, 9, 1, tzinfo=UTC)}, "published_at >="),
        ({"relocation_support": True}, "relocation_support IS true"),
        ({"relocation_support": False}, "relocation_support IS NOT true"),
        ({"saved_only": True}, "EXISTS (SELECT"),
        ({"q": "python"}, "@@"),
    ],
)
def test_each_filter_adds_one_condition(params: dict[str, Any], fragment: str) -> None:
    extra = _extra(VacancyListQuery.model_validate(params))
    assert len(extra) == 1
    assert fragment in extra[0]


def test_salary_min_without_currency_has_no_currency_condition() -> None:
    extra = _extra(VacancyListQuery(salary_min=100_000))
    assert len(extra) == 1
    assert "salary_currency" not in extra[0]
    assert "salary_period" in extra[0]


def test_currency_without_amount_has_no_coalesce() -> None:
    extra = _extra(VacancyListQuery(salary_currency="RUB"))
    assert len(extra) == 1
    assert "coalesce" not in extra[0]


def test_salary_and_currency_give_two_conditions() -> None:
    extra = _extra(VacancyListQuery(salary_min=100_000, salary_currency="RUB"))
    assert len(extra) == 2


def test_city_alias_is_canonicalized() -> None:
    query = VacancyListQuery(city="мск", exclude_hidden=False)
    condition = build_conditions(query, USER_ID, None)[1]
    assert "lower('Москва')" in _sql(condition)


def test_saved_only_and_exclude_hidden_combined() -> None:
    conditions = build_conditions(VacancyListQuery(saved_only=True), USER_ID, None)
    sqls = [_sql(c, literal=False) for c in conditions]
    assert len(conditions) == 3
    assert sqls[1].startswith("NOT (EXISTS")
    assert sqls[2].startswith("EXISTS")


def test_tsquery_uses_both_configs() -> None:
    sql = _sql(build_tsquery("разработчик"))
    assert "websearch_to_tsquery('russian'::regconfig" in sql
    assert "websearch_to_tsquery('english'::regconfig" in sql
    assert "||" in sql


def _order_sql(sort: VacancySort, *, with_rank: bool) -> list[str]:
    rank = rank_expression(build_tsquery("python")) if with_rank else None
    return [_sql(key, literal=False) for key in build_order_by(sort, rank)]


def test_order_relevance_with_query() -> None:
    keys = _order_sql(VacancySort.RELEVANCE, with_rank=True)
    assert keys[0].startswith("ts_rank(") and keys[0].endswith("DESC")
    assert keys[1] == "vacancies.published_at DESC NULLS LAST"
    assert keys[-1] == "vacancies.id ASC"


def test_order_relevance_without_query_equals_date() -> None:
    assert _order_sql(VacancySort.RELEVANCE, with_rank=False) == _order_sql(
        VacancySort.DATE, with_rank=False
    )
    assert _order_sql(VacancySort.DATE, with_rank=False) == [
        "vacancies.published_at DESC NULLS LAST",
        "vacancies.id ASC",
    ]


def test_order_match_falls_back_to_date() -> None:
    # Порядок по матчу строит сервис; в SQL `MATCH` — это сортировка по дате.
    for with_rank in (False, True):
        assert _order_sql(VacancySort.MATCH, with_rank=with_rank) == _order_sql(
            VacancySort.DATE, with_rank=False
        )


def test_order_salary() -> None:
    keys = _order_sql(VacancySort.SALARY, with_rank=False)
    assert keys == [
        "coalesce(vacancies.salary_max, vacancies.salary_min) DESC NULLS LAST",
        "vacancies.published_at DESC NULLS LAST",
        "vacancies.id ASC",
    ]


def test_normalize_query_text() -> None:
    assert normalize_query_text("  ") is None
    assert normalize_query_text(None) is None
    assert normalize_query_text("  python ") == "python"
