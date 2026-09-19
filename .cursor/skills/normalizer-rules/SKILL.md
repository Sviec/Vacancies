---
name: normalizer-rules
description: Правила приведения сырых данных вакансий к NormalizedVacancy для vacancies-service (зарплата, навыки, уровень, дедупликация). Use when writing or editing app/services/normalizer.py, app/utils/skills_dict.py, or any parser's to_normalized method.
---

# Правила нормализации вакансий (раздел 3 ТЗ)

## Зарплата
Парсить строки вида «от 150 000 руб.», «150-200к», «$3000-4000», «до 250т.р.», «з/п по договорённости».

- `к` / `k` / `т.р.` = множитель ×1000.
- «от X» → `salary_min=X`, `salary_max=None`.
- «до X» → `salary_max=X`, `salary_min=None`.
- «по договорённости» или отсутствие суммы → `salary_min`, `salary_max`, `salary_currency`, `salary_period` все `None`.
- Валюта определяется по символу (₽/$/€) или слову (руб/rub/usd/eur). `salary_currency` — код ISO-4217 (`RUB`, `USD`, `EUR`).

## Навыки
- Приводить к нижнему регистру.
- Применять словарь синонимов из `utils/skills_dict.py`: `js`/`javascript` → `javascript`, `питон`/`python` → `python`, `postgres`/`postgresql` → `postgresql`.
- Словарь — расширяемый JSON-файл, никогда не хардкодить соответствия прямо в `normalizer.py`.

## Уровень опыта
1. Сначала искать ключевые слова в заголовке: `junior`/`джуниор`/`стажёр` → `intern`/`junior`, аналогично для middle/senior/lead.
2. Если ключевых слов нет — выводить из `experience_min_years`: 0–1 → `junior`, 1–3 → `middle`, 3–6 → `senior`, 6+ → `lead`.
3. Если ни то ни другое не определено — `unknown`, не гадать.

## Дедупликация
- `content_hash` = sha256 от (`title` + `company` + `description_clean`).
- Перед вставкой всегда проверять существующий хэш. При совпадении — обновить `last_seen_at` у существующей записи, не создавать дубль.
- Дубли между разными Telegram-каналами — ожидаемая ситуация, не ошибка парсинга.

## Обязательные поля и `parse_quality`
- Парсер, который не может заполнить обязательное поле (кроме `title`, которое всегда обязательно), должен пометить вакансию `parse_quality="partial"`, а не отбросить её.
- `description_clean` всегда без эмодзи, markdown-разметки, хештегов — но `description_raw` хранится как есть, без изменений.
