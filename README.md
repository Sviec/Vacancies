# vacancies-service

Сервис агрегации вакансий из внешних источников, ведения резюме и подбора
рекомендаций под конкретное резюме. Работает автономно, без авторизации и без
остальных сервисов платформы.

Полное техническое задание: [TZ_vacancies_service.md](TZ_vacancies_service.md).
Локальная разработка и проверки — в [vacancies-service/README.md](vacancies-service/README.md).

## Подготовка

Команды ниже — из папки `vacancies-service/`. Сначала скопируйте окружение
без правок. Файл обязателен: `docker compose` читает его у api, worker,
scheduler и frontend.

```
cd vacancies-service
Copy-Item .env.example .env
```

На Linux и macOS: `cp .env.example .env`.

В скопированном файле уже `LLM_MODE=mock`, `PROFILE_MODE=mock` и
`PARSERS_ENABLED=false`. Демо после сида работает без API-ключей и без
интернета. Реальный LLM отложен, см. [docs/llm-generation.md](docs/llm-generation.md).

## Запуск

Нужен Docker Compose v2.

```
docker compose up
```

Одна команда поднимает postgres, redis, api, worker, scheduler, frontend и
одноразовый `migrate`, который накатывает схему до старта API. Повторный `up`
для миграций ничего не меняет. Сид в эту команду не входит.

Сайт: http://localhost:5173 — экраны `/vacancies`, `/resumes`, `/sources`.
API: http://localhost:8000. Живой стек отвечает `GET /health` со статусом `ok`.

Порты хоста задаются в `.env`: `API_HOST_PORT` (8000), `FRONTEND_HOST_PORT`
(5173), `POSTGRES_HOST_PORT` (5432), `REDIS_HOST_PORT` (6379). Если 5432 занят
локальным Postgres, смените только `POSTGRES_HOST_PORT` (на этой машине
разработки это 5433). Внутри Compose база всё равно доступна как `postgres:5432`.

## Демо-данные

Сид запускается вручную, когда контейнеры уже работают.

```
docker compose exec api python -m scripts.seed --dry-run
docker compose exec api python -m scripts.seed
docker compose exec api python -m scripts.seed --reset --yes
```

`--dry-run` печатает отчёт и откатывает транзакцию, в базу ничего не пишет.
Без флагов запись идемпотентна: уже существующие источники пропускаются.
Перед показом демо нужен `--reset --yes`: повторный сид без сброса не
обновляет даты публикаций. В `ENVIRONMENT=prod` сид запрещён и до базы не
доходит.
