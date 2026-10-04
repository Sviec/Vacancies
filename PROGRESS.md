# Прогресс реализации vacancies-service

Соответствует порядку раздела 12 ТЗ. Статус: `not started` / `in progress` / `done`.
Обновляется агентом по завершении этапа (см. `.cursor/rules/workflow.mdc`).

Код сервиса живёт в подпапке `vacancies-service/`. Папка `replit_template/` — read-only
визуальный референс (макеты `career-service`), в git не версионируется.

| # | Этап | Статус | Файлы | Допущения / TODO |
|---|---|---|---|---|
| 1 | Каркас проекта, конфиг, docker-compose, подключение БД | done | см. раздел «Этап 1» ниже | 15 допущений, см. ниже |
| 2 | Модели SQLAlchemy + миграции Alembic | done | см. раздел «Этап 2» ниже | 20 допущений, см. ниже |
| 3 | Pydantic-схемы, включая `NormalizedVacancy` | done | см. раздел «Этап 3» ниже | 8 допущений, см. ниже |
| 4 | `services/normalizer.py` + тесты | done | см. раздел «Этап 4» ниже | 26 допущений, см. ниже |
| 5 | CRUD API резюме и вакансий | done | см. раздел «Этап 5» ниже | 26 допущений, см. ниже |
| 6 | `services/resume_scorer.py` + `services/matching.py` + тесты | done | см. раздел «Этап 6» ниже | 20 допущений, см. ниже |
| 7 | `scripts/seed.py` | done | см. раздел «Этап 7» ниже | 13 допущений, см. ниже |
| 8 | Демо-фронтенд (все 4 экрана) на сид-данных | done | см. раздел «Этап 8» ниже | 12 допущений, см. ниже |
| 9 | Адаптеры LLM/profile с mock-реализациями | done | см. раздел «Этап 9» ниже | 8 допущений, см. ниже |
| 10 | ИИ-функции (генерация, tailor, формулировка рекомендаций) | done | см. раздел «Этап 10» ниже | 8 допущений, см. ниже |
| 11 | Парсеры (telegram → html) + RQ-задачи + планировщик | done | см. раздел «Этап 11» ниже | 14 допущений, см. ниже |
| 12 | README с инструкцией запуска | done | см. раздел «Этап 12» ниже | 2 допущения, см. ниже |

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

### Незакрытые замечания этапа 1 (не блокируют)

- Логи api не на 100% JSON: строки uvicorn-reloader (`Started reloader process`, `WatchFiles detected changes`) идут мимо structlog. Access-логи `http_request` — валидный JSON с `request_id`.
- OpenAPI для `/health` описывает только 200, хотя при деградации ответ 503.
- Образ api ставит `.[dev]` (pytest, ruff, mypy) — лишний вес; разделить, если понадобится прод-образ.
- `clsx` и `tailwind-merge` установлены, но ещё не используются — понадобятся на этапе 8.

---

## Этап 2 — модели SQLAlchemy + миграции Alembic

**Статус:** `done`. Схема накатана, `migrate` в compose завершается с кодом 0,
`/health` остаётся 200, офлайн-тесты и дрейф-тест зелёные.
Проверки закрытия: `verifier` — блокеров нет; `mock-mode-auditor` — каркас изолирован
(полный сценарий раздела 7 ещё не применим: нет seed/UI/ИИ).

### Созданные и изменённые файлы

| Файл | Назначение |
|---|---|
| `app/enums.py` | 10 `StrEnum` домена; переиспользуются схемами этапа 3 |
| `app/db/base.py` | `Base`, `NAMING_CONVENTION`, `type_annotation_map`, миксины, `enum_column` |
| `app/db/models.py` | 12 моделей: канонические `vacancies` + публикации `vacancy_postings` и остальное из раздела 4 |
| `alembic.ini` | DSN пустой, читается из `Settings`; комментарии ASCII из‑за cp1251 на Windows |
| `migrations/env.py` | async Alembic, DSN из `get_settings()`, `compare_type`/`compare_server_default` |
| `migrations/script.py.mako` | шаблон ревизий с условным импортом `postgresql` |
| `migrations/versions/20260919_2303_ba833660ecb2_initial_schema.py` | первая ревизия, 12 таблиц |
| `tests/test_models_metadata.py` | офлайн-инварианты схемы |
| `tests/test_migrations_offline.py` | одна голова, рабочий `downgrade` |
| `tests/integration/conftest.py` | пересоздание `vacancies_test` |
| `tests/integration/test_migration_drift.py` | `upgrade head` + пустой `compare_metadata` |
| `Dockerfile` | `COPY alembic.ini` и `migrations/` |
| `docker-compose.yml` | сервис `migrate`, api/worker ждут `service_completed_successfully` |
| `pyproject.toml` | маркер `integration`, `known-first-party`, `extend-exclude` для `migrations/versions` |
| `README.md` | заглушка: миграции накатывает `migrate` |

### Подтверждено исполнением

- `ruff check`, `ruff format --check`, `mypy app` — чисто.
- `pytest` — 51 passed, 2 deselected (integration), без Postgres/Redis.
- `pytest -m integration` — 2 passed (предупреждение Alembic про computed `search_vector` ожидаемо).
- `\dt` — 12 таблиц + `alembic_version`.
- `vacancies`: UNIQUE `dedup_key`, GIN на `skills` и `search_vector`, btree на `source`/`published_at`, generated `search_vector`; нет `content_hash`/`external_id`/`raw_payload`.
- `vacancy_postings`: UNIQUE `(source, external_id)` и `(source, content_hash)`, btree `(vacancy_id, source)`, FK CASCADE.
- `resumes`: частичный UNIQUE `uq_resumes_primary_per_user WHERE is_primary`.
- Две строки с `dedup_key IS NULL` вставляются; одинаковый непустой ключ даёт `uq_vacancies_dedup_key`.
- `docker compose up -d --build`: `migrate` Exited 0, api/postgres/redis healthy, `/health` = 200.
- Ревизия видна в образе: `/srv/migrations/versions/20260919_2303_ba833660ecb2_initial_schema.py`.

### Принятые допущения этапа 2

| # | Допущение | Где |
|---|---|---|
| 1 | PK везде `UUID` (`uuid4` на стороне Python), не `bigint` | `app/db/base.py` |
| 2 | `uuid4`, не `uuid7`: в stdlib 3.12 его нет | `app/db/base.py` |
| 3 | Enum — `VARCHAR` + `CHECK` (`native_enum=False`), не PG ENUM | `app/db/base.py` |
| 4 | Деньги — `Integer`; риск int4 на экзотических валютах | `app/db/models.py` |
| 5 | **Отклонение от раздела 3:** дедупликация по `company+title+city`, не по `content_hash` описания | `app/db/models.py` |
| 6 | Две таблицы: `vacancies` (канонический оффер) и `vacancy_postings` (появление в источнике) | `app/db/models.py` |
| 7 | Каноническая запись денормализована: поля победителя копируются, без `primary_posting_id` | `app/db/models.py` |
| 8 | Победитель: `parse_quality=full`, затем макс. длина описания; поля проигравших не подмешиваются | `app/db/models.py` |
| 9 | `dedup_key` — sha256 тройки, заполняется сервисным слоем (этап 4), не GENERATED | `app/db/models.py` |
| 10 | `UNIQUE(dedup_key)` обычный: NULL различны, вакансии без компании не конфликтуют | `app/db/models.py` |
| 11 | Без компании `dedup_key=NULL`, склейки нет | `app/db/models.py` |
| 12 | Пустой город — пустая третья компонента ключа, иначе склейка транзитивна | `app/db/models.py` |
| 13 | **Отклонение от раздела 4:** `content_hash` на публикациях, UNIQUE `(source, content_hash)` | `app/db/models.py` |
| 14 | `published_at` канонической записи — MIN по публикациям; `last_seen_at` — MAX | `app/db/models.py` |
| 15 | Склейка глобальна во времени, без окна 60 дней | решение пользователя |
| 16 | Нормализация заголовка консервативная (этап 4): грейд и скобки сохраняем | решение пользователя |
| 17 | Операции «разделить вакансию» нет | решение пользователя |
| 18 | `resumes.contacts` JSONB и `origin` сверх раздела 4 | `app/db/models.py` |
| 19 | `vacancies.source` без FK на `sources.slug` | `app/db/models.py` |
| 20 | `alembic.ini` в образе через COPY; bind-mount `./migrations` только у `migrate` | `Dockerfile`, `docker-compose.yml` |

### Незакрытые замечания этапа 2 (не блокируют)

- Alembic `compare_server_default` предупреждает, что generated `vacancies.search_vector` нельзя изменить через autogenerate — дрейф-тест зелёный, править руками при смене FTS.
- `ruff` не форматтит `migrations/versions/` (`extend-exclude`): autogenerate пишет длинные `op.create_table`.
- Допущение 10 этапа 1 закрыто: `alembic.ini` и `migrations/` на месте, `migrate` накатывает схему при `compose up`.

---

## Этап 3 — Pydantic-схемы, включая `NormalizedVacancy`

**Статус:** `done`. Эндпоинты не вешались. `verifier` — блокеров нет.

### Созданные файлы

| Файл | Назначение |
|---|---|
| `app/schemas/__init__.py` | реэкспорт публичных классов |
| `app/schemas/common.py` | валюта, content_hash, пагинация, `VacancySort`, конверт ошибки |
| `app/schemas/normalized.py` | `NormalizedVacancy` — контракт публикации |
| `app/schemas/vacancies.py` | карточка, деталь, фильтры п. 5.5, action, meta |
| `app/schemas/resumes.py` | CRUD резюме и вложенные секции |
| `app/schemas/scoring.py` | форма оценки п. 5.4 и `MatchDetails` п. 5.6 |
| `app/schemas/recommendations.py` | query `resume_id` и плоская карточка + score |
| `app/schemas/ai.py` | запросы generate/tailor и черновик LLM |
| `app/schemas/sources.py` | список источников и `ParseRunRead` |
| `tests/test_schemas.py` | 22 офлайн-теста валидации |

### Подтверждено исполнением

- `ruff check`, `ruff format --check`, `mypy app` — чисто (33 файла).
- `pytest` — 73 passed, 2 deselected (integration).
- OpenAPI по-прежнему только `/health`: роутеры вакансий и резюме пустые, `GET /api/v1/vacancies` → 404 с конвертом ошибок.

### Принятые допущения этапа 3

| # | Допущение | Где |
|---|---|---|
| 1 | `NormalizedVacancy` описывает публикацию, не канон: `content_hash` — идентичность текста, `dedup_key` в схему не входит | `app/schemas/normalized.py` |
| 2 | Публичный Read канона без `content_hash` / `external_id` / `raw_payload` / `description_raw`; краткий список публикаций тоже без `raw_payload` | `app/schemas/vacancies.py` |
| 3 | `exclude_hidden` по умолчанию `True` | `VacancyListQuery` |
| 4 | Рекомендации без пагинации: ответ `{items: [...]}` | `app/schemas/recommendations.py` |
| 5 | `SourceListItem` без `config` — селекторы и каналы не отдаются в списке | `app/schemas/sources.py` |
| 6 | `ResumeRead.score_details` — свободный `dict` (зеркало JSONB); строгая форма только у `ResumeScoreResponse` | `app/schemas/resumes.py`, `scoring.py` |
| 7 | `ResumeContacts` — фиксированные ключи (`email`, `phone`, `telegram`, `linkedin`, `github`, `website`), лишние режет `extra=forbid` и на Read | `app/schemas/resumes.py` |
| 8 | Пустой `title=""` допустим: обязательное поле раздела 3 означает «ключ есть», а не «строка непустая» — иначе `parse_quality=partial` без заголовка не пройти схему | `NormalizedVacancy` |

### Незакрытые замечания этапа 3 (не блокируют)

- Навыки вакансии в `NormalizedVacancy` не приводятся к lowercase — это нормализатор, этап 4. На навыках резюме lowercase уже проверяется.
- Потолки `max_points` матчинга (45/20/15/12/8) в схеме не зафиксированы жёстко: числа считает этап 6.
- «Не в будущем» сравнивается с `datetime.now(tz=UTC).date()`, не с `date.today()` (ruff DTZ011).

---

## Этап 4 — `services/normalizer.py` + запись в БД (`services/ingest.py`) + тесты

**Статус:** `done`. По решению пользователя в этап включена запись в БД: чистые функции
нормализатора плюс `ingest.py` с upsert канона и публикаций. Seed (этап 7) и парсеры (этап 11)
переиспользуют эту связку. Проверки закрытия: `determinism-checker` — блокеров нет;
`verifier` — блокеров нет. Это после двух раундов исправлений ложных навыков: сначала
`cv`/`rest`/`go`/`swift` и т.п. из обычных слов, затем пропавший `Rails`.

### Созданные и изменённые файлы

| Файл | Назначение |
|---|---|
| `app/data/skills.json` | 133 канона навыков с синонимами, `text_extraction_exclude`, `text_extraction_case_sensitive` |
| `app/data/vocab.json` | города и страны, формат работы, тип занятости, релокация, грейды |
| `app/utils/text.py` | `fold`, `unify_dashes`, `collapse_spaces`, `remove_emoji`, `fold_case_keep_length` |
| `app/utils/skills_dict.py` | `SkillsDictionary` (frozen, `MappingProxyType`, `lru_cache`), сборка регулярок по словарю |
| `app/utils/vocab.py` | загрузка `vocab.json` в неизменяемые структуры |
| `app/services/__init__.py` | пакет сервисов |
| `app/services/normalizer.py` | `RawVacancy` → `NormalizedVacancy`: зарплата, навыки, уровень, стаж, описание, формат, `dedup_key`, `content_hash`, выбор победителя |
| `app/services/ingest.py` | `ingest_vacancy` / `ingest_batch`: `ON CONFLICT (dedup_key)`, `FOR UPDATE`, savepoint на запись, 6 статусов `IngestStatus` |
| `tests/factories.py` | фабрики `RawVacancy` / `NormalizedVacancy` |
| `tests/test_normalizer_{salary,text,skills,dedup,build}.py`, `tests/test_dictionaries.py` | офлайн-тесты нормализатора и словарей |
| `tests/integration/test_ingest.py` | 13 сценариев записи: склейка, повтор, правка, понижение победителя, порядок |
| `tests/integration/conftest.py` | фикстура `db_session`: внешняя транзакция + `create_savepoint`, откат после теста |
| `pyproject.toml` | `[tool.coverage.run] concurrency = ["greenlet", "thread"]` — иначе async SQLAlchemy занижает покрытие |
| `.cursor/skills/normalizer-rules/SKILL.md` | синхронизирован с фактическими правилами |

### Подтверждено исполнением

- `ruff check`, `ruff format --check`, `mypy app` — чисто (39 файлов в `app`).
- `pytest` — 303 passed, 15 deselected; покрытие `normalizer.py` 100%, `skills_dict.py` 98%, `text.py` 100%, `ingest.py` 99%.
- `pytest -m integration` — 15 passed (только `vacancies_test`, рабочая БД не тронута).
- Детерминизм: при `PYTHONHASHSEED=0` и `2147483647` `model_dump` побайтно совпадает; перестановки ключей `skills.json` дают те же навыки; 6 перестановок порядка трёх публикаций дают один и тот же канон; `last_seen_at` не убывает.
- Эталонный ключ: `яндекс|senior python developer|москва` → `1cf3ecb5…f1f69b`.
- Образ api загружает JSON-словари (214 синонимов).

### Принятые допущения этапа 4 (в коде помечены `# TODO:`)

| # | Допущение |
|---|---|
| 1 | Сумма есть, период не указан → month |
| 2 | Одно число без «от/до» → min = max |
| 3 | Валюта без символа → None; RUB только при «т.р.»/«тр» |
| 4 | Сумма больше int4 → вся зарплата None |
| 5 | Стаж → уровень: ≤1 junior, ≤3 middle, ≤6 senior, >6 lead; intern из стажа не выводится |
| 6 | Несколько грейдов в заголовке → младший |
| 7 | Грейд ищется только в заголовке |
| 8 | Задан `skills_hint` → берётся только он, без слияния с текстом |
| 9 | Кириллические синонимы ловят окончания до 3 букв (финальная гласная синонима отбрасывается); `c`, `r`, `express` в тексте не ищутся |
| 10 | В тексте не ищутся слова из `text_extraction_exclude` (`cv`, `rest`, `shell`, `torch`, `rabbit`, `elastic`): в обычном тексте это не навыки; `REST API`, `PyTorch`, `RabbitMQ` и т.п. ловятся полными синонимами |
| 11 | `Go`, `GO`, `Swift`, `Rust`, `Spring`, `Gin`, `Helm`, `Excel`, `REST`, `Rails` ищутся только в точном регистре; английское предложение, начинающееся с «Go …», даст ложный `go` |
| 12 | Хештеги сопоставляются с синонимом целиком (`#rails` → ruby on rails, `#python_developer` → ничего) и уважают exclude |
| 13 | Многословные синонимы совпадают через `\s+`; кавычки в названии компании → пробел |
| 14 | Эмодзи в заголовке для ключа удаляются по всей строке; пунктуация — только по краям, `+` и `#` сохраняются |
| 15 | `|` внутри компонент `dedup_key` → пробел |
| 16 | `content_hash` = sha256 JSON-массива `[title, company or "", description_clean]` |
| 17 | `full` ⇔ непустые title и description_clean и задана company |
| 18 | languages, education_required и город из текста не извлекаются |
| 19 | Приоритет формата работы и занятости — порядок в `vocab.json`; релокация только True/None |
| 20 | Заголовок/компания/город обрезаются до 500/255/100 символов |
| 21 | Период зарплаты — самое раннее упоминание; тире в стаже унифицируются |
| 22 | Правка со сменой `dedup_key` или коллизией `content_hash` → только `last_seen_at` (`POSTING_EDIT_IGNORED`), без переноса между канонами |
| 23 | Понижение отредактированного победителя → канон перенормализуется из сохранённой публикации нового победителя; явные структурные поля источника теряются |
| 24 | Гонка двух воркеров по одному `(source, external_id)` не закрыта: IntegrityError уходит в ошибки батча; по одному RQ-заданию на источник. Гонка по `dedup_key` закрыта `ON CONFLICT` + `FOR UPDATE` |
| 25 | `ingest` не коммитит — коммит делает вызывающий (seed, RQ-задача) |
| 26 | `ingest` не перенормализует переданный `NormalizedVacancy` |

### Незакрытые замечания этапа 4 (не блокируют)

- `description_clean` не вырезает HTML-теги — это зона HTML-парсера (этап 11).
- В отображаемых title/company сохраняются эмодзи и правовые формы («ООО»); для ключа они чистятся.
- Экзотические ложные навыки остаются: «500 ml» → machine learning, «git the file» → git, строчное «rails» в тексте не ловится.
- PK — `uuid4`, порядок строк в БД не детерминирован; на канон это не влияет.

---

## Этап 5 — CRUD API резюме и вакансий

**Статус:** `done`. Проверка закрытия: `verifier` — блокеров нет. Проверены живые запросы
к API на `vacancies_test` и пересборка `docker compose up -d --build` с GET-запросами к рабочей БД.
Остальные проверки не требовались: нормализатор, матчинг, адаптеры, парсеры и фронтенд
не менялись.

**Решения пользователя на этом этапе:**
- Фильтра `skills[]` в поиске и `top_skills` в `filters/meta` нет — отклонение от п. 5.5 и п. 6 ТЗ. Навыки пользователя учитываются через резюме в подборе (этап 6).
- Зарплата: `salary_min` без валюты фильтрует по всем валютам, включая NULL; валюта не додумывается.
- `saved` и `hidden` взаимоисключающие.

### Эндпоинты

- **Резюме:** `GET/POST /api/v1/resumes`, `GET/PATCH/DELETE /api/v1/resumes/{id}`, `POST /api/v1/resumes/{id}/duplicate`.
- **Вакансии:**
  - `GET /api/v1/vacancies`;
  - `GET /api/v1/vacancies/filters/meta`;
  - `GET /api/v1/vacancies/{id}`;
  - `POST /api/v1/vacancies/{id}/action`;
  - `DELETE /api/v1/vacancies/{id}/action/{action}`.

### Созданные и изменённые файлы

| Файл | Назначение |
|---|---|
| `app/api/deps.py` | `get_current_user_id` → `DEMO_USER_ID`, `CurrentUserDep` |
| `app/services/resumes.py` | CRUD, дублирование, семантика `is_primary`, замена секций, канонизация навыков, сброс `score` и `vacancy_matches` |
| `app/services/vacancy_filters.py` | чистые построители условий, FTS и сортировок |
| `app/services/vacancies.py` | лента (3 SQL-запроса на страницу), деталь, `filters/meta` |
| `app/services/user_actions.py` | идемпотентные действия, `saved` и `hidden` снимают друг друга |
| `app/api/v1/resumes.py`, `app/api/v1/vacancies.py` | тонкие эндпоинты; коммит — в эндпоинте |
| `app/api/errors.py` | `IntegrityError` → 409 `CONFLICT` |
| `app/db/models.py` | только `order_by` у коллекций `Resume` (без миграции) |
| `app/db/session.py` | docstring: сервисы делают только flush, коммит в эндпоинте |
| `app/schemas/resumes.py`, `vacancies.py`, `__init__.py` | длины колонок, запрет `null` в PATCH, уникальность языков, `ResumeListItem`, `saved_only`, `user_actions`, `is_active`, `VacancyUserState`, `currencies`; убраны `skills` и `top_skills` |
| `tests/test_routes_order.py`, `test_vacancy_filters.py`, `test_resume_skills_prepare.py`, `test_error_handlers.py` | офлайн-тесты |
| `tests/integration/test_api_{resumes,vacancies_list,vacancy_detail_actions,filters_meta}.py` | интеграционные тесты API |
| `tests/integration/conftest.py`, `tests/factories.py`, `tests/test_schemas.py` | фикстуры `api_client`/`other_user`, `make_resume_payload`, `ingest_raws` |
| `vacancies-service/README.md` | короткий README сервиса: его копирует `Dockerfile` и читает `pyproject.toml`; основной README перенесён в корень репозитория |

### Подтверждено исполнением

- `ruff check`, `ruff format --check`, `mypy app` — чисто (44 файла в `app`).
- `pytest` — 350 passed; `pytest -m integration` — 115 passed.
- Покрытие: `resumes.py` 99%, `vacancies.py`, `vacancy_filters.py`, `user_actions.py` — 100%.
- Живой сценарий на `vacancies_test`:
  - полный цикл резюме, ни одного сбоя; изменения видны из нового соединения;
  - в любой момент ровно одно основное резюме;
  - поиск с русской морфологией, работа фильтров в сочетании друг с другом.
- Лента из 20 вакансий — 3 SQL-запроса, без N+1.
- `docker compose up -d --build`: `migrate` Exited 0, api healthy. В OpenAPI 11 маршрутов этапа. Ошибки 404/409/422 приходят в едином формате, без SQL и traceback.

### Принятые допущения этапа 5 (в коде помечены `# TODO:`)

| # | Допущение |
|---|---|
| 1 | `user_id` — из `get_current_user_id()` → `DEMO_USER_ID`; auth заменит только эту функцию |
| 2 | Коммит делает эндпоинт, сервисы только flush-ят |
| 3 | Чужое резюме → 404, не 403 |
| 4 | Первое резюме всегда основное; снять флаг с основного нельзя (409) — только назначить другое |
| 5 | При удалении основного основным становится резюме с максимальным `updated_at` |
| 6 | Снятие `is_primary` не меняет `updated_at` соседнего резюме |
| 7 | PATCH секций заменяет список целиком |
| 8 | Навыки резюме канонизируются `normalize_skills`; дубликаты канона схлопываются молча, уровень — первый ненулевой |
| 9 | Любое изменение, кроме `title` и `is_primary`, удаляет `vacancy_matches` и обнуляет `score`; пересчёт — этап 6 |
| 10 | Копия резюме: « (копия)», не основная, `score` копируется, матчи — нет |
| 11 | Порядок секций задаёт `order_by`; колонки позиции нет, пользовательский порядок не сохраняется |
| 12 | Списочные query-параметры — повтором ключа, без `param[]` |
| 13 | Фильтра `skills[]` и `top_skills` нет (решение пользователя, отклонение от п. 5.5 и п. 6 ТЗ) |
| 14 | `salary_min` и `salary_currency` независимы; детектор валюты по стране или компании — позже |
| 15 | Фильтр по сумме: `COALESCE(salary_max, salary_min)`, только `period='month'` |
| 16 | `sort=salary` без валюты сравнивает числа разных валют как есть |
| 17 | `relocation_support=false` означает `IS NOT TRUE` |
| 18 | `published_after` сравнивается с `published_at` канона; время без зоны — UTC |
| 19 | `q` из одних стоп-слов даёт пустую выдачу |
| 20 | `country` — по `lower()`, `city` — через `canonicalize_city` + `lower()` |
| 21 | Новых индексов нет; пересмотреть по `EXPLAIN` на сид-данных этапа 7 |
| 22 | `saved`/`hidden` взаимоисключающие; любое действие снимается через `DELETE .../action/{action}` |
| 23 | Ответ на действие — 200 с полным множеством действий |
| 24 | Деталь отдаёт неактивные и скрытые вакансии; `viewed` автоматически не пишется |
| 25 | `sources` в `filters/meta` — из публикаций, не из таблицы `sources` |
| 26 | `IntegrityError` → 409 `CONFLICT` без имени ограничения в ответе |

### Незакрытые замечания этапа 5 (не блокируют)

- `GET /vacancies/recommended` до этапа 6 отдаёт 422: строка `recommended` не UUID.
- Проверка порядка маршрутов сделана через поведение и разбор `router.py`: в FastAPI 0.141 подключённые роутеры не видны в `app.routes` плоским списком.

---

## Этап 6 — оценка резюме (`resume_scorer`) и подбор вакансий (`matching`)

**Статус:** `done`. Проверки закрытия:
- `determinism-checker` — блокеров нет. Одинаковый результат при `PYTHONHASHSEED=0` и `2147483647` (JSON совпадает побайтно) и при перестановке входных данных.
- `verifier` — блокеров нет. Проверены живые запросы к API на `vacancies_test` и `docker compose up -d --build` с GET-запросами к рабочей БД.

**Решения пользователя на этом этапе:**
- Вакансия без навыков получает нейтральные 22.5 из 45.
- Зарплата: желаемая сумма внутри вилки или вилка выше неё — 15; «от X» без верхней границы при X ниже желаемого — 7; верх вилки ниже желаемого — 0.
- Кандидат хочет удалёнку, а вакансия в офисе — 0 баллов за локацию.
- Оценка резюме пересчитывается автоматически при создании и при каждом содержательном PATCH.
- Критерий навыков по ТЗ: половина баллов — за количество навыков, половина — за совпадение с частотными навыками рынка.

### Эндпоинты

- `POST /api/v1/resumes/{id}/score` — оценка 0–10, 8 критериев, рекомендации.
- `GET /api/v1/vacancies/recommended?resume_id=&exclude_hidden=&limit=` — без `resume_id` берётся основное резюме; если резюме нет, ответ 200 с пустым списком.

### Созданные и изменённые файлы

| Файл | Назначение |
|---|---|
| `app/services/timeline.py` | чистая хронология: интервалы, слияние перекрытий, пробелы больше 6 месяцев, суммарный стаж |
| `app/services/resume_scorer.py` | 8 критериев п. 5.4: доли в `Fraction`, баллы в `Decimal` с округлением до 0.01, `issues` и шаблонные рекомендации |
| `app/services/matching.py` | 0–100 по п. 5.6: навыки 45, уровень 20, зарплата 15, локация 12, свежесть 8; разбивка в `match_details` |
| `app/services/resume_scoring.py` | частотные навыки рынка из БД (FTS по целевой позиции или все вакансии), сохранение оценки без изменения `updated_at` |
| `app/services/recommendations.py` | выдача рекомендаций; кэш `vacancy_matches` пересчитывается при чтении, записываются только изменившиеся строки |
| `app/data/demo_resumes.json` | эталонные резюме strong 9.85 / medium 6.31 / weak 2.91; их переиспользует сид |
| `app/schemas/scoring.py`, `recommendations.py`, `__init__.py` | `ScoreIssue`, `MarketSkillsInfo`, `ResumeScoreDetails`; `reason`/`context` в разбивке матча; `resume_id`/`limit` в запросе рекомендаций |
| `app/services/resumes.py` | `build_resume`; пересчёт оценки при создании и PATCH; параметр `today` |
| `app/services/vacancy_filters.py` | `user_action_exists` стал публичным |
| `app/api/v1/resumes.py`, `app/api/v1/recommendations.py` | эндпоинты `/score` и `/recommended` |
| `app/db/models.py` | только комментарий у `Resume.score` (точность 0.01) |
| `tests/test_timeline.py`, `test_resume_scorer.py`, `test_resume_scorer_reference.py`, `test_matching.py` | офлайн-тесты: таблицы по каждому критерию и компоненте, граничные значения, инварианты |
| `tests/integration/test_api_resume_score.py`, `test_api_recommendations.py` | интеграционные тесты оценки, выдачи и кэша |
| `tests/test_schemas.py`, `test_routes_order.py`, `tests/integration/test_api_resumes.py`, `test_api_vacancy_detail_actions.py` | правки под новое поведение |

### Подтверждено исполнением

- `ruff check`, `ruff format --check`, `mypy app` — чисто (49 файлов в `app`).
- `pytest` — 556 passed; `pytest -m integration` — 141 passed.
- Покрытие `resume_scorer.py`, `matching.py` и `timeline.py` — 100%.
- Повторный `POST /score` даёт тот же балл и побайтно тот же `score_details` (п. 11.5); `updated_at` резюме не меняется.
- Смена основного резюме или `resume_id` меняет порядок ленты (п. 11.3). Повторный GET не трогает `computed_at`.
- `/recommended` — около 6 SQL-запросов на весь ответ, без N+1.

### Принятые допущения этапа 6 (в коде помечены `# TODO:`)

| # | Допущение |
|---|---|
| 1 | Компоненты округляются до 0.01 (ROUND_HALF_UP), итог — точная сумма; `score` хранится с двумя знаками |
| 2 | «Непустое» — `strip() != ""`; контакты заполнены, если есть хотя бы одно значение |
| 3 | Длина описания считается только по `description`; частичные баллы за 100–199 и 1501–3000 символов |
| 4 | Метрика определяется регуляркой (%, кратность, k/млн, число из ≥2 цифр, кроме годов и версий); ложные срабатывания вроде «команда из 12 человек» допустимы |
| 5 | Оптимум навыков 8–15; больше 15 — половина баллов за количество |
| 6 | Рынок навыков: FTS по `target_position`, если найдено ≥5 вакансий, иначе все активные; топ-20. Оценка воспроизводима, пока база вакансий не меняется |
| 7 | Пустой рынок — критерий навыков считается только по количеству |
| 8 | Все пробелы считаются необъяснёнными; хвостовой пробел до «сегодня» учитывается, поэтому без текущей работы оценка со временем снижается |
| 9 | Позиция без `end_date` и без `is_current` — нарушение последовательности, её длина 0 |
| 10 | Зарплата в целях считается заполненной только вместе с валютой; `desired_work_format=unknown` считается заполненным |
| 11 | Рекомендации — русские шаблоны по `issues`; переформулировка через LLM — этап 10 |
| 12 | Уровень резюме: грейд из `target_position`, иначе `level_from_years(стаж // 12)`; без опыта — junior |
| 13 | Вакансия без навыков — 22.5 из 45; уровень `unknown` — 10 из 20 |
| 14 | Зарплата: 15 / 7 / 0 по решению пользователя; разные валюты, разные периоды или нет данных — нейтральные 7 |
| 15 | Желаемая удалёнка против офиса — 0; нет локации у одной из сторон — 6 |
| 16 | `published_at=NULL` — 0 баллов за свежесть; границы 3/7/14/30 дней включительные |
| 17 | Кэш пересчитывается при каждом GET, записываются только изменившиеся строки; `computed_at` — время последнего изменения; GET пишет в БД |
| 18 | Строки матчей неактивных вакансий не удаляются |
| 19 | Рекомендации без пагинации: `limit` по умолчанию 50, максимум 200 |
| 20 | Нет резюме — 200 с пустым списком; при изменении резюме матчи удаляются и строятся заново при следующем GET |

### Незакрытые замечания этапа 6 (не блокируют)

- При росте объёма перейти на инкрементальный пересчёт матчей по событиям (RQ после ingest и после PATCH резюме) и на чтение через индекс `(resume_id, score)`.
- Если по `target_position` найдено меньше 5 вакансий, рынок строится по всем вакансиям (`basis=all_vacancies`). На сиде этапа 7 стоит дать достаточно вакансий по позициям эталонных резюме.

---

## Этап 7 — `scripts/seed.py`

**Статус:** `done`. Проверки закрытия:
- `verifier` — блокеров нет. Независимый прогон тестов, дым-тест CLI и SQL-сверка на `vacancies_test`, живые запросы к API (uvicorn :8011), детерминизм: два сида с одинаковым `--now` дают одинаковый SHA256 снимка. Также `docker compose build api` и `seed --help` в контейнере.
- `mock-mode-auditor` — блокеров нет. В графе импортов сида нет httpx, redis, rq и адаптеров; все ссылки фиктивные; у всех источников `demo: true`; `.env.example` поднимается в mock без ключей.
- `determinism-checker` не требовался: нормализатор, скоринг и матчинг не менялись. Детерминизм сида покрыт тестом снимков.

**Решения пользователя на этом этапе:**
- `--reset` чистит весь домен вакансий (вакансии, публикации, матчи, действия, источники, запуски) и резюме демо-пользователя; нужен `--yes` или ввод имени БД в TTY.
- Компании вымышленные; демо-действия проставляются (saved 3, applied 2, hidden 2, viewed 5).
- Автосида при `compose up` нет — только ручная команда.
- Оценка эталонного резюме вне диапазона — ошибка и откат (код 2).
- `GET /sources` и `/sources/runs` — в начале этапа 8, только чтение.
- Рабочая БД `vacancies` наполняется только после отдельного подтверждения пользователя (сначала `--dry-run`).

### Команды

- Локально из `vacancies-service/`: `.venv\Scripts\python -m scripts.seed [--dry-run] [--reset --yes] [--now ISO]`.
- В Docker: `docker compose exec api python -m scripts.seed`; перед демо — `--reset --yes`, чтобы освежить даты.

### Созданные и изменённые файлы

| Файл | Назначение |
|---|---|
| `app/data/seed_sources.json` | 4 источника (2 telegram, 2 html) с историей из 11 запусков, один `failed` |
| `app/data/seed_vacancies.json` | 72 публикации → 64 канона: 8 склеек (tg↔tg, tg↔html, html↔html), 4 partial-канона |
| `app/services/seed_data.py` | чистый слой: pydantic-модели сида с перекрёстными проверками, `to_raw`, `build_run_batches` |
| `app/services/seed.py` | `run_seed` / `reset_demo_data` / `format_report`; путь `RawVacancy` → `normalize_vacancy` → `ingest_batch`; только flush |
| `scripts/__init__.py`, `scripts/seed.py` | CLI: `--reset`, `--yes`, `--dry-run`, `--now`, `--no-actions`, `--no-score-check`, `--preview`; запрет в `ENVIRONMENT=prod` |
| `Dockerfile`, `docker-compose.yml` | `COPY scripts`, volume `./scripts` у api и worker |
| `pyproject.toml` | ruff `src` включает `scripts`, T201 разрешён в `scripts/*` |
| `README.md` (сервиса) | команды сида |
| `tests/test_seed_data.py`, `tests/test_seed_cli.py` | офлайн: 25 тестов данных (склейки = задуманным офферам, распределения, правила FTS) и 15 тестов CLI |
| `tests/integration/test_seed.py`, `test_seed_api.py`, `conftest.py` | фикстуры `seeded` и `no_app_engine`; счётчики, оценки, идемпотентность, reset, снимок, API и фильтры на сиде |

### Подтверждено исполнением

- `ruff check`, `ruff format --check`, `mypy app scripts` — чисто (53 файла).
- `pytest` — 596 passed; `pytest -m integration` — 155 passed.
- Сид: 4 источника, 11 запусков (найдено 103 публикации, новых 72), 64 вакансии, 8 склеек, 4 partial, 12 действий.
- Запуски: `tg_it_jobs` 7/7, 6/6, 17/4; `tg_relocate_remote` 11/11, 7/7, 18/0; `html_careerhub` 10/10, 8/8; `html_jobboard` 12/12, 7/7, failed 0/0 с `last_error`.
- Оценки при фиксированном и реальном `now`: strong 10.0 (`target_position`, основное), medium 6.31 (`target_position`), weak 2.91 (`all_vacancies`).
- Рекомендации: выдачи трёх резюме различаются; top-5 strong — python-вакансии; top-5 weak — удалёнка; top-1 medium — Fullstack (Django + React).
- CLI: `--dry-run` ничего не пишет; повтор идемпотентен; `--reset` без `--yes` без TTY и `ENVIRONMENT=prod` — код 3 до соединения; `--reset --yes` пересоздаёт данные.

### Принятые допущения этапа 7 (в коде помечены `# TODO:`)

| # | Допущение |
|---|---|
| 1 | Возраст публикаций считается от `now` запуска; повторный сид без `--reset` даты не освежает (ingest не меняет `published_at`) |
| 2 | Единица идемпотентности — источник: существующий `slug` пропускается вместе с запусками и публикациями |
| 3 | Эталонное резюме опознаётся по `title` у демо-пользователя |
| 4 | Действия сидируются, только если у пользователя нет ни одного действия |
| 5 | `--reset` чистит домен вакансий для всех пользователей, резюме — только демо-пользователя |
| 6 | В `ENVIRONMENT=prod` сид запрещён целиком, флага обхода нет |
| 7 | Оценка вне диапазона — ошибка и откат (код 2); проверяются только резюме, созданные в этом запуске |
| 8 | Время запусков синтетическое, но `items_found`/`items_new` — фактический результат `ingest_batch`; `resee_previous` повторно подаёт прошлые публикации источника |
| 9 | `last_run_at` источника — начало его последнего запуска |
| 10 | Telegram-записи без структурных полей (title/company/city заданы явно, как от парсера), html-записи со структурными |
| 11 | `raw_payload` сида имитирует формат `fetch_raw` этапа 11 |
| 12 | `vacancy_matches` заранее не считаются; превью в отчёте идёт через `get_recommendations` |
| 13 | `--now` обязан быть с таймзоной и не в будущем |

Вымышленные компании, ссылки `example.com`/`example.org`/`t.me/demo_…` и `demo: true` у источников зафиксированы в JSON-данных.

### Наполнение рабочей БД `vacancies`

- 2026-09-30, с подтверждения пользователя: `docker compose exec api python -m scripts.seed`, `now = 2026-09-29T21:32:04+00:00` (перед этим `--dry-run` показал те же числа и ничего не записал).
- Итог: 4 источника, 11 запусков, 64 вакансии (8 склеек, 4 partial), 3 резюме (strong 10.0 — основное, medium 6.31, weak 2.91), 12 действий.
- API: `GET /vacancies` total 62 (64 со скрытыми), `/resumes` 3, `/recommended` top-3 — Senior Python Developer 100/95/90, `filters/meta` 4 источника, 11 стран, валюты EUR/GBP/KZT/RUB/USD.

### Незакрытые замечания этапа 7 (не блокируют)

- Отчёт CLI в консоли Windows (cp1251) показывает кириллицу и эмодзи как mojibake/`\U…` (`errors="backslashreplace"`); данные в БД и API корректны. В Docker проблемы нет.
- Оценка strong 10.0, а не ≈9.85 из плана: рынок сида покрывает все 11 навыков резюме, это внутри диапазона.
- Отдельного теста на `config.demo is True` у источников сида нет (проверено аудитом вручную).
- Индексы по `EXPLAIN` (допущение 21 этапа 5) на 64 строках не показательны — пересмотреть на реальных объёмах после этапа 11.
- В данных поправлен текст оффера «Верстальщик на проект» (добавлены Figma/SCSS/Webpack/Git), чтобы top-1 для medium был Fullstack, а не partial-вёрстка.

---

## Этап 8 — демо-фронтенд (4 экрана) на сид-данных

**Статус:** `done`. Проверки закрытия:
- `visual-reviewer` — блокеров нет (после правок: текст ≥13px, отступы сетки кратны 4px, подписи радара 13px).
- `verifier` — блокеров нет. Бэкенд: ruff/format/mypy, pytest 609, integration 168. Фронтенд: typecheck, lint, vitest 85, build. Живые GET к API и Playwright на `:5173`.
- `mock-mode-auditor` — блокеров нет. Нет CDN и внешних шрифтов; API только через `/api`; кнопки ИИ и «Запустить» ничего не отправляют.
- `determinism-checker` (после 8a) — блокеров нет: порядок `sort=match` совпадает с `/recommended` при разных `PYTHONHASHSEED`.

**Решения пользователя:**
- Процент соответствия — `GET /vacancies?resume_id=` и `sort=match` в одной ленте с фильтрами.
- Селектор резюме не меняет `is_primary`. Черновик редактора только в `localStorage`; на сервер — по «Сохранить».
- `viewed` при открытии drawer. Кнопки ИИ и «Запустить» видны, но заблокированы до этапов 10 и 11.
- На карточке все источники. Из `config` наружу только канал или URL (`location`).
- Пагинация по 20. Скрытые — переключателем. Skeleton при любой смене ленты.
- Коммиты по подэтапам 8a–8c; 8d — в коммите закрытия этапа.

### Экраны

- «Вакансии» — фильтры п. 5.5 (без навыков), сортировка по соответствию, drawer с разбивкой матча, модалка фильтров ниже 768px.
- «Мои резюме» — карточки, дублирование, удаление, назначение основного.
- «Редактор» — секции, локальный черновик с восстановлением, радар по 8 критериям, оценка после сохранения.
- «Источники» — 4 источника сида, история 11 запусков, у `html_jobboard` статус ошибки.

### Подтверждено исполнением

- `/sources`: 4 источника, location `@demo_it_jobs`, `@demo_relocate_jobs`, `careers.example.com`, `jobs.example.org`; `html_jobboard` failed 0/0; `/sources/runs` — 11; ключа `config` нет.
- Лента с `sort=match` совпадает с `/recommended`; без `resume_id` сортировка по соответствию даёт 422.
- Смена резюме меняет порядок. Фильтр remote + middle даёт непустую выдачу. Три резюме на месте (10.0 / 6.31 / 2.91).
- Сайт: http://localhost:5173.

### Принятые допущения этапа 8

| # | Допущение |
|---|---|
| 1 | `sort=match` считает матчи по всей отфильтрованной выборке; GET с `resume_id` пишет кэш |
| 2 | `sort=match` без `resume_id` — 422, основное резюме само не подставляется |
| 3 | Из `config` наружу только `channel` или `url` |
| 4 | Активное резюме ленты — выбор в UI, не `is_primary` |
| 5 | Skeleton при любой смене ключа ленты |
| 6 | Черновик резюме в `localStorage`; PATCH только по кнопке |
| 7 | Радар нормирует критерии в проценты от веса |
| 8 | ИИ-генерация и ручной запуск парсера выключены флагами `FEATURES` |
| 9 | `viewed` пишется один раз на id за сессию |
| 10 | Пороги цвета матча 75/50, оценки резюме 8/6.5 |
| 11 | Заголовок страницы 30/34px — исключение; eyebrow PageHeader — 11px |
| 12 | Типы API генерируются из OpenAPI (`npm run gen:api`) и коммитятся |

### Незакрытые замечания этапа 8 (не блокируют)

- На ширине 768px часть колонок таблицы источников уходит в горизонтальный скролл.
- Кнопка «Запустить» в светлой теме выглядит почти активной, хотя она disabled.
- При ошибке загрузки источников плитки сводки показывают 0, а не «—».

---

## Этап 9 — адаптеры LLM и profile с mock-реализациями

**Статус:** `done`. Проверки закрытия:
- `mock-mode-auditor` — блокеров нет. Mock не открывает сеть и не читает ключ; real только при `*_mode=real`; SDK openai/anthropic нет.
- `verifier` — блокеров нет. 26 тестов адаптеров, ruff и mypy чистые. Эндпоинтов generate/tailor нет. `resume_scorer.py`, `matching.py`, `normalizer.py` не менялись.

### Созданные и изменённые файлы

| Файл | Назначение |
|---|---|
| `app/schemas/adapters.py` | `ProfileSnapshot`, `CriterionFailure`, `VacancyEnrichmentInput`, `VacancyEnrichment` |
| `app/adapters/fixtures.py` | константные фикстуры mock |
| `app/adapters/llm.py` | `LLMAdapter`: mock и httpx-real, повтор невалидного JSON |
| `app/adapters/profile.py` | `ProfileAdapter`: mock и `GET /users/{id}` |
| `app/adapters/__init__.py` | пакет |
| `app/api/deps.py` | `LLMAdapterDep`, `ProfileAdapterDep` |
| `app/schemas/__init__.py` | реэкспорт DTO |
| `app/config.py`, `.env.example` | комментарий: пустой ключ не валит старт |
| `tests/test_adapters_llm.py`, `test_adapters_profile.py`, `test_adapter_deps.py` | офлайн-тесты, real через `MockTransport` |

Роуты адаптеры не вызывают. Фронтенд на этом этапе не менялся.

### Принятые допущения этапа 9

| # | Допущение |
|---|---|
| 1 | Real без ключа или URL бросает `ExternalServiceError` в методе адаптера; `model_validator` на старте не делается |
| 2 | `LLM_PROVIDER=anthropic` не вызывает Messages API: без `LLM_BASE_URL` вызов падает, с URL идёт OpenAI-compatible `/chat/completions` |
| 3 | Profile-core: `GET {PROFILE_SERVICE_URL}/users/{user_id}` без авторизации; лишние поля корня игнорируются |
| 4 | Mock не разбирает `raw_text` и `description_raw`; фикстуры — константы Python |
| 5 | Повтор только для невалидного JSON или схемы; HTTP и таймаут не повторяются |
| 6 | `content` чата обязан быть строкой; массив контента не поддерживается |
| 7 | `tailor_resume` есть в Protocol, HTTP-эндпоинт — этап 10; парсеры обогащение не вызывают |
| 8 | Экран «Профиль» по-прежнему копирует поля резюме; адаптер эти поля только умеет отдать |

---

## Этап 10 — ИИ-функции (генерация, tailor, формулировка рекомендаций)

**Статус:** `done`. Проверки закрытия:
- `mock-mode-auditor` — блокеров нет. Mock не открывает сеть; сид всегда передаёт `MockLLMAdapter`.
- `visual-reviewer` — блокеров нет. Кнопка генерации активна, плашки «этап 10» нет.
- `verifier` — блокеров нет. Generate 201 с `origin=generated`, tailor не меняет `origin` и `is_primary`, ошибка формулировки оставляет шаблоны и 200.

### Созданные и изменённые файлы

| Файл | Назначение |
|---|---|
| `app/services/resume_ai.py` | сохранить черновик generate и результат tailor |
| `app/api/v1/resumes.py` | `POST /generate` до `/{id}`, `POST /{id}/tailor` |
| `app/services/resume_scoring.py` | подмена текстов рекомендаций после `score_resume` |
| `app/services/resumes.py` | `llm` прокинут в create/update |
| `app/adapters/llm.py` | mock-фразы = шаблоны скорера; промпт tailor про акценты опыта |
| `app/services/seed.py` | сид всегда на `MockLLMAdapter` |
| `frontend/.../GenerateModal.tsx`, `features.ts`, `api/resumes.ts` | модалка вызывает generate и открывает редактор |
| `tests/test_resume_phrases.py`, `tests/integration/test_api_resume_ai.py` | фразы и HTTP-контракт |

`resume_scorer.py` не менялся: числа по-прежнему считает код.

### Подтверждено исполнением

- Модалка на http://localhost:5173: ввод текста и позиции «Проверка генерации» → 201, `origin=generated`, заголовок и поле названия совпали. Созданное резюме удалено (204), в рабочей базе его нет.

### Принятые допущения этапа 10

| # | Допущение |
|---|---|
| 1 | Сид всегда получает `MockLLMAdapter`, даже при `llm_mode=real` |
| 2 | Если шаблон рекомендации вернул пусто, mock отдаёт пустую строку |
| 3 | Несовпадение длины фраз оставляет шаблонные тексты |
| 4 | Черновик, не прошедший `ResumeCreate` / `ResumeUpdate`, — 502 `LLM_RESPONSE_INVALID` |
| 5 | Лимит текста 10 000 символов только в модалке |
| 6 | Вакансии общие: 404 у tailor только если id нет |
| 7 | Tailor не меняет `is_primary`; mock переписывает только summary |
| 8 | `schema.gen.ts` на этом этапе не обновлялся |

---

## Этап 11 — парсеры (telegram → html) + RQ-задачи + планировщик

**Статус:** `done`. Проверки закрытия:
- `parser-extensibility-checker` — блокеров нет. Новый HTML-сайт — строка `sources.config`, без правки Python.
- `mock-mode-auditor` — блокеров нет. `PARSERS_ENABLED=false` не ходит наружу; демо-источник — 409 `DEMO_SOURCE`.
- `visual-reviewer` — блокеров нет. Кнопка «Запустить» активна, текст 409 по-русски по `code`. Смотрел код, браузер не открывал.
- `verifier` — блокеров нет. ruff, mypy, pytest 683, фронтенд 92 теста и typecheck.

### Созданные и изменённые файлы

| Файл | Назначение |
|---|---|
| `app/parsers/` | база, реестр, config, HTML (selectolax + Playwright) и Telegram (Telethon) |
| `app/services/parsing.py` | прогон: `parse_run`, `normalize_vacancy`, `ingest_batch`, commit |
| `app/tasks/queue.py`, `parse_source.py`, `scheduler.py` | lock, RQ-задача, отдельный планировщик |
| `app/api/v1/sources.py`, `app/schemas/sources.py`, `app/utils/errors.py` | `POST /sources/{id}/run` → 202 или 409 |
| `app/tasks/worker.py` | воркер без встроенного планировщика |
| `Dockerfile`, `docker-compose.yml`, `.env.example`, `pyproject.toml` | Chromium в образе, сервис `scheduler`, пин `rq<2` |
| `tests/test_*parser*.py`, `test_parsing_schedule.py`, `test_source_run_api.py`, `tests/integration/test_parse_job.py` | офлайн-тесты и интеграция прогона |
| `frontend/.../SourcesTable.tsx`, `run-error.ts`, `features.ts`, `api/sources.ts` | кнопка «Запустить» и русские тексты 409 |

`normalizer.py`, `matching.py`, `resume_scorer.py` и сид не менялись.

### Подтверждено исполнением

- `ruff check`, `ruff format --check`, `mypy app`, `pytest` (683 passed, интеграция deselected).
- Фронтенд: `npm test` (92), `npm run typecheck`.
- `pytest -m integration tests/integration/test_parse_job.py` не запускался: Postgres на `127.0.0.1:5433` соединения не принимает.
- Экран источников в браузере не прокликан: дев-сервер для проверки не поднимался.

### Принятые допущения этапа 11

| # | Допущение |
|---|---|
| 1 | Остаёмся на `rq<2` и `rq-scheduler` 0.13; воркер на `Worker.work` не переписываем |
| 2 | `to_normalized` возвращает `RawVacancy`, не `NormalizedVacancy` из ТЗ 5.1 |
| 3 | Новый HTML-сайт — строка `sources.config`; новый тип — класс и `register` |
| 4 | LLM-обогащение partial не вызывается |
| 5 | CSS разбирает selectolax после `page.content()`; `@attr` — по последнему `@` |
| 6 | robots.txt не 200 и не 404 — прогон failed; 404 — обход можно |
| 7 | Оба ключа пагинации сразу: побеждает `next_selector` |
| 8 | Нет url у карточки: `external_id` = `{page_url}#{index}` |
| 9 | Ошибки отдельных публикаций в `ingest_batch` не переводят run в `failed` |
| 10 | Первый плановый запуск через один интервал; смена интервала — рестарт scheduler |
| 11 | Lock живёт до `rq_default_timeout`, если воркер умер |
| 12 | Нет интерактивного логина Telegram; нет файла сессии — failed `parse_run` |
| 13 | Chromium с `--no-sandbox` из-за non-root в образе |
| 14 | `demo is True` проверяется раньше `parsers_enabled`, ответ `DEMO_SOURCE` |

---

## Этап 12 — README с инструкцией запуска

**Статус:** `done`. Проверки закрытия:
- `verifier` — блокеров нет. Команды и порты сходятся с Compose, `.env.example` и сидом.
- `visual-reviewer`, `mock-mode-auditor`, `parser-extensibility-checker`, `determinism-checker` не запускались: код не менялся.

### Изменённые файлы

| Файл | Назначение |
|---|---|
| `README.md` | запуск демо: `.env`, `docker compose up`, сид |
| `vacancies-service/README.md` | локальное окружение, проверки, очередь |

### Принятые допущения этапа 12

| # | Допущение |
|---|---|
| 1 | В инструкции команда `docker compose` (Compose v2), хотя ТЗ пишет `docker-compose` |
| 2 | `--reset --yes` перед демо нужен, потому что повторный сид без сброса не обновляет даты публикаций |

---

## Долги, запланированные на конкретные этапы

Найдены проверками на этапах 1–2, исправлять нужно там, где появится соответствующий код.

### Этап 2 (модели и Alembic) — закрыт

- `Base` / `DeclarativeBase`, `alembic.ini`, `migrations/env.py`, COPY и volume — сделано.

### Этап 4 (нормализатор) — закрыт

- `dedup_key`, консервативный заголовок, выбор победителя, MIN/MAX дат, lowercase и синонимы навыков — сделано.

### Этап 6 (скоринг и матчинг) — закрыт

- Пересчёт оценки в `_invalidate_derived`, `user_actions` и `exclude_hidden` в `/recommended` — сделано.

### Этап 7 (seed) — закрыт

- Публикации и каноны через `normalize_vacancy` → `ingest_batch`, склейки из разных источников, резюме из `demo_resumes.json`, проверка диапазонов оценок, ≥5 вакансий по FTS для strong — сделано.

### Этап 8 (фронтенд) — закрыт

- Read-only `/sources` и `/sources/runs`, четыре экрана, токены, примитивы, stagger 30 мс, модалка фильтров, состояния skeleton/empty/error — сделано.

### Этап 9 (адаптеры LLM и profile) — закрыт

- Mock не читает ключ и не создаёт HTTP-клиент. Real выбирается только при `*_mode=real`, через `Depends`.
- Пустой ключ или URL не валит старт: `ExternalServiceError` бросается в методе адаптера. `model_validator` на `Settings` сознательно не добавлен.
- Повтор невалидного JSON — одна дополнительная попытка внутри адаптера. Эндпоинты generate/tailor — этап 10.

### Этап 10 (ИИ-функции) — закрыт

- `POST /resumes/generate` и `POST /resumes/{id}/tailor` ходят в LLM-адаптер. В mock сети нет.
- Числа скора считает код. Ошибка формулировки оставляет шаблонные тексты.
- `FEATURES.aiGenerate` включён, модалка создаёт черновик и открывает его редактор.

### Этап 11 (парсеры) — закрыт

- Playwright Chromium ставится в `python:3.12-slim` через `playwright install --with-deps`. `PARSERS_ENABLED=false` в демо.
- Пин `rq<2` и `rq-scheduler` 0.13 оставлен. `to_normalized` → `RawVacancy` → `normalize_vacancy` → `ingest_batch`.
- HTML вырезает теги сам. `@attr` по последнему `@`. Один RQ-job на источник. Демо — 409 `DEMO_SOURCE`. Счётчики — из `ingest_batch`.
- `FEATURES.runSource` включён. Гонка `(source, external_id)` в БД по-прежнему не закрыта.

### Этап 12 (README) — закрыт

- Корень: `.env` без правок, `docker compose up`, затем сид. Перед демо `--reset --yes`, предпросмотр `--dry-run`.
- `vacancies-service/README.md`: Python 3.12, ruff/mypy/pytest, фронтенд, воркер только в Docker/Linux.

### После этапов 11 и 12

- Генерация через готовую модель и варианты развёртывания — `docs/llm-generation.md`. Сейчас не делать: демо остаётся на `LLM_MODE=mock`.
