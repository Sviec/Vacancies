# Публикация на сервере 2 ядра / 4 ГБ / 40 ГБ

На этой машине работает сервис вакансий: Postgres, Redis, API и статический
фронтенд. Сумма лимитов контейнеров около 1.5 ГБ, остальное остаётся системе.

Сюда не ставятся:

- веса модели (Qwen 7B в Q4 — около 5 ГБ на диске и несколько гигабайт в RAM);
- Ollama, llama.cpp, vLLM;
- Chromium, worker и scheduler. `PARSERS_ENABLED=false`.

Модель крутится на ноутбуке или на другой машине с достаточным объёмом памяти.
Как её скачать и какие размеры брать — в [llm-generation.md](llm-generation.md).
Пока API на сервере остаётся в `LLM_MODE=mock`: черновик резюме фиксированный,
запроса к модели нет.

Авторизации в сервисе нет. Любой, кто откроет сайт, работает с одним
демо-пользователем. Это публичное демо, не закрытый кабинет.

## Состав

`vacancies-service/docker-compose.prod.yml` поднимает пять сервисов:

| Сервис | Лимит RAM | Зачем |
|---|---|---|
| postgres | 768 МБ | `shared_buffers=128MB`, не больше 30 соединений |
| redis | 96 МБ | очередь health-проверки, снимок на диск выключен, потолок 64 МБ |
| migrate | 256 МБ | один раз `alembic upgrade head` |
| api | 512 МБ | один процесс uvicorn, пул базы 2+2 |
| web | 64 МБ | nginx со статикой Vite, `/api` и `/health` проксируются на api |

Порты Postgres и Redis наружу не публикуются. Снаружи открыт только порт
`WEB_HOST_PORT` (по умолчанию 80). Логи каждого контейнера режутся до 3 файлов
по 10 МБ, чтобы журнал не заполнил диск.

Образ API — `Dockerfile.api`: зависимости без pytest/ruff и без браузера
Playwright. Обычный `docker compose up` по-прежнему собирает демо-образ с
Chromium и Vite.

## Запуск

Команды из папки `vacancies-service/`. Собирать образы лучше на ноутбуке:
на VPS сборка Node и pip легко упирается в 4 ГБ.

```
Copy-Item .env.prod.example .env.prod
```

В `.env.prod` смените `POSTGRES_PASSWORD`. Тот же пароль должен стоять в
`DATABASE_URL`. `ENVIRONMENT=dev` оставляет сид доступным. `ENVIRONMENT=prod`
запрещает `scripts.seed` до подключения к базе.

```
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```

Сначала зарегистрируйтесь на сайте, затем передайте эту почту сиду:

```
docker compose --env-file .env.prod -f docker-compose.prod.yml exec api python -m scripts.seed --reset --yes --email you@example.com
```

Сайт: `http://<адрес-сервера>/`. Проверка: `GET /health` со статусом `ok`.

Флаг `--env-file .env.prod` обязателен. Без него Compose подставит пароль
`change-me` из значений по умолчанию в файле, даже если в `.env.prod` записан
другой.

## Модель рядом, но не на этом сервере

На машине с моделью:

```
ollama pull qwen2.5:7b-instruct
ollama serve
```

К API вакансий на VPS этот процесс сам не подключится: сервер не достучится
до `localhost` ноутбука. Пока связь не нужна, на VPS оставляйте `LLM_MODE=mock`.
Когда появится машина, до которой VPS ходит по сети, в `.env.prod` API
достаточно такого блока и рестарта `api`:

```
LLM_MODE=real
LLM_BASE_URL=http://<хост-с-моделью>:11434/v1
LLM_API_KEY=local
LLM_MODEL=qwen2.5:7b-instruct
LLM_TIMEOUT_SECONDS=120
```

Ключ `local` — любая непустая строка. Веса по-прежнему не копируются на VPS.

## Публикация через GitHub

Разработка идёт в отдельных ветках. Push в такую ветку проверки не запускает.
Pull request в `main` гоняет тесты. После влития в `main` те же тесты
проходят ещё раз, и только потом задача деплоя заходит на сервер по SSH:
`git pull` и `docker compose -f docker-compose.prod.yml up -d --build`.
Модели, `.env.prod` и файл сессии Telegram в репозитории нет, деплой их не
переносит.

Секреты репозитория: `SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY`, `DEPLOY_PATH`
(каталог клона на сервере). В настройках `main` лучше запретить прямой push
и требовать прошедший pull request.

