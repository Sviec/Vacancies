# Прогресс реализации vacancies-service

Соответствует порядку раздела 12 ТЗ. Статус: `not started` / `in progress` / `done`.
Обновляется агентом по завершении этапа (см. `.cursor/rules/workflow.mdc`).

Код сервиса живёт в подпапке `vacancies-service/`. Папка `replit_template/` — read-only
визуальный референс (макеты `career-service`), в git не версионируется.

| # | Этап | Статус | Файлы | Допущения / TODO |
|---|---|---|---|---|
| 1 | Каркас проекта, конфиг, docker-compose, подключение БД | done | см. раздел «Этап 1» ниже | 15 допущений, см. ниже |
| 2 | Модели SQLAlchemy + миграции Alembic | not started | | |
| 3 | Pydantic-схемы, включая `NormalizedVacancy` | not started | | |
| 4 | `services/normalizer.py` + тесты | not started | | |
| 5 | CRUD API резюме и вакансий | not started | | |
| 6 | `services/resume_scorer.py` + `services/matching.py` + тесты | not started | | |
| 7 | `scripts/seed.py` | not started | | |
| 8 | Демо-фронтенд (все 4 экрана) на сид-данных | not started | | |
| 9 | Адаптеры LLM/profile с mock-реализациями | not started | | |
| 10 | ИИ-функции (генерация, tailor, формулировка рекомендаций) | not started | | |
| 11 | Парсеры (telegram → html) + RQ-задачи + планировщик | not started | | |
| 12 | README с инструкцией запуска | not started | | |

---

## Этап 1 — каркас проекта, конфиг, docker-compose, подключение БД

**Статус:** `done`. Проверено `mock-mode-auditor` (чисто), `visual-reviewer` (отклонения
исправлены или зафиксированы как допущения), `verifier` (блокирующих проблем нет).

### Созданные файлы

**Корень рабочего пространства**

| Файл | Назначение |
|---|---|
| `.gitignore` | Python / Node / env / Telethon-сессии / OS-IDE; исключает `replit_template/` |
| `.gitattributes` | нормализация переводов строк в LF (иначе CRLF ломает команды в Linux-образе) |

**`vacancies-service/` — бэкенд**

| Файл | Назначение |
|---|---|
| `pyproject.toml` | PEP 621 + hatchling, зависимости, конфиги ruff / mypy (strict) / pytest |
| `README.md` | заглушка; полноценный README — этап 12 |
| `.env.example`, `.env` | полное зеркало `Settings`; копирование без правок даёт рабочий mock-режим |
| `Dockerfile`, `.dockerignore` | `python:3.12-slim`, один образ на api и worker, non-root |
| `docker-compose.yml` | 5 сервисов: postgres, redis, api, worker, frontend |
| `app/__init__.py` | `__version__` |
| `app/config.py` | `Settings` на pydantic-settings, 42 поля, `get_settings()` с `lru_cache` |
| `app/main.py` | `create_app()`, `lifespan`, CORS, подключение роутеров |
| `app/api/health.py` | `GET /health` с проверками Postgres и Redis через `Depends` |
| `app/api/middleware.py` | `RequestContextMiddleware`: request_id, access-лог, `X-Request-ID` |
| `app/api/errors.py` | 4 обработчика исключений → единый конверт раздела 6 ТЗ |
| `app/api/v1/router.py` | агрегатор `/api/v1` с фиксированным порядком включения |
| `app/api/v1/{vacancies,recommendations,resumes,sources}.py` | роутеры-заглушки под этапы 5–11 |
| `app/db/session.py` | async engine и sessionmaker как модульные синглтоны, `get_session`, `SessionDep` |
| `app/db/redis.py` | async-клиент Redis, `RedisDep` |
| `app/tasks/worker.py` | точка входа RQ-воркера |
| `app/utils/logging.py` | `configure_logging` (structlog JSON), `get_logger` |
| `app/utils/errors.py` | `AppError` + 8 подклассов, `build_error_payload`, `HTTP_STATUS_TO_CODE` |
| `tests/conftest.py` | фикстуры; тесты офлайн через `ASGITransport` + `dependency_overrides` |
| `tests/test_health.py` | 3 теста: ok, деградация в 503, формат ошибки на 404 |
| `tests/test_config.py` | 2 теста: mock-режим по умолчанию, разбор `CORS_ORIGINS` из строки |

**`vacancies-service/frontend/` — скелет демо-страницы**

| Файл | Назначение |
|---|---|
| `package.json` | React 19.1, Vite 7, Tailwind 4, framer-motion, TanStack Query, lucide-react, recharts |
| `vite.config.ts` | прокси `/api` и `/health` на бэкенд, alias `@/`, polling для Docker на Windows |
| `tsconfig.json`, `tsconfig.node.json` | strict, `moduleResolution: bundler`, project references |
| `index.html` | `lang="ru"`, инлайновый скрипт применения темы до первой отрисовки |
| `Dockerfile`, `.dockerignore` | `node:24-alpine`, Vite dev-server |
| `src/index.css` | палитра раздела 8, светлая и тёмная темы, keyframes, focus-ring, reduced-motion |
| `src/lib/theme.tsx` | `ThemeProvider`, `useTheme`, режимы light / dark / system |
| `src/lib/api.ts` | `apiFetch`, `ApiError`, типы `HealthResponse` / `CheckResult` |
| `src/components/ThemeToggle.tsx` | переключатель темы |
| `src/App.tsx` | одна страница: статус сервиса в трёх состояниях (skeleton / успех / ошибка) |
| `src/main.tsx` | `StrictMode`, `ThemeProvider`, `QueryClientProvider` |

### Подтверждено исполнением

- `ruff check`, `ruff format --check`, `mypy app`, `pytest` (5 тестов), `npm run typecheck`, `npm run build` — все шесть чистые.
- `pytest` проходит без запущенных Postgres и Redis.
- `docker compose up -d --build` поднимает 5 контейнеров; postgres, redis, api — `healthy`.
- `GET /health` → 200, `status: ok`, обе зависимости зелёные.
- Остановка Redis → `/health` отдаёт 503 и `status: degraded`, API не падает; после возврата Redis снова 200.
- `http://localhost:5173/health` → 200 через Vite-прокси; `http://localhost:5173` → 200.
- Единый формат ошибок раздела 6 проверен на 404, 405, 422 и 500: `details` всегда объект, traceback и SQL в ответ не утекают.
- `create_app()` не падает при недоступной БД (нужно, чтобы `docker compose up` не ломался на гонке стартов).

### Принятые допущения

| # | Допущение | Где |
|---|---|---|
| 1 | React 19 + Tailwind 4 вместо «React 18» из раздела 1 ТЗ — чтобы вёрстка из макетов переносилась без переписывания | `frontend/package.json` |
| 2 | Python 3.12 вместо «3.11+ / последней» — на 3.14 не гарантированы asyncpg, Telethon, Playwright | `pyproject.toml` |
| 3 | `rq` запиннен `<2`, из-за этого `rq-scheduler` взят 0.13.x (0.14 требует rq 2.x); выбор пересмотреть на этапе 11 | `pyproject.toml` |
| 4 | `recharts` 3.x вместо 2.x из шаблона — 2.x конфликтует с React 19 по peer-зависимостям, а макеты recharts не используют | `frontend/package.json` |
| 5 | Postgres 16 (ТЗ требует «15+»), Node 24 в образе фронтенда | `docker-compose.yml`, `frontend/Dockerfile` |
| 6 | `/health` при деградации отдаёт 503 с телом `HealthResponse`, а не error-конверт раздела 6: health сообщает состояние сервиса, а не ошибку запроса | `app/api/health.py` |
| 7 | `recommendations.router` монтируется на префикс `/vacancies` и подключается раньше `vacancies.router`, иначе `/vacancies/recommended` будет съеден маршрутом `/vacancies/{id}` | `app/api/v1/router.py` |
| 8 | RQ использует `fork`, поэтому воркер работает только в Docker/Linux; локально на Windows не запускается | `app/tasks/worker.py` |
| 9 | CORS с `allow_credentials=False` — авторизации нет (п. 0.2), куки не используются | `app/main.py` |
| 10 | Alembic добавлен в зависимости на этапе 1, но `alembic.ini` и `migrations/` — этап 2; база поднимается пустой, `/health` этого не требует | `pyproject.toml`, `README.md` |
| 11 | Фронтенд запускается только как Vite dev-server; прод-сборка под nginx вне объёма | `frontend/Dockerfile` |
| 12 | Inter не подгружается с CDN (офлайн-требование п. 11.2) — используется системный стек с Inter первым | `frontend/index.html` |
| 13 | Фронтенд ходит по относительным путям через Vite-прокси, а не по абсолютному `VITE_API_BASE_URL` — поэтому CORS в браузере не возникает | `frontend/vite.config.ts` |
| 14 | Тёмная тема реализована полноценно, хотя раздел 8 помечает её опциональной; цвета живут в CSS-переменных на `:root`/`.dark`, а `@theme inline` только ссылается на них | `frontend/src/index.css` |
| 15 | Зацикленный shimmer у `.skeleton` идёт 1.25 с, формально выходя за лимит «не дольше 300 мс» раздела 8: лимит относится к разовым переходам, а цикл в 300 мс дал бы стробоскоп | `frontend/src/index.css` |
| 16 | `translateY(-2px)` в `.lift` сохранён: раздел 8 запрещает масштабирование, подъём на 2px им не является, свойств ровно два, и так сделано в утверждённых макетах | `frontend/src/index.css` |
| 17 | `WATCHFILES_FORCE_POLLING` и `VITE_USE_POLLING` включены: bind-mount Docker Desktop на Windows не доставляет inotify-события | `docker-compose.yml` |
| 18 | Порты хоста параметризованы (`API_HOST_PORT`, `POSTGRES_HOST_PORT`, ...); на машине разработки Postgres вынесен на 5433, потому что 5432 занят локальной службой | `.env`, `docker-compose.yml` |

### Незакрытые замечания (не блокируют этап)

- Логи api не на 100% JSON: строки uvicorn-reloader (`Started reloader process`, `WatchFiles detected changes`) идут мимо structlog. Access-логи `http_request` — валидный JSON с `request_id`.
- OpenAPI для `/health` описывает только 200, хотя при деградации ответ 503.
- Образ api ставит `.[dev]` (pytest, ruff, mypy) — лишний вес; разделить, если понадобится прод-образ.
- `clsx` и `tailwind-merge` установлены, но ещё не используются — понадобятся на этапе 8.

---

## Долги, запланированные на конкретные этапы

Найдены проверками на этапе 1, исправлять нужно там, где появится соответствующий код.

### Этап 2 (модели и Alembic)

- `Base` / `DeclarativeBase` нет — появится в `app/db/models.py`; `session.py` модели не импортирует, циклов нет.
- `target_metadata` для Alembic брать негде: нужен `alembic init`, `alembic.ini`, `migrations/env.py`.
- `migrations/` не монтируется в контейнеры и не копируется в образ — добавить и в `Dockerfile`, и в volumes, иначе bind-mount на Windows не донесёт файлы.

### Этап 8 (фронтенд)

- **Словарь токенов неполон** под литеральные hex макетов: нет `#57534E` (описания, компании), `--accent-hover` (`#334155`), `--accent-border` (`#CBD5E1`), `--overlay` (`#1C1917` 15–20% для drawer и модалок), `--surface-inset` (`#F0EFED`), `#94A3B8` для светлой темы, `#E2E8F0`, `#D6D3D1` для dashed-границ, токенов теней (карточка, дропдаун, модалка, drawer) и радиуса карточки.
- Переносить вёрстку макетов **только через токены**: `bg-white` → `bg-surface`, `text-[#1C1917]` → `text-ink`, `border-[#E7E5E4]` → `border-line`. Копирование hex-классов сломает тёмную тему.
- Нет общих оболочек и примитивов: `AppShell` (шапка сейчас зашита в `App.tsx`), `EmptyState`, `ErrorState`, `Skeleton`, `IconButton`, хелпер `cn()` на `clsx` + `tailwind-merge`.
- `prefers-reduced-motion` через CSS **не заглушит Framer Motion** — нужен `MotionConfig reducedMotion` или `useReducedMotion()`.
- Нет stagger-хелпера; договориться, CSS-класс `.rise` или Framer Motion, и не смешивать.
- Карточки в скелете используют `rounded-2xl` и `shadow-sm` вместо макетных `rounded-xl` и `0 1px 2px rgb(28 25 23 / 0.02)` — привести к макету.
- **Расхождение макетов с ТЗ, решить явно:** stagger в `Resumes.tsx` шаблона идёт по 45 мс без потолка, ТЗ требует 30 мс на первых восьми элементах.
- **Дыра и в ТЗ, и в шаблоне:** фильтры ниже 768px должны сворачиваться в модальное окно, в макетах этого паттерна нет — придётся проектировать.
- Экран «Источники» в макетах отсутствует — собирать из токенов, а не копировать.
- Заголовок страницы 30/34px против «20–24px» раздела 8: это утверждённый язык макетов, зафиксировать как исключение для display-заголовка, заголовки секций держать в 15–24px.
- Состояния загрузки, пустоты и ошибки обязательны на всех четырёх экранах; в макетах есть только пустое состояние ленты.

### Этап 9 (адаптеры LLM и profile)

- Добавить `model_validator`: режим `real` без ключа или URL — явная ошибка конфига на старте, а не таймаут в сеть. Режим `mock` ключа не требует.
- При `llm_mode="mock"` не читать `llm_api_key` и не создавать HTTP-клиент, даже если ключ заполнен. То же для `profile_mode="mock"` и `profile_service_url`.
- Выбор реализации — через `Depends` по `settings.*_mode`, без try/except вокруг реального SDK. Mock — детерминированные фикстуры, не `random` и не сеть.
- Пустые строки в `.env` уже нормализуются в `None`, поэтому в адаптере проверять `is None`, а не truthiness `SecretStr`.
- В тестах инстанцировать `Settings(_env_file=None)`, иначе локальный `.env` с `LLM_MODE=real` сломает офлайн-тесты.

### Этап 11 (парсеры)

- Playwright потребует либо `playwright install --with-deps chromium` в образе, либо базовый образ `mcr.microsoft.com/playwright/python`.
- Держать `PARSERS_ENABLED=false` в демо-конфиге: при включении HTML-парсер пойдёт за `robots.txt` во внешнюю сеть.
- Пересмотреть пин `rq<2` вместе с выбором планировщика.
