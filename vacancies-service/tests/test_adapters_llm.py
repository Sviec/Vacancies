"""Офлайн-тесты LLM-адаптера: фикстура и httpx.MockTransport."""

import json
from collections.abc import Callable
from uuid import UUID

import httpx
import pytest

from app.adapters.fixtures import mock_resume_draft
from app.adapters.llm import MockLLMAdapter, RealLLMAdapter
from app.adapters.profile import MockProfileAdapter
from app.config import Settings
from app.enums import EmploymentType, ExperienceLevel, WorkFormat
from app.schemas.adapters import CriterionFailure, VacancyEnrichmentInput
from app.schemas.ai import ResumeGenerateRequest
from app.schemas.scoring import ScoreCriterionKey, ScoreIssue
from app.utils.errors import ExternalServiceError, LLMResponseInvalidError

_USER = UUID("00000000-0000-0000-0000-000000000001")


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


def _completion(content: str, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        json={"choices": [{"message": {"role": "assistant", "content": content}}]},
    )


def _transport(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[list[httpx.Request], httpx.MockTransport]:
    seen: list[httpx.Request] = []

    def _spy(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return seen, httpx.MockTransport(_spy)


def _queue(responses: list[httpx.Response]) -> tuple[list[httpx.Request], httpx.MockTransport]:
    pending = list(responses)

    def handler(_request: httpx.Request) -> httpx.Response:
        return pending.pop(0)

    return _transport(handler)


def _draft_content() -> str:
    return json.dumps(
        mock_resume_draft("Data Scientist").model_dump(mode="json"), ensure_ascii=False
    )


def _user_text(request: httpx.Request) -> str:
    body = json.loads(request.content)
    return str(body["messages"][1]["content"])


async def test_mock_generate_is_deterministic() -> None:
    adapter = MockLLMAdapter()
    profile = await MockProfileAdapter().get_profile(_USER)
    first = await adapter.generate_resume(
        ResumeGenerateRequest(raw_text="один текст", target_position="  Analyst  ")
    )
    second = await adapter.generate_resume(
        ResumeGenerateRequest(raw_text="другой текст", target_position="  Analyst  ")
    )
    assert first == second
    assert first.title == "Analyst"
    assert first.target_position == "Analyst"
    assert first.summary == "Черновик резюме из mock-адаптера."
    assert first.desired_salary_min == 200_000
    assert first.desired_salary_currency == "RUB"
    assert first.desired_country == "Россия"
    assert first.desired_city == "Москва"
    assert first.desired_work_format == WorkFormat.REMOTE
    assert first.is_primary is False
    assert first.experience == profile.experience
    assert first.education == profile.education
    assert first.skills == profile.skills
    assert first.languages == profile.languages
    fallback = await adapter.generate_resume(
        ResumeGenerateRequest(raw_text="ещё", target_position=None)
    )
    blank = await adapter.generate_resume(
        ResumeGenerateRequest(raw_text="иной", target_position="   ")
    )
    assert fallback == blank
    assert fallback.title == "Data Scientist"
    assert fallback == await adapter.generate_resume(ResumeGenerateRequest(raw_text="ещё"))


async def test_mock_tailor_changes_only_summary() -> None:
    adapter = MockLLMAdapter()
    draft = await adapter.generate_resume(
        ResumeGenerateRequest(raw_text="сырой", target_position="Data Scientist")
    )
    original = draft.model_dump()
    tailored = await adapter.tailor_resume(draft, "Аналитик", ["python", "sql"])
    assert draft.model_dump() == original
    assert tailored.summary == "Под вакансию «Аналитик». Навыки: python, sql."
    changed = tailored.model_dump()
    changed["summary"] = original["summary"]
    assert changed == original


async def test_mock_recommendations_follow_input_order() -> None:
    adapter = MockLLMAdapter()
    failures = [
        CriterionFailure(
            key=ScoreCriterionKey.LANGUAGES,
            issues=[ScoreIssue(code="missing", context={"b": 1, "a": "x", "flag": False})],
        ),
        CriterionFailure(key=ScoreCriterionKey.COMPLETENESS, issues=[]),
        CriterionFailure(
            key=ScoreCriterionKey.SKILLS_RELEVANCE,
            issues=[
                ScoreIssue(code="low", context={}),
                ScoreIssue(code="gap", context={"skill": "sql"}),
            ],
        ),
    ]
    assert await adapter.phrase_recommendations(failures) == [
        "languages:missing|a=x,b=1,flag=false",
        "completeness:",
        "skills_relevance:low|,gap|skill=sql",
    ]
    assert await adapter.phrase_recommendations([]) == []


async def test_mock_enrich_echoes_title_and_is_stable() -> None:
    adapter = MockLLMAdapter()
    first = await adapter.enrich_vacancy(
        VacancyEnrichmentInput(title="  ML  ", description_raw="шум", company=None)
    )
    second = await adapter.enrich_vacancy(
        VacancyEnrichmentInput(title="  ML  ", description_raw="другой шум", company=None)
    )
    assert first == second
    assert first is not second
    assert first.title == "ML"
    assert first.company == "Mock Company"
    assert first.description_clean == "Очищенное описание из mock-адаптера."
    assert first.skills == ["python", "sql"]
    assert first.city == "Москва"
    assert first.country == "Россия"
    assert first.work_format == WorkFormat.REMOTE
    assert first.experience_level == ExperienceLevel.MIDDLE
    assert first.employment_type == EmploymentType.FULL_TIME
    assert first.salary_min == 200_000
    assert first.salary_max == 300_000
    assert first.salary_currency == "RUB"
    named = await adapter.enrich_vacancy(
        VacancyEnrichmentInput(title="   ", description_raw="x", company="Acme")
    )
    assert named.title == "Data Scientist"
    assert named.company == "Acme"


async def test_mock_llm_does_not_open_http(monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("HTTP client must not be created")

    monkeypatch.setattr(httpx.AsyncClient, "__init__", _forbidden)
    monkeypatch.setattr(httpx.Client, "__init__", _forbidden)
    adapter = MockLLMAdapter()
    draft = await adapter.generate_resume(ResumeGenerateRequest(raw_text="текст"))
    tailored = await adapter.tailor_resume(draft, "Роль", ["sql"])
    phrases = await adapter.phrase_recommendations([])
    enriched = await adapter.enrich_vacancy(
        VacancyEnrichmentInput(title="ML", description_raw="текст")
    )
    assert draft.title == "Data Scientist"
    assert tailored.summary.startswith("Под вакансию")
    assert phrases == []
    assert enriched.company == "Mock Company"


async def test_real_missing_api_key_makes_no_request() -> None:
    seen, transport = _queue([_completion('{"title": "Data Scientist"}')])
    adapter = RealLLMAdapter(
        _settings(llm_mode="real", llm_api_key=None, llm_base_url="https://llm.example/v1"),
        transport=transport,
    )
    with pytest.raises(ExternalServiceError) as exc_info:
        await adapter.generate_resume(ResumeGenerateRequest(raw_text="текст"))
    assert seen == []
    assert type(exc_info.value) is ExternalServiceError
    assert exc_info.value.message == "LLM API key is not configured"
    assert exc_info.value.details == {"service": "llm", "reason": "missing_api_key"}


async def test_real_anthropic_without_base_url_makes_no_request() -> None:
    seen, transport = _queue([_completion('{"title": "Data Scientist"}')])
    adapter = RealLLMAdapter(
        _settings(
            llm_mode="real",
            llm_provider="anthropic",
            llm_api_key="sk-test",
            llm_base_url=None,
        ),
        transport=transport,
    )
    with pytest.raises(ExternalServiceError) as exc_info:
        await adapter.generate_resume(ResumeGenerateRequest(raw_text="текст"))
    assert seen == []
    assert exc_info.value.message == "LLM base URL is not configured"
    assert exc_info.value.details == {"service": "llm", "reason": "missing_base_url"}


async def test_real_openai_default_url_and_bearer() -> None:
    seen, transport = _queue([_completion('{"title": "Data Scientist"}')])
    adapter = RealLLMAdapter(
        _settings(
            llm_mode="real",
            llm_provider="openai",
            llm_api_key="sk-test",
            llm_base_url=None,
            llm_model="test-model",
        ),
        transport=transport,
    )
    draft = await adapter.generate_resume(ResumeGenerateRequest(raw_text="текст"))
    assert draft.title == "Data Scientist"
    assert len(seen) == 1
    request = seen[0]
    assert str(request.url) == "https://api.openai.com/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer sk-test"
    body = json.loads(request.content)
    assert body["model"] == "test-model"
    assert body["temperature"] == 0
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"][0]["role"] == "system"
    assert "sk-test" not in request.content.decode()


async def test_real_generate_parses_message_content() -> None:
    content = _draft_content()
    seen, transport = _queue([_completion(content)])
    adapter = RealLLMAdapter(
        _settings(
            llm_mode="real",
            llm_api_key="sk-test",
            llm_base_url="https://llm.example/v1/",
        ),
        transport=transport,
    )
    draft = await adapter.generate_resume(
        ResumeGenerateRequest(raw_text="сырой текст", target_position="ignored-by-real")
    )
    assert draft == mock_resume_draft("Data Scientist")
    assert str(seen[0].url) == "https://llm.example/v1/chat/completions"


async def test_real_strips_markdown_fence() -> None:
    fenced = f"```json\n{_draft_content()}\n```"
    _seen, transport = _queue([_completion(fenced)])
    adapter = RealLLMAdapter(
        _settings(llm_mode="real", llm_api_key="sk-test", llm_base_url="https://llm.example/v1"),
        transport=transport,
    )
    draft = await adapter.generate_resume(ResumeGenerateRequest(raw_text="текст"))
    assert draft == mock_resume_draft("Data Scientist")


async def test_real_retries_invalid_json_once() -> None:
    seen, transport = _queue([_completion("not-json"), _completion('{"title": "Data Scientist"}')])
    adapter = RealLLMAdapter(
        _settings(llm_mode="real", llm_api_key="sk-test", llm_base_url="https://llm.example/v1"),
        transport=transport,
    )
    draft = await adapter.generate_resume(ResumeGenerateRequest(raw_text="текст"))
    assert draft.title == "Data Scientist"
    assert len(seen) == 2
    assert "Previous response was invalid:" not in _user_text(seen[0])
    assert "Previous response was invalid:" in _user_text(seen[1])
    assert "Return only a JSON object." in _user_text(seen[1])


async def test_real_invalid_twice_raises() -> None:
    seen, transport = _queue([_completion("not-json"), _completion("{")])
    adapter = RealLLMAdapter(
        _settings(llm_mode="real", llm_api_key="sk-test", llm_base_url="https://llm.example/v1"),
        transport=transport,
    )
    with pytest.raises(LLMResponseInvalidError) as exc_info:
        await adapter.generate_resume(ResumeGenerateRequest(raw_text="текст"))
    assert len(seen) == 2
    assert exc_info.value.code == "LLM_RESPONSE_INVALID"
    assert exc_info.value.details["attempts"] == 2
    reason = exc_info.value.details["reason"]
    assert isinstance(reason, str)
    assert reason
    assert len(reason) <= 300


async def test_real_schema_mismatch_retries() -> None:
    seen, transport = _queue(
        [_completion('{"title": 1}'), _completion('{"title": "Data Scientist"}')]
    )
    adapter = RealLLMAdapter(
        _settings(llm_mode="real", llm_api_key="sk-test", llm_base_url="https://llm.example/v1"),
        transport=transport,
    )
    draft = await adapter.generate_resume(ResumeGenerateRequest(raw_text="текст"))
    assert draft.title == "Data Scientist"
    assert len(seen) == 2
    assert "Previous response was invalid:" in _user_text(seen[1])


async def test_real_recommendations_length_mismatch_is_invalid() -> None:
    failures = [
        CriterionFailure(key=ScoreCriterionKey.COMPLETENESS, issues=[]),
        CriterionFailure(key=ScoreCriterionKey.LANGUAGES, issues=[]),
    ]
    short = json.dumps({"items": ["only-one"]})
    seen, transport = _queue([_completion(short), _completion(short)])
    adapter = RealLLMAdapter(
        _settings(llm_mode="real", llm_api_key="sk-test", llm_base_url="https://llm.example/v1"),
        transport=transport,
    )
    with pytest.raises(LLMResponseInvalidError) as exc_info:
        await adapter.phrase_recommendations(failures)
    assert len(seen) == 2
    assert exc_info.value.details["attempts"] == 2


async def test_real_http_500_does_not_retry() -> None:
    seen, transport = _queue(
        [
            httpx.Response(500, json={"error": "boom"}),
            _completion('{"title": "Data Scientist"}'),
        ]
    )
    adapter = RealLLMAdapter(
        _settings(llm_mode="real", llm_api_key="sk-test", llm_base_url="https://llm.example/v1"),
        transport=transport,
    )
    with pytest.raises(ExternalServiceError) as exc_info:
        await adapter.generate_resume(ResumeGenerateRequest(raw_text="текст"))
    assert len(seen) == 1
    assert type(exc_info.value) is ExternalServiceError
    assert exc_info.value.message == "External service call failed"
    assert exc_info.value.details == {"service": "llm", "status_code": 500}


async def test_real_timeout_does_not_retry() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        raise httpx.ReadTimeout("timed out", request=request)

    adapter = RealLLMAdapter(
        _settings(llm_mode="real", llm_api_key="sk-test", llm_base_url="https://llm.example/v1"),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ExternalServiceError) as exc_info:
        await adapter.tailor_resume(mock_resume_draft("Data Scientist"), "Роль", ["python"])
    assert len(seen) == 1
    assert type(exc_info.value) is ExternalServiceError
    assert exc_info.value.message == "External service call failed"
    assert exc_info.value.details == {"service": "llm", "reason": "timeout"}
