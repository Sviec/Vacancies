/**
 * Флаги функций, которые интерфейс уже показывает.
 * `aiGenerate` — генерация резюме через LLM.
 * `runSource` включается на этапе 11 (ручной запуск парсера).
 */
export const FEATURES = {
  aiGenerate: true,
  runSource: false,
} as const;
