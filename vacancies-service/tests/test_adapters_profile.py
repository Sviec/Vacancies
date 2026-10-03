"""Офлайн-тесты profile-адаптера: фикстура и httpx.MockTransport."""

from datetime import date
from uuid import UUID

import httpx
import pytest

from app.adapters.profile import MockProfileAdapter, RealProfileAdapter
from app.config import Settings
from app.enums import LanguageLevel
from app.schemas.resumes import (
    ResumeContacts,
    ResumeEducationCreate,
    ResumeExperienceCreate,
    ResumeLanguageCreate,
    ResumeSkillCreate,
)
from app.utils.errors import ExternalServiceError

_USER_A = UUID("00000000-0000-0000-0000-000000000001")
_USER_B = UUID("11111111-1111-1111-1111-111111111111")


def _snapshot_payload() -> dict[str, object]:
    """Валидное тело profile-core плюс лишнее поле корня."""
    return {
        "unused": "ignore-me",
        "skills": [
            {"skill": "python", "level": 4},
            {"skill": "sql", "level": 3},
        ],
        "experience": [
            {
                "company": "Mock Lab",
                "position": "Data Scientist",
                "start_date": "2022-07-01",
                "end_date": None,
                "is_current": True,
                "description": "Анализ данных и автоматизация отчётности.",
                "achievements": "Сократил время отчёта на 30%.",
            }
        ],
        "education": [
            {
                "institution": "МГУ",
                "degree": "магистр",
                "field": "прикладная математика",
                "start_year": 2016,
                "end_year": 2018,
            }
        ],
        "languages": [{"language": "English", "level": "B2"}],
        "contacts": {"email": "demo@example.com", "telegram": "@demo"},
        "desired_country": "Россия",
        "desired_city": "Москва",
    }


async def test_mock_profile_is_deterministic() -> None:
    adapter = MockProfileAdapter()
    first = await adapter.get_profile(_USER_A)
    second = await adapter.get_profile(_USER_B)
    assert first == second
    assert first is not second
    assert first.skills == [
        ResumeSkillCreate(skill="python", level=4),
        ResumeSkillCreate(skill="sql", level=3),
    ]
    assert first.experience == [
        ResumeExperienceCreate(
            company="Mock Lab",
            position="Data Scientist",
            start_date=date(2022, 7, 1),
            end_date=None,
            is_current=True,
            description="Анализ данных и автоматизация отчётности.",
            achievements="Сократил время отчёта на 30%.",
        )
    ]
    assert first.education == [
        ResumeEducationCreate(
            institution="МГУ",
            degree="магистр",
            field="прикладная математика",
            start_year=2016,
            end_year=2018,
        )
    ]
    assert first.languages == [ResumeLanguageCreate(language="English", level=LanguageLevel.B2)]
    assert first.contacts == ResumeContacts(email="demo@example.com", telegram="@demo")
    assert first.desired_country == "Россия"
    assert first.desired_city == "Москва"
    first.skills.clear()
    again = await adapter.get_profile(_USER_A)
    assert len(again.skills) == 2


async def test_mock_profile_does_not_open_http(monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("HTTP client must not be created")

    monkeypatch.setattr(httpx.AsyncClient, "__init__", _forbidden)
    monkeypatch.setattr(httpx.Client, "__init__", _forbidden)
    snapshot = await MockProfileAdapter().get_profile(_USER_A)
    assert snapshot.desired_city == "Москва"


async def test_real_missing_url_raises_before_http() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    adapter = RealProfileAdapter(
        Settings(_env_file=None, profile_service_url=None),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ExternalServiceError) as exc_info:
        await adapter.get_profile(_USER_A)
    assert seen == []
    assert type(exc_info.value) is ExternalServiceError
    assert exc_info.value.message == "Profile service URL is not configured"
    assert exc_info.value.details == {"service": "profile", "reason": "missing_service_url"}


async def test_real_get_profile_parses_snapshot() -> None:
    seen: list[httpx.Request] = []
    payload = _snapshot_payload()

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=payload)

    base = "http://profile.test/v1/"
    adapter = RealProfileAdapter(
        Settings(_env_file=None, profile_mode="real", profile_service_url=base),
        transport=httpx.MockTransport(handler),
    )
    snapshot = await adapter.get_profile(_USER_A)
    expected = await MockProfileAdapter().get_profile(_USER_B)
    assert snapshot == expected
    assert len(seen) == 1
    request = seen[0]
    assert request.method == "GET"
    assert str(request.url) == f"http://profile.test/v1/users/{_USER_A}"
    assert request.headers["accept"] == "application/json"
    assert "authorization" not in request.headers


async def test_real_http_error() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(503, text="down")

    adapter = RealProfileAdapter(
        Settings(_env_file=None, profile_service_url="http://profile.test"),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ExternalServiceError) as exc_info:
        await adapter.get_profile(_USER_A)
    assert len(seen) == 1
    assert type(exc_info.value) is ExternalServiceError
    assert exc_info.value.message == "External service call failed"
    assert exc_info.value.details == {"service": "profile", "status_code": 503}


def _single_response(response: httpx.Response) -> tuple[list[httpx.Request], httpx.MockTransport]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return response

    return seen, httpx.MockTransport(handler)


async def test_real_invalid_payload() -> None:
    cases = [
        httpx.Response(200, text="not-json"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={"skills": "nope"}),
    ]
    for response in cases:
        seen, transport = _single_response(response)
        adapter = RealProfileAdapter(
            Settings(_env_file=None, profile_service_url="http://profile.test"),
            transport=transport,
        )
        with pytest.raises(ExternalServiceError) as exc_info:
            await adapter.get_profile(_USER_A)
        assert len(seen) == 1
        assert type(exc_info.value) is ExternalServiceError
        assert exc_info.value.message == "Profile service returned an invalid payload"
        assert exc_info.value.details == {"service": "profile", "reason": "invalid_payload"}
