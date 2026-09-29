# Один образ обслуживает оба Python-сервиса: api (uvicorn) и worker (RQ).
# Они отличаются только командой запуска, поэтому docker-compose.yml объявляет
# у обоих одинаковые `build: .` и `image: vacancies-service:local` — Compose
# собирает образ ровно один раз.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# apt-get сознательно не вызывается: у asyncpg и остальных зависимостей есть
# готовые колёса cp312, компилятор не нужен.
# TODO: на этапе 11 добавится Playwright — тогда потребуется либо
# `playwright install --with-deps chromium` (тянет системные библиотеки
# Chromium), либо переход на базовый образ mcr.microsoft.com/playwright/python.

# Порядок COPY даёт кэш слоёв: тяжёлый слой с зависимостями пересобирается
# только при правке pyproject.toml или app/__init__.py, а не при каждой правке
# кода. Не переставлять.
# app/__init__.py копируется до установки, потому что hatchling при
# editable-установке требует, чтобы пакет из [tool.hatch.build.targets.wheel]
# уже существовал на диске.
COPY pyproject.toml README.md ./
COPY app/__init__.py app/__init__.py

RUN pip install --upgrade pip && pip install -e ".[dev]"

COPY app ./app
COPY scripts ./scripts
COPY tests ./tests

# Миграции копируются вместе с кодом, последним слоем: кэш тяжёлого слоя
# зависимостей это не ломает. Нужны и сервису migrate (он их применяет), и
# образу api/worker — чтобы `alembic` можно было запустить внутри контейнера
# для разбора инцидента, не пересобирая образ.
COPY alembic.ini ./
COPY migrations ./migrations

# Non-root после установки зависимостей: pip должен писать в system site-packages.
# /srv и содержимое остаются за root с правами 755 — пользователю app этого
# достаточно, чтобы читать и импортировать код.
RUN useradd --create-home --uid 10001 app
USER app

EXPOSE 8000

# Healthcheck объявлен в docker-compose.yml, а не здесь: он использует
# urllib из стандартной библиотеки, чтобы не тащить curl/wget в образ.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
