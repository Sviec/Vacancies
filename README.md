# vacancies-service

Сервис агрегации вакансий из внешних источников, ведения резюме и подбора
рекомендаций под конкретное резюме.

## Запуск

```
cd vacancies-service
docker compose up
```

Одна команда поднимает Postgres, Redis, API, worker, frontend и одноразовый
`migrate`, который накатывает схему до старта API. Повторный `up` — no-op
для миграций.

Полное техническое задание: [TZ_vacancies_service.md](TZ_vacancies_service.md).

Подробная инструкция по запуску и разработке будет здесь на этапе 12.
