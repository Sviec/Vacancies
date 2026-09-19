---
name: error-format
description: Единый формат ошибок API для vacancies-service. Use when writing or editing any file under app/api/v1, exception handlers, or FastAPI error responses.
---

# Единый формат ошибок API

Все ошибки API возвращаются в одном формате:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Человекочитаемое описание проблемы",
    "details": { "field": "salary_min", "reason": "must be >= 0" }
  }
}
```

## Правила
- `code` — стабильная машиночитаемая строка в SCREAMING_SNAKE_CASE (`NOT_FOUND`, `VALIDATION_ERROR`, `PARSE_FAILED`, `LLM_RESPONSE_INVALID` и т.п.), по ней фронтенд может ветвить обработку.
- `message` — понятное описание на русском или английском (консистентно с остальным API), без утечки внутренних деталей (stacktrace, SQL).
- `details` — опциональный объект с контекстом ошибки (какое поле, какое значение ожидалось). Пустой объект `{}`, если деталей нет — не `null`.
- Реализовать через единый FastAPI exception handler (`app/main.py` или `app/api/errors.py`), а не через ручное формирование JSON в каждом эндпоинте.
- HTTP-статусы остаются стандартными (404, 422, 500 и т.д.) — формат `error` не заменяет статус-код, а дополняет тело ответа.
- Для `POST /api/v1/resumes/generate` при неудачном повторе разбора JSON от LLM (раздел 5.3) — использовать код вроде `LLM_RESPONSE_INVALID` с понятным `message`, а не общий `500`.
