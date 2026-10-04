# vacancies-service

Бэкенд и демо-фронтенд сервиса вакансий. Как поднять демо в Docker —
в [README репозитория](../README.md). Техническое задание —
[../TZ_vacancies_service.md](../TZ_vacancies_service.md).

## Локальное окружение

Python 3.12. Из этой папки:

```
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

`DATABASE_URL` и `REDIS_URL` в `.env` указывают на localhost — это запуск вне
Docker. Compose подменяет их на имена `postgres` и `redis` внутри сети.

## Проверки

Из этой папки, без запущенных Postgres и Redis:

```
.venv\Scripts\ruff check app tests
.venv\Scripts\ruff format --check app tests
.venv\Scripts\mypy app
.venv\Scripts\pytest
```

`pytest` по умолчанию не берёт интеграционные тесты. Для них нужен живой
Postgres; база `vacancies_test` выводится из `DATABASE_URL`:

```
.venv\Scripts\pytest -m integration
```

Фронтенд, из `frontend/`:

```
npm install
npm run typecheck
npm test
```

## Очередь

`python -m app.tasks.worker` на Windows не стартует: RQ использует `fork`.
Воркер и планировщик (`python -m app.tasks.scheduler`) запускаются в Docker
или на Linux. В демо `PARSERS_ENABLED=false`, планировщик наружу не ходит.

## Сид вне Docker

Те же флаги, что в корневом README, из этой папки:

```
.venv\Scripts\python -m scripts.seed --help
```

Порядок для демо (`--dry-run`, запись, `--reset --yes`) описан в корневом
README. В `ENVIRONMENT=prod` сид запрещён.
