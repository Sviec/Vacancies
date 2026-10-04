/**
 * Русские подписи к кодам POST /sources/{id}/run.
 * `error.message` с бэкенда не показываем: там английский текст API.
 */

const RUN_ERROR_TEXT: Record<string, string> = {
  DEMO_SOURCE:
    "Демо-источник не обходится. Данные на экране — из сида, сеть не вызывается.",
  PARSERS_DISABLED: "Парсеры выключены.",
  SOURCE_DISABLED: "Источник выключен.",
  SOURCE_NOT_RUNNABLE: "Этот тип источника не запускается.",
  SOURCE_ALREADY_RUNNING: "Парсер уже выполняется.",
  NOT_FOUND: "Источник не найден.",
  DEPENDENCY_UNAVAILABLE: "Очередь задач недоступна.",
};

export function runErrorMessage(code: string): string {
  return RUN_ERROR_TEXT[code] ?? "Не удалось запустить парсер";
}
