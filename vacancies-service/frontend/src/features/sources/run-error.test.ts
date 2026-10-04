import { describe, expect, it } from "vitest";

import { runErrorMessage } from "@/features/sources/run-error";

describe("runErrorMessage", () => {
  it("объясняет демо-источник", () => {
    expect(runErrorMessage("DEMO_SOURCE")).toBe(
      "Демо-источник не обходится. Данные на экране — из сида, сеть не вызывается.",
    );
  });

  it("коротко переводит известные коды", () => {
    expect(runErrorMessage("PARSERS_DISABLED")).toBe("Парсеры выключены.");
    expect(runErrorMessage("SOURCE_DISABLED")).toBe("Источник выключен.");
    expect(runErrorMessage("SOURCE_NOT_RUNNABLE")).toBe("Этот тип источника не запускается.");
    expect(runErrorMessage("SOURCE_ALREADY_RUNNING")).toBe("Парсер уже выполняется.");
    expect(runErrorMessage("NOT_FOUND")).toBe("Источник не найден.");
    expect(runErrorMessage("DEPENDENCY_UNAVAILABLE")).toBe("Очередь задач недоступна.");
  });

  it("неизвестный код не показывает английский message", () => {
    expect(runErrorMessage("SOMETHING_ELSE")).toBe("Не удалось запустить парсер");
    expect(runErrorMessage("")).toBe("Не удалось запустить парсер");
  });
});