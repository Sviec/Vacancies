/**
 * Флаги недоступных пока функций: интерфейс готов, отправка выключена.
 * `aiGenerate` включается на этапе 10 (генерация резюме через LLM),
 * `runSource` — на этапе 11 (ручной запуск парсера).
 */
export const FEATURES = {
  aiGenerate: false,
  runSource: false,
} as const;
