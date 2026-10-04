/**
 * Флаги функций, которые интерфейс уже показывает.
 * `aiGenerate` — генерация резюме через LLM.
 * `runSource` — ручной запуск парсера (POST /sources/{id}/run).
 */
export const FEATURES = {
  aiGenerate: true,
  runSource: true,
} as const;
