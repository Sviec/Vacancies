# Парсинг источников

Стек умеет обходить публичные Telegram-каналы и HTML-страницы. Демо этого не
делает: `PARSERS_ENABLED=false`. Этот файл — что включить руками. Код сам по
себе ничего не переключает. Подключение модели — в [llm.md](llm.md).
Источник hh.ru через API в работе — план и справка в [hh-api.md](hh-api.md).

Демо-источники сида (`config.demo` равен `true`, каналы `@demo_…` и адреса
`example.com` / `example.org`) не обходятся никогда, даже после включения
парсеров. Кнопка «Запустить» на них отвечает 409 `DEMO_SOURCE`.

После любой правки `.env` перезапустите контейнеры `api`, `worker` и
`scheduler`. Настройки читаются при старте процесса, живой контейнер новый
файл не подхватывает.

```
docker compose up -d
docker compose restart api worker scheduler
```

Команды ниже — из папки `vacancies-service/`, стек уже поднят.

## 1. Общее для парсеров

1. В `.env` поставьте `PARSERS_ENABLED=true`.
2. Перезапустите `api`, `worker` и `scheduler`.
3. Добавьте строку в таблицу `sources`. Отдельного API «создать источник» нет.
   `slug` уникален. `source_type` — `telegram` или `html`. В `config` не
   ставьте `"demo": true`. `is_enabled` оставьте `true`.
4. Ручной прогон — кнопка «Запустить» на экране «Источники». Она шлёт
   `POST /api/v1/sources/{id}/run`. Ответ 202 значит, что
задача в очереди, а не что вакансии уже записаны. Первый плановый обход
начинается через `interval_hours` (если ключа нет — через 3 часа), не в момент
рестарта. Смена интервала и новый источник попадают в расписание только после
рестарта `scheduler`.

Пока по источнику идёт задача, второй запуск отвечает 409
`SOURCE_ALREADY_RUNNING`. Если воркер умер, блокировка живёт до
`RQ_DEFAULT_TIMEOUT` (по умолчанию 900 секунд).

Результат смотрите на экране «Источники»: статус, «найдено / новых», текст
ошибки. Счётчики берутся из записи в базу. Ошибка одной публикации не роняет
весь прогон: запуск остаётся успешным, текст ошибки пишется в историю.

Парсеры модель не вызывают. Слабо разобранная вакансия остаётся с
`parse_quality=partial`.

## 2. Telegram

Нужен публичный канал с username. Приватные каналы и каналы без `@username`
не обходятся. Медиа не скачиваются. Интерактивного входа в аккаунт в сервисе
нет: воркер только подключается к уже готовому файлу сессии.

### Ключи и сессия

1. На [my.telegram.org](https://my.telegram.org) создайте приложение и возьмите
   `api_id` и `api_hash`.
2. В `.env`:

```
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=ваш_hash
TELEGRAM_SESSION_NAME=vacancies
```

3. Один раз создайте файл сессии тем же именем, с теми же ключами, на своей
   машине (не в репозитории). Файл `*.session` в git не попадает. Пример,
   из папки, где лежит сессия:

```
python -c "from telethon.sync import TelegramClient; TelegramClient('vacancies', 123456, 'ваш_hash').start()"
```

Команда спросит телефон и код. На выходе появится `vacancies.session`.

4. Воркер ищет файл в рабочей папке контейнера: `/srv/vacancies.session`.
   Compose этот файл не монтирует, при пересоздании контейнера он пропадёт.
   Скопируйте его в работающий воркер:

```
docker compose cp vacancies.session worker:/srv/vacancies.session
```

Чтобы сессия пережила пересоздание, смонтируйте файл в сервис `worker` в
`docker-compose.yml` (только у воркера, планировщик в Telegram не ходит):

```yaml
volumes:
  - ./vacancies.session:/srv/vacancies.session:ro
```

Путь слева — файл на хосте. После правки compose: `docker compose up -d worker`.

Нет ключей или нет файла — прогон падает со статусом `failed`, API и остальные
источники продолжают работать.

### Строка источника

```sql
INSERT INTO sources (id, slug, source_type, config)
VALUES (
  gen_random_uuid(),
  'tg_it_jobs_live',
  'telegram',
  '{
    "channel": "@it_jobs",
    "limit": 100,
    "keywords_filter": ["python", "удалён"],
    "interval_hours": 3
  }'::jsonb
);
```

`channel` — публичный `@username`. `limit` — сколько последних сообщений
читать; нет ключа — 100, больше 500 сервис обрежет. Пустой
`keywords_filter` пропускает все посты. Иначе пост должен содержать хотя бы
одно слово, без учёта регистра.

Из текста поста регулярками берутся: первая непустая строка (заголовок, до
200 символов), строки `Компания:` / `Company:` / `Работодатель:`, `Город:` /
`City:` / `Локация:` / `Location:`, первая строка с зарплатой и первая ссылка
`http(s)`. Остальной текст уходит в описание как есть. Дальше общий
нормализатор.

После вставки перезапустите `scheduler` и нажмите «Запустить» у новой строки,
если ждать интервал не нужно.

## 3. Сайты с вакансиями

Новый сайт — новая строка `source_type=html`. Python не меняется. В образ
уже входит headless Chromium. Селекторы — обычный CSS, который понимает
selectolax. Селектор, который умеет только Playwright, не сработает.
Атрибут пишется через `@` в конце: `a.vacancy-link@href`, `time@datetime`.

Обязательны `url` и `list_selector`. Без них прогон падает до запроса страницы.

Перед страницами сервис читает `robots.txt` этого хоста (`RESPECT_ROBOTS_TXT=true`).
Ответ 404 — обход разрешён. Любой другой сбой или запрет — прогон `failed`,
страница не открывается. Между страницами пауза не меньше 1 секунды:
`delay_seconds` в config, иначе `HTTP_REQUEST_DELAY_SECONDS` (1.5).

Пагинация: `next_selector` (ссылка «дальше») или `page_param` (номер в query).
Если заданы оба, используется только `next_selector`. Нет ни того ни другого —
одна страница. `max_pages` нет — одна страница.

```sql
INSERT INTO sources (id, slug, source_type, config)
VALUES (
  gen_random_uuid(),
  'html_careerhub_live',
  'html',
  '{
    "url": "https://careers.example.com/vacancies",
    "list_selector": "article.vacancy-card",
    "fields": {
      "title": "h2.vacancy-title",
      "company": ".vacancy-company",
      "city": ".vacancy-location",
      "salary": ".vacancy-salary",
      "description": ".vacancy-body",
      "url": "a.vacancy-link@href",
      "published_at": "time@datetime",
      "skills": ".vacancy-tags li"
    },
    "pagination": {"next_selector": "a.pager-next", "max_pages": 5},
    "delay_seconds": 2,
    "interval_hours": 3
  }'::jsonb
);
```

`published_at` — дата ISO-8601 с часовым поясом, иначе поле пустое. Зарплата
берётся строкой, числа считает нормализатор. Нет ключа `skills` — навыки
ищутся в тексте. Ключ есть, узлов нет — список навыков пустой. Нет ссылки у
карточки — внешний id равен `{адрес страницы}#{номер карточки}`.

Второй способ листания, вместо `next_selector`:

```json
"pagination": {"page_param": "page", "max_pages": 3}
```

Страницы идут с `page=1`. Пустая выдача останавливает обход раньше
`max_pages`.

Дальше то же, что у Telegram: рестарт `scheduler`, при необходимости кнопка
«Запустить».
