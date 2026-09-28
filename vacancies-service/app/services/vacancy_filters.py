"""SQL-условия и сортировка ленты вакансий (п. 5.5 ТЗ). Чистый модуль без БД.

Условия разных фильтров объединяются через AND, значения внутри одного
списка — через OR; параметр `None` означает, что фильтр не применяется.
"""

# TODO: отклонение от п. 5.5 и п. 6 ТЗ по решению пользователя — фильтра по
# навыкам (`skills[]`) нет: навыки пользователя учитываются матчингом этапа 6.

from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Float, and_, exists, func, literal_column, or_

from app.db.models import UserVacancyAction, Vacancy, VacancyPosting
from app.enums import SalaryPeriod, UserAction
from app.schemas.common import VacancySort
from app.schemas.vacancies import VacancyListQuery
from app.services.normalizer import canonicalize_city
from app.utils.text import collapse_spaces

# Те же словари, что в генерируемой колонке `vacancies.search_vector`.
_TS_CONFIGS = ("russian", "english")


def normalize_query_text(q: str | None) -> str | None:
    """Пустой после `strip` поисковый запрос равнозначен его отсутствию."""
    if q is None:
        return None
    stripped = q.strip()
    return stripped or None


def build_tsquery(text: str) -> ColumnElement[Any]:
    """`websearch_to_tsquery('russian', :q) || websearch_to_tsquery('english', :q)`.

    `websearch_to_tsquery` не падает на синтаксисе пользовательского ввода.
    """
    # TODO: запрос из одних стоп-слов даёт пустой tsquery и пустую выдачу.
    ru, en = (
        func.websearch_to_tsquery(literal_column(f"'{config}'::regconfig"), text)
        for config in _TS_CONFIGS
    )
    return ru.op("||")(en)


def rank_expression(tsquery: ColumnElement[Any]) -> ColumnElement[float]:
    """Веса по умолчанию ставят совпадение в заголовке (`A`) выше тела (`B`)."""
    return func.ts_rank(Vacancy.search_vector, tsquery, type_=Float)


def _user_action_exists(user_id: UUID, action: UserAction) -> ColumnElement[bool]:
    return exists().where(
        UserVacancyAction.vacancy_id == Vacancy.id,
        UserVacancyAction.user_id == user_id,
        UserVacancyAction.action == action,
    )


def build_conditions(
    query: VacancyListQuery,
    user_id: UUID,
    tsquery: ColumnElement[Any] | None,
) -> list[ColumnElement[bool]]:
    """Список условий WHERE; первое всегда `is_active`."""
    conditions: list[ColumnElement[bool]] = [Vacancy.is_active.is_(True)]

    if tsquery is not None:
        conditions.append(Vacancy.search_vector.op("@@")(tsquery))
    if query.experience_level:
        conditions.append(Vacancy.experience_level.in_(query.experience_level))
    if query.employment_type:
        conditions.append(Vacancy.employment_type.in_(query.employment_type))
    if query.work_format:
        conditions.append(Vacancy.work_format.in_(query.work_format))

    # TODO: `country` сравнивается по `lower()`, `city` — через словарь
    # `canonicalize_city` + `lower()`; составной индекс (country, city) при
    # этом не используется.
    if query.country:
        country = collapse_spaces(query.country)
        conditions.append(func.lower(Vacancy.country) == func.lower(country))
    if query.city:
        canon, _ = canonicalize_city(query.city)
        if canon is not None:
            conditions.append(func.lower(Vacancy.city) == func.lower(canon))

    # TODO: `salary_min` и `salary_currency` независимы (решение пользователя):
    # сумма фильтрует по всем валютам, включая NULL; заданная валюта отсекает
    # NULL. Детектор валюты по стране или компании — позже.
    # TODO: сумма сравнивается с верхом вилки `COALESCE(salary_max, salary_min)`
    # только для `period='month'`; годовые и почасовые вилки не участвуют.
    if query.salary_min is not None:
        conditions.append(
            and_(
                Vacancy.salary_period == SalaryPeriod.MONTH,
                func.coalesce(Vacancy.salary_max, Vacancy.salary_min) >= query.salary_min,
            )
        )
    if query.salary_currency is not None:
        conditions.append(Vacancy.salary_currency == query.salary_currency)
    if query.has_salary is True:
        conditions.append(or_(Vacancy.salary_min.is_not(None), Vacancy.salary_max.is_not(None)))
    elif query.has_salary is False:
        conditions.append(and_(Vacancy.salary_min.is_(None), Vacancy.salary_max.is_(None)))

    if query.source:
        conditions.append(
            exists().where(
                VacancyPosting.vacancy_id == Vacancy.id,
                VacancyPosting.source.in_(query.source),
            )
        )

    # TODO: `published_after` сравнивается с `published_at` канона (самая
    # ранняя публикация); вакансии без даты исключаются.
    if query.published_after is not None:
        conditions.append(Vacancy.published_at >= query.published_after)

    # TODO: `relocation_support=false` означает `IS NOT TRUE` — нормализатор
    # даёт только `True` или `None`.
    if query.relocation_support is True:
        conditions.append(Vacancy.relocation_support.is_(True))
    elif query.relocation_support is False:
        conditions.append(Vacancy.relocation_support.is_not(True))

    if query.exclude_hidden:
        conditions.append(~_user_action_exists(user_id, UserAction.HIDDEN))
    if query.saved_only:
        conditions.append(_user_action_exists(user_id, UserAction.SAVED))

    return conditions


def build_order_by(
    sort: VacancySort, rank: ColumnElement[float] | None
) -> list[ColumnElement[Any]]:
    """Ключи сортировки; последний всегда `id` — детерминированный разрыв ничьих."""
    fresh_first = Vacancy.published_at.desc().nulls_last()
    tiebreak = Vacancy.id.asc()
    if sort == VacancySort.RELEVANCE and rank is not None:
        return [rank.desc(), fresh_first, tiebreak]
    if sort == VacancySort.SALARY:
        # TODO: без фильтра валюты числа разных валют сравниваются как есть.
        salary = func.coalesce(Vacancy.salary_max, Vacancy.salary_min)
        return [salary.desc().nulls_last(), fresh_first, tiebreak]
    return [fresh_first, tiebreak]
