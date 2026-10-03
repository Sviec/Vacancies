"""Адаптер LLM: mock и OpenAI-compatible chat completions (раздел 9 ТЗ).

Повтор при невалидном JSON живёт здесь, чтобы этап 10 только вызвал метод.
Импорт модуля не создаёт HTTP-клиент и не требует ключа.
"""

import json
from collections.abc import Callable, Sequence
from typing import Protocol

import httpx
from pydantic import BaseModel, ValidationError

from app.adapters.fixtures import (
    MOCK_FALLBACK_COMPANY,
    MOCK_FALLBACK_TITLE,
    mock_resume_draft,
    mock_vacancy_enrichment,
    resolved_draft_title,
)
from app.config import Settings
from app.schemas.adapters import (
    CriterionFailure,
    RecommendationPhrases,
    VacancyEnrichment,
    VacancyEnrichmentInput,
)
from app.schemas.ai import ResumeDraft, ResumeGenerateRequest
from app.services.resume_scorer import render_recommendation
from app.utils.errors import ExternalServiceError, LLMResponseInvalidError

_SERVICE = "llm"
_ERROR_SNIPPET_LIMIT = 300
_DEFAULT_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}
_SYSTEM_PROMPT = (
    "Return only a JSON object without markdown. "
    "The object must match the JSON schema from the user message."
)
_TASK_GENERATE = "Generate a resume draft from the input."
_TASK_TAILOR = (
    "Tailor the resume draft to the vacancy. "
    "Rewrite the summary and the emphasis of experience descriptions and achievements "
    "to match the vacancy; do not change the JSON shape."
)
_TASK_RECOMMENDATIONS = "Write one recommendation phrase per criterion failure, in input order."
_TASK_ENRICH = "Extract structured vacancy fields from the input."


class LLMAdapter(Protocol):
    """Контракт вызовов LLM. Реализация подставляется через Depends."""

    async def generate_resume(self, request: ResumeGenerateRequest) -> ResumeDraft:
        """Собрать черновик резюме из сырого текста."""
        ...

    # TODO: обогащение вакансии никто из парсеров не вызывает (этап 11).
    async def tailor_resume(
        self,
        draft: ResumeDraft,
        vacancy_title: str,
        vacancy_skills: Sequence[str],
    ) -> ResumeDraft:
        """Подстроить черновик под название и навыки вакансии."""
        ...

    async def phrase_recommendations(self, failures: Sequence[CriterionFailure]) -> list[str]:
        """Фраза на каждый провал. Порядок ответа совпадает с порядком входа."""
        ...

    async def enrich_vacancy(self, vacancy: VacancyEnrichmentInput) -> VacancyEnrichment:
        """Добрать поля вакансии из сырого текста."""
        ...


class MockLLMAdapter:
    """Детерминированные ответы. Не принимает Settings и не открывает HTTP."""

    async def generate_resume(self, request: ResumeGenerateRequest) -> ResumeDraft:
        """Черновик из фикстуры. raw_text на результат не влияет."""
        title = resolved_draft_title(request.target_position)
        return mock_resume_draft(title)

    async def tailor_resume(
        self,
        draft: ResumeDraft,
        vacancy_title: str,
        vacancy_skills: Sequence[str],
    ) -> ResumeDraft:
        """Копия черновика, в которой меняется только summary."""
        skills = ", ".join(vacancy_skills)
        summary = f"Под вакансию «{vacancy_title}». Навыки: {skills}."
        return draft.model_copy(update={"summary": summary}, deep=True)

    async def phrase_recommendations(self, failures: Sequence[CriterionFailure]) -> list[str]:
        """Шаблон `render_recommendation` на каждый провал. Порядок входа сохраняется."""
        return [_mock_phrase(failure) for failure in failures]

    async def enrich_vacancy(self, vacancy: VacancyEnrichmentInput) -> VacancyEnrichment:
        """Стабильное обогащение. description_raw не читается."""
        title = vacancy.title.strip() or MOCK_FALLBACK_TITLE
        company = vacancy.company or MOCK_FALLBACK_COMPANY
        return mock_vacancy_enrichment(title=title, company=company)


class RealLLMAdapter:
    """Chat completions. Клиент создаётся на вызов метода, не в конструкторе."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def generate_resume(self, request: ResumeGenerateRequest) -> ResumeDraft:
        """Сгенерировать черновик. Схема ответа — ResumeDraft."""
        return await self._run(
            task=_TASK_GENERATE,
            payload=request.model_dump(mode="json"),
            response_model=ResumeDraft,
            extra_check=None,
        )

    async def tailor_resume(
        self,
        draft: ResumeDraft,
        vacancy_title: str,
        vacancy_skills: Sequence[str],
    ) -> ResumeDraft:
        """Подстроить черновик. Схема ответа — ResumeDraft."""
        payload = {
            "draft": draft.model_dump(mode="json"),
            "vacancy_title": vacancy_title,
            "vacancy_skills": list(vacancy_skills),
        }
        return await self._run(
            task=_TASK_TAILOR,
            payload=payload,
            response_model=ResumeDraft,
            extra_check=None,
        )

    async def phrase_recommendations(self, failures: Sequence[CriterionFailure]) -> list[str]:
        """Фразы в обёртке RecommendationPhrases. Длина items обязана совпасть с входом."""
        expected = len(failures)

        def _check_length(parsed: RecommendationPhrases) -> None:
            if len(parsed.items) != expected:
                msg = f"items length {len(parsed.items)} != failures length {expected}"
                raise ValueError(msg)

        parsed = await self._run(
            task=_TASK_RECOMMENDATIONS,
            payload=[failure.model_dump(mode="json") for failure in failures],
            response_model=RecommendationPhrases,
            extra_check=_check_length,
        )
        return parsed.items

    async def enrich_vacancy(self, vacancy: VacancyEnrichmentInput) -> VacancyEnrichment:
        """Обогатить вакансию. Схема ответа — VacancyEnrichment."""
        return await self._run(
            task=_TASK_ENRICH,
            payload=vacancy.model_dump(mode="json"),
            response_model=VacancyEnrichment,
            extra_check=None,
        )

    async def _run[ModelT: BaseModel](
        self,
        *,
        task: str,
        payload: object,
        response_model: type[ModelT],
        extra_check: Callable[[ModelT], None] | None,
    ) -> ModelT:
        """Проверить конфиг до клиента и запросить JSON с повтором разбора."""
        url, api_key = _llm_endpoint(self._settings)
        async with httpx.AsyncClient(
            timeout=self._settings.llm_timeout_seconds,
            transport=self._transport,
        ) as client:
            return await _complete_json(
                client,
                url=url,
                api_key=api_key,
                model_name=self._settings.llm_model,
                task=task,
                payload=payload,
                response_model=response_model,
                extra_check=extra_check,
                max_retries=self._settings.llm_max_retries,
            )


def build_llm_adapter(settings: Settings) -> LLMAdapter:
    """Mock не читает ключ и не создаёт клиент. Real получает Settings как есть."""
    if settings.llm_mode == "mock":
        return MockLLMAdapter()
    return RealLLMAdapter(settings)


def _llm_endpoint(settings: Settings) -> tuple[str, str]:
    """Ключ и URL проверяются до создания клиента. Вернуть (url, secret)."""
    if settings.llm_api_key is None:
        raise ExternalServiceError(
            "LLM API key is not configured",
            details={"service": _SERVICE, "reason": "missing_api_key"},
        )
    base_url = _resolve_base_url(settings)
    return f"{base_url.rstrip('/')}/chat/completions", settings.llm_api_key.get_secret_value()


def _resolve_base_url(settings: Settings) -> str:
    """Явный LLM_BASE_URL перекрывает дефолт провайдера."""
    # TODO: LLM_PROVIDER=anthropic не вызывает Messages API Anthropic; без
    # LLM_BASE_URL вызов падает, с URL идёт OpenAI-compatible /chat/completions.
    if settings.llm_base_url is not None:
        return settings.llm_base_url
    default = _DEFAULT_BASE_URLS.get(settings.llm_provider)
    if default is None:
        raise ExternalServiceError(
            "LLM base URL is not configured",
            details={"service": _SERVICE, "reason": "missing_base_url"},
        )
    return default


def _mock_phrase(failure: CriterionFailure) -> str:
    # TODO: если шаблон вернул None, mock отдаёт пустую строку, а не пропуск элемента.
    text = render_recommendation(failure.key, failure.issues)
    return "" if text is None else text


def _clip(text: str) -> str:
    compact = " ".join(text.split())
    if len(compact) <= _ERROR_SNIPPET_LIMIT:
        return compact
    return compact[:_ERROR_SNIPPET_LIMIT]


def _user_message(task: str, payload: object, response_model: type[BaseModel]) -> str:
    rendered_input = json.dumps(payload, ensure_ascii=False)
    rendered_schema = json.dumps(response_model.model_json_schema(), ensure_ascii=False)
    return f"{task}\n\nInput:\n{rendered_input}\n\nJSON schema:\n{rendered_schema}"


def _with_retry_hint(original: str, reason: str) -> str:
    return f"{original}\n\nPrevious response was invalid: {reason}. Return only a JSON object."


def _strip_markdown_fence(text: str) -> str:
    """Снять одну ограду ``` вокруг текста. Вторую обёртку не трогаем."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    newline = stripped.find("\n")
    if newline == -1:
        return stripped
    body = stripped[newline + 1 :].rstrip()
    if body.endswith("```"):
        body = body[:-3].rstrip()
    return body.strip()


def _message_content(payload: object) -> str:
    """Достать choices[0].message.content. Нестрока — невалидный ответ."""
    # TODO: content чата обязан быть строкой; составной массив контента не поддерживается.
    if not isinstance(payload, dict):
        msg = "LLM response is not a JSON object"
        raise ValueError(msg)
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        msg = "LLM response does not contain choices"
        raise ValueError(msg)
    first = choices[0]
    if not isinstance(first, dict):
        msg = "LLM choice is not an object"
        raise ValueError(msg)
    message = first.get("message")
    if not isinstance(message, dict):
        msg = "LLM choice does not contain a message"
        raise ValueError(msg)
    content = message.get("content")
    if not isinstance(content, str):
        msg = "LLM message content must be a string"
        raise ValueError(msg)
    return content


def _parse_model[ModelT: BaseModel](payload: object, response_model: type[ModelT]) -> ModelT:
    content = _message_content(payload)
    try:
        data = json.loads(_strip_markdown_fence(content))
    except json.JSONDecodeError as exc:
        raise ValueError(str(exc)) from None
    try:
        return response_model.model_validate(data)
    except ValidationError as exc:
        raise ValueError(str(exc)) from None


def _read_body(response: httpx.Response) -> object:
    try:
        return response.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(str(exc)) from None


async def _complete_json[ModelT: BaseModel](
    client: httpx.AsyncClient,
    *,
    url: str,
    api_key: str,
    model_name: str,
    task: str,
    payload: object,
    response_model: type[ModelT],
    extra_check: Callable[[ModelT], None] | None,
    max_retries: int,
) -> ModelT:
    """Один клиент на вызов. Повтор только если не разобрали JSON или схему."""
    # TODO: повтор только для невалидного JSON/схемы; HTTP и таймаут не повторяются.
    attempts = 1 + max(0, max_retries)
    original = _user_message(task, payload, response_model)
    user_prompt = original
    last_reason = "invalid response"
    for _attempt in range(attempts):
        try:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model_name,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                },
            )
        except httpx.RequestError as exc:
            raise _network_error(exc) from None
        if response.status_code < 200 or response.status_code >= 300:
            raise _status_error(response.status_code)
        try:
            parsed = _parse_model(_read_body(response), response_model)
            if extra_check is not None:
                extra_check(parsed)
        except ValueError as exc:
            last_reason = _clip(str(exc))
            user_prompt = _with_retry_hint(original, last_reason)
            continue
        return parsed
    raise LLMResponseInvalidError(details={"attempts": attempts, "reason": last_reason})


def _network_error(exc: httpx.RequestError) -> ExternalServiceError:
    reason = "timeout" if isinstance(exc, httpx.TimeoutException) else "connect"
    return ExternalServiceError(
        "External service call failed",
        details={"service": _SERVICE, "reason": reason},
    )


def _status_error(status_code: int) -> ExternalServiceError:
    return ExternalServiceError(
        "External service call failed",
        details={"service": _SERVICE, "status_code": status_code},
    )
