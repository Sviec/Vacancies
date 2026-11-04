# Прогресс реализации vacancies-service

Этапы 1–12 — порядок раздела 12 ТЗ, этапы 13+ — [docs/roadmap.md](docs/roadmap.md).
Статус: `not started` / `in progress` / `done`. Обновляется агентом по
завершении этапа (см. `.cursor/rules/workflow.mdc`).

Код сервиса — в `vacancies-service/`. Папка `replit_template/` — read-only
визуальный референс (макеты `career-service`), в git не версионируется.

## Статус

| # | Этап | Статус |
|---|---|---|
| 1 | Каркас проекта, конфиг, docker-compose, подключение БД | done |
| 2 | Модели SQLAlchemy + миграции Alembic | done |
| 3 | Pydantic-схемы, включая `NormalizedVacancy` | done |
| 4 | `services/normalizer.py` + запись в БД + тесты | done |
| 5 | CRUD API резюме и вакансий | done |
| 6 | `resume_scorer.py` + `matching.py` + тесты | done |
| 7 | `scripts/seed.py` | done |
| 8 | Демо-фронтенд (4 экрана) на сид-данных | done |
| 9 | Адаптеры LLM/profile с mock-реализациями | done |
| 10 | ИИ-функции (генерация, tailor, формулировка рекомендаций) | done |
| 11 | Парсеры (telegram → html) + RQ-задачи + планировщик | done |
| 12 | README с инструкцией запуска | done |
| 12+ | Вне ТЗ: вход по почте, CI, публикация на маленьком сервере | done |
| 13 | Источник hh.ru через API ([план](docs/hh-api.md)) | in progress |
| 14 | Производительность на реальных объёмах | not started |
| 15 | Управление источниками через API и UI | not started |
| 16 | Парсинг на сервере публикации | not started |
| 17 | Реальная модель и обогащение partial | not started |
| 18 | Мелкий техдолг | not started |

Открытые замечания этапов 1–12 собраны в этап 18 [docs/roadmap.md](docs/roadmap.md).

## Отклонения от ТЗ

Действуют сейчас. Подробности — в допущениях соответствующего этапа.

| Что в ТЗ | Как сделано | Этап |
|---|---|---|
| Без авторизации, `DEMO_USER_ID` (п. 0.2) | Вход по почте и паролю, сессия в httpOnly-куке; сид кладёт резюме учётной записи `--email` | 12+ |
| React 18, Python 3.11+, PostgreSQL 15+ | React 19 + Tailwind 4, Python 3.12, PostgreSQL 16, recharts 3 | 1 |
| Дедупликация по `content_hash` (разд. 3, 4) | Канон `vacancies` по `dedup_key = company + title + city`; `content_hash` — на публикациях `vacancy_postings` | 2 |
| Фильтр `skills[]`, `top_skills` в `filters/meta` (п. 5.5, 6) | Нет; навыки учитываются через резюме в подборе | 5 |
| `to_normalized → NormalizedVacancy` (п. 5.1) | Возвращает `RawVacancy`, дальше общий нормализатор | 11 |
| Новый источник = новый класс | Новый HTML-сайт — строка `sources.config`; класс — только для нового типа | 11 |
| LLM-обогащение partial (п. 5.1) | Не вызывается; запланировано на этап 17 | 11 |
| `docker-compose up` | `docker compose up` (Compose v2) | 12 |

---

## Этап 1 — каркас, конфиг, docker-compose, БД

**Файлы.** Корень: `.gitignore`, `.gitattributes` (LF). Сервис: `pyproject.toml`,
`.env.example`, `Dockerfile`, `.dockerignore`, `docker-compose.yml`,
`app/{__init__,config,main}.py`, `app/api/{health,middleware,errors}.py`,
`app/api/v1/router.py` и роутеры-заглушки, `app/db/{session,redis}.py`,
`app/tasks/worker.py`, `app/utils/{logging,errors}.py`,
`tests/{conftest,test_health,test_config}.py`. Фронтенд: `package.json`,
`vite.config.ts`, `tsconfig*.json`, `index.html`, `Dockerfile`,
`src/{index.css,main.tsx,App.tsx}`, `src/lib/{theme.tsx,api.ts}`,
`src/components/ThemeToggle.tsx`.

**Допущения.**

| # | Допущение |
|---|---|
| 1 | React 19 + Tailwind 4 вместо React 18 — вёрстка из макетов переносится без переписывания |
| 2 | Python 3.12: на 3.14 не гарантированы asyncpg, Telethon, Playwright |
| 3 | `rq<2`, поэтому `rq-scheduler` 0.13.x |
| 4 | `recharts` 3.x: 2.x конфликтует с React 19 |
| 5 | Postgres 16, Node 24 в образе фронтенда |
| 6 | `/health` при деградации — 503 с телом `HealthResponse`, не конверт ошибки |
| 7 | `recommendations.router` подключается раньше `vacancies.router`, иначе `/vacancies/recommended` съест `/vacancies/{id}` |
| 8 | RQ использует `fork`: воркер только в Docker/Linux |
| 9 | ~~CORS с `allow_credentials=False`~~ — заменено на этапе 12+: `True`, сессия в куке |
| 10 | Фронтенд в dev — Vite dev-server; прод — nginx (`Dockerfile.prod`, этап 12+) |
| 11 | Inter не грузится с CDN (офлайн, п. 11.2) — системный стек с Inter первым |
| 12 | Фронтенд ходит по относительным путям через прокси, CORS в браузере не возникает |
| 13 | Тёмная тема реализована; цвета в CSS-переменных `:root` / `.dark` |
| 14 | Зацикленный shimmer `.skeleton` 1.25 с: лимит 300 мс раздела 8 — для разовых переходов |
| 15 | `translateY(-2px)` в `.lift` — не масштабирование, свойств два |
| 16 | Polling в Docker на Windows (`WATCHFILES_FORCE_POLLING`, `VITE_USE_POLLING`) |
| 17 | Порты хоста параметризованы; на машине разработки Postgres на 5433 |

---

## Этап 2 — модели SQLAlchemy и миграции Alembic

**Файлы.** `app/enums.py`, `app/db/base.py`, `app/db/models.py` (12 моделей),
`alembic.ini`, `migrations/{env.py,script.py.mako}`,
`migrations/versions/20260919_2303_ba833660ecb2_initial_schema.py`,
`tests/test_models_metadata.py`, `tests/test_migrations_offline.py`,
`tests/integration/{conftest,test_migration_drift}.py`; сервис `migrate` в compose.

**Допущения.**

| # | Допущение |
|---|---|
| 1 | PK — `UUID` (`uuid4` в Python); `uuid7` в stdlib 3.12 нет |
| 2 | Enum — `VARCHAR` + `CHECK` (`native_enum=False`) |
| 3 | Деньги — `Integer`; риск int4 на экзотических валютах |
| 4 | Отклонение: дедупликация по `company + title + city`, не по `content_hash` |
| 5 | Две таблицы: `vacancies` (канон) и `vacancy_postings` (появление в источнике) |
| 6 | Канон денормализован: поля победителя копируются, без `primary_posting_id` |
| 7 | Победитель: `parse_quality=full`, затем самое длинное описание; поля проигравших не подмешиваются |
| 8 | `dedup_key` — sha256 тройки, считает сервисный слой |
| 9 | Без компании `dedup_key=NULL`, склейки нет; NULL не конфликтуют |
| 10 | Пустой город — пустая третья компонента ключа |
| 11 | Отклонение: UNIQUE `(source, content_hash)` на публикациях |
| 12 | `published_at` канона — MIN по публикациям, `last_seen_at` — MAX |
| 13 | Склейка глобальна во времени, без окна 60 дней (решение пользователя) |
| 14 | Нормализация заголовка консервативная: грейд и скобки сохраняются (решение пользователя) |
| 15 | Операции «разделить вакансию» нет (решение пользователя) |
| 16 | `resumes.contacts` JSONB и `origin` сверх раздела 4 |
| 17 | `vacancies.source` без FK на `sources.slug` |
| 18 | `alembic.ini` в образе через COPY; bind-mount `./migrations` только у `migrate` |

---

## Этап 3 — Pydantic-схемы

**Файлы.** `app/schemas/{__init__,common,normalized,vacancies,resumes,scoring,recommendations,ai,sources}.py`,
`tests/test_schemas.py`.

**Допущения.**

| # | Допущение |
|---|---|
| 1 | `NormalizedVacancy` описывает публикацию; `dedup_key` в схему не входит |
| 2 | Публичный Read канона без `content_hash`, `external_id`, `raw_payload`, `description_raw` |
| 3 | `exclude_hidden` по умолчанию `True` |
| 4 | Рекомендации без пагинации: `{items: [...]}` |
| 5 | `SourceListItem` без `config` |
| 6 | `ResumeRead.score_details` — свободный `dict`; строгая форма только у `ResumeScoreResponse` |
| 7 | `ResumeContacts` — фиксированные ключи, лишние режет `extra=forbid` |
| 8 | Пустой `title=""` допустим, иначе partial без заголовка не пройдёт схему |

---

## Этап 4 — нормализатор, запись в БД, тесты

**Файлы.** `app/data/{skills,vocab}.json`, `app/utils/{text,skills_dict,vocab}.py`,
`app/services/{normalizer,ingest}.py`, `tests/factories.py`,
`tests/test_normalizer_{salary,text,skills,dedup,build}.py`,
`tests/test_dictionaries.py`, `tests/integration/test_ingest.py`,
`.cursor/skills/normalizer-rules/SKILL.md`.

**Допущения** (в коде `# TODO:`).

| # | Допущение |
|---|---|
| 1 | Сумма есть, период не указан → month |
| 2 | Одно число без «от/до» → min = max |
| 3 | Валюта без символа → None; RUB только при «т.р.» / «тр» |
| 4 | Сумма больше int4 → вся зарплата None |
| 5 | Стаж → уровень: ≤1 junior, ≤3 middle, ≤6 senior, >6 lead; intern из стажа не выводится |
| 6 | Несколько грейдов в заголовке → младший; грейд ищется только в заголовке |
| 7 | Задан `skills_hint` → берётся только он, без слияния с текстом; неизвестные навыки остаются lowercase |
| 8 | Кириллические синонимы ловят окончания до 3 букв; `c`, `r`, `express` в тексте не ищутся |
| 9 | `text_extraction_exclude` (`cv`, `rest`, `shell`, `torch`, `rabbit`, `elastic`) в тексте не ищутся |
| 10 | `Go`, `Swift`, `Rust`, `Spring`, `Gin`, `Helm`, `Excel`, `REST`, `Rails` — только в точном регистре |
| 11 | Хештег сопоставляется с синонимом целиком и уважает exclude |
| 12 | Многословные синонимы через `\s+`; кавычки в компании → пробел |
| 13 | Эмодзи в заголовке для ключа удаляются; пунктуация — только по краям, `+` и `#` сохраняются; `|` → пробел |
| 14 | `content_hash` = sha256 JSON `[title, company or "", description_clean]` |
| 15 | `full` ⇔ непустые title и description_clean и задана company |
| 16 | languages, education_required и город из текста не извлекаются |
| 17 | Приоритет формата работы и занятости — порядок в `vocab.json`; релокация только True/None |
| 18 | Заголовок / компания / город обрезаются до 500 / 255 / 100 символов |
| 19 | Период зарплаты — самое раннее упоминание |
| 20 | Правка со сменой `dedup_key` или коллизией `content_hash` → только `last_seen_at` |
| 21 | Понижение победителя → канон перенормализуется из публикации нового победителя |
| 22 | Гонка двух воркеров по `(source, external_id)` не закрыта; по `dedup_key` закрыта `ON CONFLICT` + `FOR UPDATE` |
| 23 | `ingest` не коммитит и не перенормализует переданный `NormalizedVacancy` |
| 24 | `description_clean` HTML-теги не вырезает — это зона парсера |

---

## Этап 5 — CRUD API резюме и вакансий

**Эндпоинты.** `GET/POST /resumes`, `GET/PATCH/DELETE /resumes/{id}`,
`POST /resumes/{id}/duplicate`, `GET /vacancies`, `GET /vacancies/filters/meta`,
`GET /vacancies/{id}`, `POST /vacancies/{id}/action`,
`DELETE /vacancies/{id}/action/{action}`.

**Файлы.** `app/api/deps.py`, `app/services/{resumes,vacancy_filters,vacancies,user_actions}.py`,
`app/api/v1/{resumes,vacancies}.py`, правки `app/api/errors.py`, `app/db/models.py`,
`app/schemas/*`; тесты `tests/test_{routes_order,vacancy_filters,resume_skills_prepare,error_handlers}.py`,
`tests/integration/test_api_{resumes,vacancies_list,vacancy_detail_actions,filters_meta}.py`;
`vacancies-service/README.md` (короткий, его читают `Dockerfile` и `pyproject.toml`).

**Допущения** (в коде `# TODO:`).

| # | Допущение |
|---|---|
| 1 | ~~`user_id` из `DEMO_USER_ID`~~ — заменено на этапе 12+: из сессии, сервисы по-прежнему получают его параметром |
| 2 | Коммит делает эндпоинт, сервисы только flush |
| 3 | Чужое резюме → 404, не 403 |
| 4 | Первое резюме всегда основное; снять флаг с основного нельзя (409) |
| 5 | При удалении основного основным становится резюме с максимальным `updated_at` |
| 6 | Снятие `is_primary` не меняет `updated_at` соседнего резюме |
| 7 | PATCH секций заменяет список целиком |
| 8 | Навыки резюме канонизируются; дубликаты схлопываются, уровень — первый ненулевой |
| 9 | Изменение, кроме `title` и `is_primary`, удаляет `vacancy_matches` и пересчитывает оценку |
| 10 | Копия резюме: « (копия)», не основная, `score` копируется, матчи — нет |
| 11 | Порядок секций — `order_by`, пользовательский порядок не хранится |
| 12 | Списочные query-параметры — повтором ключа |
| 13 | Нет `skills[]` и `top_skills` (решение пользователя) |
| 14 | `salary_min` и `salary_currency` независимы; `salary_min` без валюты — по всем валютам |
| 15 | Фильтр по сумме: `COALESCE(salary_max, salary_min)`, только `period='month'` |
| 16 | `sort=salary` без валюты сравнивает числа разных валют как есть |
| 17 | `relocation_support=false` означает `IS NOT TRUE` |
| 18 | `published_after` — по `published_at` канона; время без зоны — UTC |
| 19 | `q` из одних стоп-слов даёт пустую выдачу |
| 20 | `country` — по `lower()`, `city` — через `canonicalize_city` + `lower()` |
| 21 | Новых индексов нет; пересмотреть по `EXPLAIN` на реальном объёме (этап 14) |
| 22 | `saved` и `hidden` взаимоисключающие (решение пользователя); снятие — `DELETE .../action/{action}` |
| 23 | Ответ на действие — 200 с полным множеством действий |
| 24 | Деталь отдаёт неактивные и скрытые вакансии |
| 25 | `sources` в `filters/meta` — из публикаций, не из таблицы `sources` |
| 26 | `IntegrityError` → 409 `CONFLICT` без имени ограничения |

---

## Этап 6 — оценка резюме и подбор вакансий

**Эндпоинты.** `POST /resumes/{id}/score`, `GET /vacancies/recommended`.

**Файлы.** `app/services/{timeline,resume_scorer,matching,resume_scoring,recommendations}.py`,
`app/data/demo_resumes.json`, правки `app/schemas/{scoring,recommendations}.py`,
`app/services/{resumes,vacancy_filters}.py`, `app/api/v1/{resumes,recommendations}.py`;
тесты `tests/test_{timeline,resume_scorer,resume_scorer_reference,matching}.py`,
`tests/integration/test_api_{resume_score,recommendations}.py`.

**Допущения** (в коде `# TODO:`).

| # | Допущение |
|---|---|
| 1 | Компоненты округляются до 0.01 (ROUND_HALF_UP), итог — точная сумма |
| 2 | «Непустое» — `strip() != ""`; контакты заполнены, если есть хотя бы одно значение |
| 3 | Длина описания — только по `description`; частичные баллы за 100–199 и 1501–3000 символов |
| 4 | Метрика — регулярка (%, кратность, k/млн, число из ≥2 цифр, кроме годов и версий) |
| 5 | Оптимум навыков 8–15; больше 15 — половина баллов за количество |
| 6 | Половина критерия навыков — количество, половина — совпадение с рынком (решение пользователя) |
| 7 | Рынок: FTS по `target_position`, если ≥5 вакансий, иначе все активные; топ-20 |
| 8 | Пустой рынок — критерий навыков только по количеству |
| 9 | Все пробелы в опыте необъяснённые, хвостовой пробел до «сегодня» учитывается |
| 10 | Позиция без `end_date` и без `is_current` — нарушение последовательности, длина 0 |
| 11 | Зарплата в целях заполнена только с валютой; `desired_work_format=unknown` — заполнен |
| 12 | Рекомендации — русские шаблоны по `issues`; переформулировка LLM — этап 10 |
| 13 | Уровень резюме: грейд из `target_position`, иначе из стажа; без опыта — junior |
| 14 | Вакансия без навыков — 22.5 из 45; уровень `unknown` — 10 из 20 (решение пользователя) |
| 15 | Зарплата 15 / 7 / 0; разные валюты или периоды, нет данных — 7 (решение пользователя) |
| 16 | Желаемая удалёнка против офиса — 0; нет локации у стороны — 6 (решение пользователя) |
| 17 | `published_at=NULL` — 0 за свежесть; границы 3/7/14/30 дней включительные |
| 18 | Оценка пересчитывается при создании и содержательном PATCH (решение пользователя) |
| 19 | Кэш матчей пересчитывается при каждом GET, пишутся только изменившиеся строки (этап 14 — по событиям) |
| 20 | Строки матчей неактивных вакансий не удаляются |
| 21 | `limit` рекомендаций по умолчанию 50, максимум 200 |
| 22 | Нет резюме — 200 с пустым списком |

---

## Этап 7 — `scripts/seed.py`

**Команды.** `python -m scripts.seed [--dry-run] [--reset --yes] [--now ISO] --email …`
(локально через `.venv\Scripts\python`, в Docker — `docker compose exec api`).

**Файлы.** `app/data/{seed_sources,seed_vacancies}.json` (4 источника, 11 запусков,
72 публикации → 64 канона, 8 склеек, 4 partial), `app/services/{seed_data,seed}.py`,
`scripts/{__init__,seed}.py`, правки `Dockerfile`, `docker-compose.yml`,
`pyproject.toml`; тесты `tests/test_seed_{data,cli}.py`,
`tests/integration/test_seed{,_api}.py`.

**Допущения** (в коде `# TODO:`).

| # | Допущение |
|---|---|
| 1 | Возраст публикаций считается от `now`; повторный сид без `--reset` даты не освежает |
| 2 | Единица идемпотентности — источник: существующий `slug` пропускается с запусками и публикациями |
| 3 | Эталонное резюме опознаётся по `title` у пользователя сида (с этапа 12+ — учётная запись `--email`) |
| 4 | Действия сидируются, только если у пользователя их нет |
| 5 | `--reset` чистит домен вакансий для всех, резюме — только пользователя `--email` |
| 6 | В `ENVIRONMENT=prod` сид запрещён, обхода нет |
| 7 | Оценка эталонного резюме вне диапазона — ошибка и откат (код 2) |
| 8 | `items_found` / `items_new` — фактический результат `ingest_batch` |
| 9 | `last_run_at` источника — начало его последнего запуска |
| 10 | Telegram-записи без структурных полей, html — со структурными |
| 11 | `raw_payload` имитирует формат `fetch_raw` этапа 11 |
| 12 | `vacancy_matches` заранее не считаются |
| 13 | `--now` обязан быть с таймзоной и не в будущем |
| 14 | Компании вымышленные, ссылки `example.com` / `t.me/demo_…`, у источников `demo: true` |
| 15 | Автосида при `compose up` нет |

---

## Этап 8 — демо-фронтенд (4 экрана)

**Экраны.** «Вакансии» (фильтры, `sort=match`, drawer с разбивкой матча),
«Мои резюме», «Редактор» (локальный черновик, радар по 8 критериям),
«Источники» (таблица и история запусков). Бэкенд: read-only `GET /sources`,
`GET /sources/runs`, `resume_id` и `sort=match` в `GET /vacancies`.

**Файлы.** `frontend/src/**` (страницы, компоненты, `features.ts`, API-клиенты,
`schema.gen.ts`), `app/api/v1/sources.py`, `app/services/vacancies.py`; vitest-тесты.

**Допущения.**

| # | Допущение |
|---|---|
| 1 | `sort=match` считает матчи по всей отфильтрованной выборке; GET с `resume_id` пишет кэш |
| 2 | `sort=match` без `resume_id` — 422 |
| 3 | Из `config` источника наружу только `channel` или `url` |
| 4 | Активное резюме ленты — выбор в UI, не `is_primary` |
| 5 | Skeleton при любой смене ключа ленты; пагинация по 20 |
| 6 | Черновик резюме в `localStorage`; PATCH только по кнопке |
| 7 | Радар нормирует критерии в проценты от веса |
| 8 | `viewed` пишется при открытии drawer, один раз на id за сессию |
| 9 | Пороги цвета матча 75/50, оценки резюме 8/6.5 |
| 10 | Заголовок страницы 30/34px, eyebrow 11px — исключения из типографики |
| 11 | Типы API генерируются из OpenAPI (`npm run gen:api`) и коммитятся |

---

## Этап 9 — адаптеры LLM и profile

**Файлы.** `app/schemas/adapters.py`, `app/adapters/{__init__,fixtures,llm,profile}.py`,
правки `app/api/deps.py`, `app/config.py`, `.env.example`;
тесты `tests/test_adapters_{llm,profile}.py`, `tests/test_adapter_deps.py`.

**Допущения.**

| # | Допущение |
|---|---|
| 1 | Real без ключа или URL — `ExternalServiceError` в методе адаптера, старт не падает |
| 2 | `LLM_PROVIDER=anthropic` без `LLM_BASE_URL` падает; с URL — OpenAI-compatible `/chat/completions` |
| 3 | Profile-core: `GET {PROFILE_SERVICE_URL}/users/{user_id}` без авторизации |
| 4 | Mock не разбирает вход; фикстуры — константы Python |
| 5 | Повтор только для невалидного JSON или схемы; HTTP и таймаут не повторяются |
| 6 | `content` чата обязан быть строкой |
| 7 | Экран «Профиль» копирует поля резюме; адаптер их только умеет отдать |

---

## Этап 10 — ИИ-функции

**Эндпоинты.** `POST /resumes/generate`, `POST /resumes/{id}/tailor`; переписывание
текстов рекомендаций после `score_resume`.

**Файлы.** `app/services/resume_ai.py`, правки `app/api/v1/resumes.py`,
`app/services/{resume_scoring,resumes,seed}.py`, `app/adapters/llm.py`;
фронтенд `GenerateModal.tsx`, `features.ts`, `api/resumes.ts`;
тесты `tests/test_resume_phrases.py`, `tests/integration/test_api_resume_ai.py`.

**Допущения.**

| # | Допущение |
|---|---|
| 1 | Сид всегда на `MockLLMAdapter`, даже при `llm_mode=real` |
| 2 | Пустой шаблон рекомендации — mock отдаёт пустую строку |
| 3 | Несовпадение длины фраз оставляет шаблонные тексты |
| 4 | Черновик, не прошедший `ResumeCreate` / `ResumeUpdate`, — 502 `LLM_RESPONSE_INVALID` |
| 5 | Лимит текста 10 000 символов только в модалке |
| 6 | Tailor: 404 только если вакансии нет; не меняет `origin` и `is_primary`; mock переписывает только summary |

---

## Этап 11 — парсеры, RQ-задачи, планировщик

**Эндпоинт.** `POST /sources/{id}/run` → 202 или 409 (`SOURCE_ALREADY_RUNNING`, `DEMO_SOURCE`).

**Файлы.** `app/parsers/{base,registry,config,html_parser,telegram_parser}.py`,
`app/services/parsing.py`, `app/tasks/{queue,parse_source,scheduler,worker}.py`,
правки `app/api/v1/sources.py`, `app/schemas/sources.py`, `app/utils/errors.py`,
`Dockerfile` (Chromium), `docker-compose.yml` (сервис `scheduler`), `.env.example`;
фронтенд `SourcesTable.tsx`, `run-error.ts`, `features.ts`, `api/sources.ts`;
тесты `tests/test_*parser*.py`, `tests/test_parsing_schedule.py`,
`tests/test_source_run_api.py`, `tests/integration/test_parse_job.py`.

**Допущения.**

| # | Допущение |
|---|---|
| 1 | Остаёмся на `rq<2` и `rq-scheduler` 0.13 |
| 2 | `to_normalized` возвращает `RawVacancy`, не `NormalizedVacancy` |
| 3 | Новый HTML-сайт — строка `sources.config`; новый тип — класс и `register` |
| 4 | LLM-обогащение partial не вызывается |
| 5 | CSS разбирает selectolax после `page.content()`; `@attr` — по последнему `@` |
| 6 | robots.txt не 200 и не 404 — прогон failed; 404 — обход разрешён |
| 7 | Заданы оба ключа пагинации — побеждает `next_selector` |
| 8 | Нет url у карточки — `external_id = {page_url}#{index}` |
| 9 | Ошибки отдельных публикаций не переводят run в `failed` |
| 10 | Первый плановый запуск через один интервал; смена интервала — рестарт scheduler |
| 11 | Lock живёт до `rq_default_timeout`, если воркер умер |
| 12 | Нет интерактивного логина Telegram; нет файла сессии — failed |
| 13 | Chromium с `--no-sandbox` из-за non-root |
| 14 | `demo is True` проверяется раньше `parsers_enabled` — ответ `DEMO_SOURCE` |

---

## Этап 12 — README

**Файлы.** `README.md` (запуск демо), `vacancies-service/README.md` (разработка).

**Допущения.**

| # | Допущение |
|---|---|
| 1 | Команда `docker compose` (v2), хотя ТЗ пишет `docker-compose` |
| 2 | Перед демо нужен `--reset --yes`: повторный сид не обновляет даты |

---

## Этап 12+ — вход по почте, CI, публикация (вне ТЗ)

Коммит `ac27864`. Отдельные проверки субагентами по протоколу не фиксировались.

**Что сделано.** `POST /auth/register`, `/auth/login`, `/auth/logout`,
`GET /auth/me`; сессия — случайный токен в httpOnly-куке; эндпоинты резюме,
вакансий и рекомендаций требуют входа (401 без куки), источники и `/health` — нет. Экран входа и `RequireAuth` на фронтенде,
панель профиля на «Моих резюме». GitHub Actions: тесты на PR в `main`, после
влития — деплой по SSH. `docker-compose.prod.yml` для сервера 2 ядра / 4 ГБ
(без модели, Chromium, worker и scheduler).

**Файлы.** `app/api/v1/auth.py`, `app/schemas/auth.py`,
`app/services/{auth,passwords}.py`, правки `app/api/deps.py`, `app/config.py`,
`app/db/models.py`, `app/main.py`, `app/utils/errors.py`,
`migrations/versions/20261017_2130_7c1e0a4b9d22_users_and_sessions.py`,
`scripts/{seed,check_local_llm}.py`, `.env.example`, `.env.prod.example`,
`Dockerfile.api`, `docker-compose.prod.yml`, `frontend/{Dockerfile.prod,nginx.conf}`,
`frontend/src/features/auth/*`, `frontend/src/features/resumes/{ProfilePanel,profile}.*`,
`.github/workflows/ci.yml`, `docs/{deploy,llm,parsing}.md`; тесты
`tests/integration/test_api_auth.py`, `tests/test_passwords.py`.

**Допущения.**

| # | Допущение |
|---|---|
| 1 | Общего демо-пользователя нет: резюме и действия принадлежат учётной записи, вакансии и источники общие |
| 2 | Сид требует `--email` уже зарегистрированной учётной записи |
| 3 | CORS `allow_credentials=True`; `SESSION_COOKIE_SECURE` включается только за HTTPS |
| 4 | На сервере публикации `LLM_MODE=mock`, парсеры выключены |

---

## Этап 13 — источник hh.ru через API

**Статус:** `in progress`. Спецификация — [docs/hh-api.md](docs/hh-api.md).
Решения раздела 3 приняты в варианте «первое значение». Подэтап 13.0 сделан
вручную: приложение зарегистрировано, токен приложения лежит в `.env`.

### 13a — клиент API и настройки

**Статус:** `done`. Проверки: `mock-mode-auditor` — блокеров нет;
`verifier` — блокеров нет (ruff, mypy, 31 офлайн-тест).

**Файлы.** `app/config.py`, `app/adapters/hh.py`, `scripts/hh_token.py`,
`.env.example`, `.gitignore`, `tests/test_config.py`, `tests/test_adapters_hh.py`,
`tests/test_hh_token.py`.

Клиент не импортируется из `main`, `deps` и парсеров. Парсер, маппинг и запись
вакансий — 13b–13f.

**Допущения.**

| # | Допущение |
|---|---|
| 1 | Пустой `HH_APP_TOKEN` не валит старт; ошибка — в методе `HHClient`. Сервис токен не перевыпускает |
| 2 | Таймаут и обрыв соединения не повторяются; повтор только у 429, 500 и 503 |
| 3 | `HH_MAX_RETRIES` — число повторов после первой попытки |
| 4 | Все четыре метода требуют токен, хотя справочники hh отвечают и без него |
| 5 | Скрипт `hh_token` не пишет `.env`; лимит 5 минут держит файл `.hh_token_last_request` |
