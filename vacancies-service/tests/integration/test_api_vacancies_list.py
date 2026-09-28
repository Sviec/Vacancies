"""Лента вакансий: фильтры, поиск, сортировка, пагинация (этап 5, живой PostgreSQL)."""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UserVacancyAction, Vacancy
from app.enums import EmploymentType, ExperienceLevel, SalaryPeriod, UserAction, WorkFormat
from factories import ingest_raws, make_raw

pytestmark = pytest.mark.integration

URL = "/api/v1/vacancies"


def _at(month: int, day: int, hour: int = 10) -> datetime:
    return datetime(2026, month, day, hour, tzinfo=UTC)


def _raw(
    key: str,
    title: str,
    *,
    source: str,
    city: str | None,
    level: ExperienceLevel,
    fmt: WorkFormat,
    published_at: datetime | None,
    employment: EmploymentType = EmploymentType.FULL_TIME,
    description: str | None = None,
    **extra: Any,
) -> Any:
    return make_raw(
        external_id=key,
        source=source,
        url=f"https://t.me/{source}/{key}",
        title=title,
        company=f"Компания {key}",
        city=city,
        description_raw=description or f"Описание вакансии компании {key}. Команда ждёт вас.",
        experience_level=level,
        work_format=fmt,
        employment_type=employment,
        published_at=published_at,
        **extra,
    )


def _month(low: int | None, high: int | None, currency: str | None) -> dict[str, Any]:
    return {
        "salary_min": low,
        "salary_max": high,
        "salary_currency": currency,
        "salary_period": SalaryPeriod.MONTH,
    }


@pytest.fixture
async def seeded(db_session: AsyncSession) -> dict[str, str]:
    """Восемь вакансий; `v7` склеена из двух каналов (tg_a и tg_d)."""
    raws = [
        _raw(
            "v1",
            "Python разработчик",
            source="tg_a",
            city="Москва",
            level=ExperienceLevel.MIDDLE,
            fmt=WorkFormat.REMOTE,
            published_at=_at(9, 10),
            **_month(200_000, 300_000, "RUB"),
        ),
        _raw(
            "v2",
            "Java Developer",
            source="tg_b",
            city="Берлин",
            level=ExperienceLevel.SENIOR,
            fmt=WorkFormat.HYBRID,
            published_at=_at(9, 5),
            relocation_support=True,
            **_month(3_000, 5_000, "USD"),
        ),
        _raw(
            "v3",
            "Data Scientist",
            source="tg_c",
            city="Москва",
            level=ExperienceLevel.JUNIOR,
            fmt=WorkFormat.OFFICE,
            published_at=_at(8, 20),
            **_month(None, 150_000, None),
        ),
        _raw(
            "v4",
            "Frontend-разработчик React",
            source="tg_a",
            city="Казань",
            level=ExperienceLevel.MIDDLE,
            fmt=WorkFormat.REMOTE,
            published_at=_at(8, 1),
            salary_min=2_400_000,
            salary_max=3_600_000,
            salary_currency="RUB",
            salary_period=SalaryPeriod.YEAR,
        ),
        _raw(
            "v5",
            "QA Engineer",
            source="tg_b",
            city="Минск",
            level=ExperienceLevel.JUNIOR,
            fmt=WorkFormat.OFFICE,
            published_at=None,
            employment=EmploymentType.PART_TIME,
        ),
        _raw(
            "v6",
            "DevOps Engineer",
            source="tg_c",
            city=None,
            level=ExperienceLevel.SENIOR,
            fmt=WorkFormat.REMOTE,
            published_at=_at(9, 12),
            employment=EmploymentType.CONTRACT,
            salary_min=50,
            salary_max=70,
            salary_currency="EUR",
            salary_period=SalaryPeriod.HOUR,
        ),
        _raw(
            "v7",
            "Go developer",
            source="tg_a",
            city="Москва",
            level=ExperienceLevel.SENIOR,
            fmt=WorkFormat.OFFICE,
            published_at=_at(9, 1),
            **_month(250_000, 350_000, "RUB"),
        ),
        _raw(
            "v7",
            "Go developer",
            source="tg_d",
            city="Москва",
            level=ExperienceLevel.SENIOR,
            fmt=WorkFormat.OFFICE,
            published_at=_at(9, 3),
            description="Перепост: команда Go ищет сильного инженера.",
            **_month(250_000, 350_000, "RUB"),
        ),
        _raw(
            "v8",
            "Аналитик данных",
            source="tg_d",
            city="Москва",
            level=ExperienceLevel.MIDDLE,
            fmt=WorkFormat.OFFICE,
            published_at=_at(9, 2),
            description="Нужен аналитик, раньше работавший как python разработчик.",
        ),
    ]
    ids = await ingest_raws(db_session, *raws)
    names = ["v1", "v2", "v3", "v4", "v5", "v6", "v7", "v7", "v8"]
    mapping = {name: str(vacancy_id) for name, vacancy_id in zip(names, ids, strict=True)}
    assert len(set(mapping.values())) == 8
    return mapping


async def _page(client: AsyncClient, **params: Any) -> dict[str, Any]:
    response = await client.get(URL, params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def _names(client: AsyncClient, seeded: dict[str, str], **params: Any) -> list[str]:
    by_id = {vacancy_id: name for name, vacancy_id in seeded.items()}
    return [by_id[item["id"]] for item in (await _page(client, **params))["items"]]


async def _set(client: AsyncClient, seeded: dict[str, str], **params: Any) -> set[str]:
    return set(await _names(client, seeded, **params))


DATE_ORDER = ["v6", "v1", "v2", "v8", "v7", "v3", "v4", "v5"]


async def test_no_filters_returns_all_by_date(
    api_client: AsyncClient, seeded: dict[str, str]
) -> None:
    body = await _page(api_client)
    assert body["total"] == 8
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert await _names(api_client, seeded) == DATE_ORDER
    assert await _names(api_client, seeded, sort="date") == DATE_ORDER
    card = body["items"][0]
    assert card["user_actions"] == []
    assert "description_clean" not in card


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"experience_level": "junior"}, {"v3", "v5"}),
        ({"experience_level": ["junior", "senior"]}, {"v2", "v3", "v5", "v6", "v7"}),
        ({"employment_type": "part_time"}, {"v5"}),
        ({"employment_type": ["contract", "part_time"]}, {"v5", "v6"}),
        ({"work_format": "remote"}, {"v1", "v4", "v6"}),
        ({"work_format": "hybrid"}, {"v2"}),
        ({"country": "германия"}, {"v2"}),
        ({"country": "  РОССИЯ "}, {"v1", "v3", "v4", "v7", "v8"}),
        ({"city": "мск"}, {"v1", "v3", "v7", "v8"}),
        ({"city": "москва"}, {"v1", "v3", "v7", "v8"}),
        ({"city": "KAZAN"}, {"v4"}),
        ({"has_salary": "true"}, {"v1", "v2", "v3", "v4", "v6", "v7"}),
        ({"has_salary": "false"}, {"v5", "v8"}),
        ({"relocation_support": "true"}, {"v2"}),
        ({"relocation_support": "false"}, {"v1", "v3", "v4", "v5", "v6", "v7", "v8"}),
        ({"source": "tg_d"}, {"v7", "v8"}),
        ({"source": "tg_a"}, {"v1", "v4", "v7"}),
        ({"source": ["tg_b", "tg_c"]}, {"v2", "v3", "v5", "v6"}),
        ({"published_after": "2026-09-05"}, {"v1", "v2", "v6"}),
        # 14:00 MSK = 11:00 UTC — позже v2 (10:00 UTC).
        ({"published_after": "2026-09-05T14:00:00+03:00"}, {"v1", "v6"}),
        ({"published_after": "2026-09-05T12:00:00+03:00"}, {"v1", "v2", "v6"}),
    ],
)
async def test_single_filters(
    api_client: AsyncClient,
    seeded: dict[str, str],
    params: dict[str, Any],
    expected: set[str],
) -> None:
    assert await _set(api_client, seeded, **params) == expected
    assert (await _page(api_client, **params))["total"] == len(expected)


# --- зарплата ---


async def test_salary_min_without_currency_matches_any_currency(
    api_client: AsyncClient, seeded: dict[str, str]
) -> None:
    # RUB (v1, v7), USD (v2) и NULL-валюта (v3); год (v4) и час (v6) отсечены.
    assert await _set(api_client, seeded, salary_min=3_000) == {"v1", "v2", "v3", "v7"}


async def test_salary_min_with_currency_drops_other_and_null(
    api_client: AsyncClient, seeded: dict[str, str]
) -> None:
    assert await _set(api_client, seeded, salary_min=3_000, salary_currency="RUB") == {
        "v1",
        "v7",
    }


async def test_currency_without_amount(api_client: AsyncClient, seeded: dict[str, str]) -> None:
    assert await _set(api_client, seeded, salary_currency="USD") == {"v2"}
    # Без суммы период не проверяется: почасовая EUR-вилка проходит.
    assert await _set(api_client, seeded, salary_currency="EUR") == {"v6"}


async def test_salary_uses_upper_bound(api_client: AsyncClient, seeded: dict[str, str]) -> None:
    # «до 150000» (v3) покрывает запрос 120000; USD 5000 — нет.
    assert await _set(api_client, seeded, salary_min=120_000) == {"v1", "v3", "v7"}


async def test_year_and_hour_excluded_by_amount(
    api_client: AsyncClient, seeded: dict[str, str]
) -> None:
    names = await _set(api_client, seeded, salary_min=1)
    assert "v4" not in names
    assert "v6" not in names


# --- комбинации ---


async def test_combination_format_salary_currency(
    api_client: AsyncClient, seeded: dict[str, str]
) -> None:
    params = {"work_format": "remote", "salary_min": 100_000, "salary_currency": "RUB"}
    assert await _set(api_client, seeded, **params) == {"v1"}


async def test_combination_query_source_date(
    api_client: AsyncClient, seeded: dict[str, str]
) -> None:
    params = {"q": "developer", "source": "tg_d", "published_after": "2026-08-15"}
    assert await _set(api_client, seeded, **params) == {"v7"}


async def test_combination_city_level_format(
    api_client: AsyncClient, seeded: dict[str, str]
) -> None:
    params = {"city": "Москва", "experience_level": ["middle", "senior"], "work_format": "office"}
    assert await _set(api_client, seeded, **params) == {"v7", "v8"}


# --- полнотекстовый поиск ---


async def test_query_russian_morphology(api_client: AsyncClient, seeded: dict[str, str]) -> None:
    assert await _set(api_client, seeded, q="разработчика") == {"v1", "v4", "v8"}


async def test_query_english_morphology(api_client: AsyncClient, seeded: dict[str, str]) -> None:
    assert await _set(api_client, seeded, q="developers") == {"v2", "v7"}


async def test_title_match_ranks_above_body(
    api_client: AsyncClient, seeded: dict[str, str]
) -> None:
    names = await _names(api_client, seeded, q="разработчик")
    assert set(names[:2]) == {"v1", "v4"}
    assert names[-1] == "v8"


async def test_query_syntax_does_not_fail(api_client: AsyncClient, seeded: dict[str, str]) -> None:
    body = await _page(api_client, q='"python & | ! (')
    assert body["total"] >= 0


async def test_blank_query_is_ignored(api_client: AsyncClient, seeded: dict[str, str]) -> None:
    assert await _names(api_client, seeded, q="   ") == DATE_ORDER


# --- сортировка и пагинация ---


async def test_sort_salary(api_client: AsyncClient, seeded: dict[str, str]) -> None:
    assert await _names(api_client, seeded, sort="salary") == [
        "v4",
        "v7",
        "v1",
        "v3",
        "v2",
        "v6",
        "v8",
        "v5",
    ]


async def test_equal_keys_break_ties_by_id(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    same = _at(9, 15)
    raws = [
        _raw(
            f"t{i}",
            f"Тестировщик {i}",
            source="tg_t",
            city="Москва",
            level=ExperienceLevel.MIDDLE,
            fmt=WorkFormat.OFFICE,
            published_at=same,
        )
        for i in range(4)
    ]
    ids = sorted(str(vacancy_id) for vacancy_id in await ingest_raws(db_session, *raws))
    first = [item["id"] for item in (await _page(api_client, sort="date"))["items"]]
    second = [item["id"] for item in (await _page(api_client, sort="date"))["items"]]
    assert first == second == ids


async def test_pagination(api_client: AsyncClient, seeded: dict[str, str]) -> None:
    pages = [await _names(api_client, seeded, page=n, page_size=3) for n in (1, 2, 3)]
    assert pages == [DATE_ORDER[0:3], DATE_ORDER[3:6], DATE_ORDER[6:8]]
    beyond = await _page(api_client, page=4, page_size=3)
    assert beyond["items"] == []
    assert beyond["total"] == 8


# --- действия пользователя и активность ---


async def test_hidden_excluded_by_default(
    api_client: AsyncClient, seeded: dict[str, str], db_session: AsyncSession
) -> None:
    response = await api_client.post(f"{URL}/{seeded['v1']}/action", json={"action": "hidden"})
    assert response.status_code == 200
    # Скрытие другим пользователем на выдачу текущего не влияет.
    db_session.add(
        UserVacancyAction(
            user_id=uuid.uuid4(), vacancy_id=uuid.UUID(seeded["v2"]), action=UserAction.HIDDEN
        )
    )
    await db_session.flush()

    names = await _set(api_client, seeded)
    assert "v1" not in names
    assert "v2" in names
    with_hidden = await _page(api_client, exclude_hidden="false")
    assert with_hidden["total"] == 8
    card = next(i for i in with_hidden["items"] if i["id"] == seeded["v1"])
    assert card["user_actions"] == ["hidden"]


async def test_saved_only(api_client: AsyncClient, seeded: dict[str, str]) -> None:
    for name in ("v3", "v6"):
        response = await api_client.post(f"{URL}/{seeded[name]}/action", json={"action": "saved"})
        assert response.status_code == 200
    assert await _set(api_client, seeded, saved_only="true") == {"v3", "v6"}


async def test_inactive_vacancy_not_in_feed(
    api_client: AsyncClient, seeded: dict[str, str], db_session: AsyncSession
) -> None:
    await db_session.execute(
        update(Vacancy).where(Vacancy.id == uuid.UUID(seeded["v1"])).values(is_active=False)
    )
    await db_session.flush()
    body = await _page(api_client)
    assert body["total"] == 7
    assert seeded["v1"] not in {item["id"] for item in body["items"]}


# --- 422 ---


@pytest.mark.parametrize(
    "params",
    [
        {"skills": "python"},
        {"page_size": 101},
        {"page": 0},
        {"work_format": "space"},
        {"sort": "popularity"},
        {"unknown": "1"},
        {"salary_currency": "rub"},
        {"salary_min": -1},
    ],
)
async def test_invalid_query_is_422(api_client: AsyncClient, params: dict[str, Any]) -> None:
    response = await api_client.get(URL, params=params)
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert isinstance(error["details"], dict)


async def test_empty_database_feed(api_client: AsyncClient) -> None:
    body = await _page(api_client, q="python", salary_min=1)
    assert body == {"items": [], "total": 0, "page": 1, "page_size": 20}
