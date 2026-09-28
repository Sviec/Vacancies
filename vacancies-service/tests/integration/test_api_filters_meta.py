"""GET /vacancies/filters/meta (этап 5, живой PostgreSQL)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Vacancy
from app.enums import SalaryPeriod
from factories import ingest_raws, make_raw

pytestmark = pytest.mark.integration

URL = "/api/v1/vacancies/filters/meta"


async def test_empty_database(api_client: AsyncClient) -> None:
    response = await api_client.get(URL)
    assert response.status_code == 200
    assert response.json() == {"countries": [], "cities": [], "sources": [], "currencies": []}


async def test_distinct_sorted_values_of_active_vacancies(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    month = {"salary_period": SalaryPeriod.MONTH, "salary_min": 100}
    ids = await ingest_raws(
        db_session,
        make_raw(
            external_id="1",
            source="tg_b",
            company="A",
            city="Москва",
            **month,
            salary_currency="RUB",
        ),
        # Склейка с первой: второй канал оффера `A`.
        make_raw(
            external_id="2",
            source="tg_a",
            company="A",
            city="Москва",
            **month,
            salary_currency="RUB",
        ),
        make_raw(
            external_id="3",
            source="tg_c",
            company="B",
            city="Берлин",
            **month,
            salary_currency="USD",
        ),
        make_raw(
            external_id="4",
            source="tg_c",
            company="C",
            city="Казань",
            **month,
            salary_currency="RUB",
        ),
        make_raw(external_id="5", source="tg_c", company="D", city=None),
        # Неактивная: её страна, город, валюта и источник в мета не попадают.
        make_raw(
            external_id="6",
            source="tg_zz",
            company="E",
            city="Минск",
            **month,
            salary_currency="EUR",
        ),
    )
    assert ids[0] == ids[1]
    await db_session.execute(update(Vacancy).where(Vacancy.id == ids[5]).values(is_active=False))
    await db_session.flush()

    body = (await api_client.get(URL)).json()
    assert body == {
        "countries": sorted(["Германия", "Россия"]),
        "cities": sorted(["Берлин", "Казань", "Москва"]),
        "sources": ["tg_a", "tg_b", "tg_c"],
        "currencies": ["RUB", "USD"],
    }
    assert "top_skills" not in body
