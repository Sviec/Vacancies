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

## Долги, запланированные на конкретные этапы

Найдены проверками на этапах 1–2, исправлять нужно там, где появится соответствующий код.

### Этап 2 (модели и Alembic) — закрыт

- `Base` / `DeclarativeBase`, `alembic.ini`, `migrations/env.py`, COPY и volume — сделано.

### Этап 4 (нормализатор) — закрыт

- `dedup_key`, консервативный заголовок, выбор победителя, MIN/MAX дат, lowercase и синонимы навыков — сделано.

### Этап 6 (скоринг и матчинг)

- Заменить тело `_invalidate_derived` в `services/resumes.py` на пересчёт `score` и `vacancy_matches`, а не только их очистку.
- `/vacancies/recommended` должен заполнять `user_actions` у `RecommendedVacancyItem` и уважать `exclude_hidden`.
- Навыки вакансии в ленте не фильтруются — совпадение навыков резюме учитывает только матчинг (45 баллов).

### Этап 7 (seed)

- Сид должен создавать и `vacancies`, и `vacancy_postings` (минимум два источника на один канонический оффер — для UI «источники»).
- `contacts` в сиде — только ключи `ResumeContacts`; лишний ключ уронит `ResumeRead`.
- Вакансии строить через `RawVacancy` → `normalize_vacancy` → `ingest_batch`, не вставлять строки в таблицы напрямую; коммит — в самом сиде (`ingest` не коммитит).
- Для склейки в UI давать одинаковую тройку company/title/city в разных источниках с разными текстами.

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
- Карточка вакансии: список источников из `vacancy_postings`, не одно поле `source`.
- В фильтрах нет выбора навыков (решение пользователя на этапе 5); валюта — необязательный выбор рядом с суммой, список из `filters/meta.currencies`.
- Списочные параметры запроса отправлять повтором ключа (`work_format=remote&work_format=hybrid`), не `work_format[]`.
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
- `to_normalized` парсера возвращает `RawVacancy`, дальше общий `normalize_vacancy` + `ingest_batch`; RQ-задача коммитит сама.
- HTML-парсер должен сам вырезать теги до `description_raw`: `clean_description` убирает только markdown.
- По одному RQ-заданию на источник (гонка по `(source, external_id)` не закрыта, допущение 24 этапа 4).
