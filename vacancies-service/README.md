# vacancies-service

Бэкенд и демо-фронтенд сервиса вакансий. Общее описание проекта — в
[README репозитория](../README.md), техническое задание —
[../TZ_vacancies_service.md](../TZ_vacancies_service.md).

## Запуск

Из этой папки:

```
docker compose up
```

Демо-данные (источники, вакансии, три эталонных резюме) загружаются вручную при поднятом стеке:

```
docker compose exec api python -m scripts.seed --dry-run     # отчёт без записи
docker compose exec api python -m scripts.seed               # идемпотентно
docker compose exec api python -m scripts.seed --reset --yes # очистить и засеять заново (освежает даты)
```

Локально — `.venv\Scripts\python -m scripts.seed` из этой папки. В `ENVIRONMENT=prod` сид запрещён.

Подробная инструкция по запуску и разработке будет здесь на этапе 12.
