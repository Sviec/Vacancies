/**
 * Разбор/сериализация URL экрана «Источники».
 */

import { describe, expect, it } from "vitest";

import {
  parseSourcesParams,
  serializeSourcesParams,
} from "@/features/sources/sources-url";

describe("sources-url", () => {
  it("парсит валидные source и status", () => {
    const id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
    const params = new URLSearchParams(`source=${id}&status=failed`);
    expect(parseSourcesParams(params)).toEqual({ sourceId: id, status: "failed" });
  });

  it("отбрасывает мусор", () => {
    const params = new URLSearchParams("source=not-uuid&status=boom");
    expect(parseSourcesParams(params)).toEqual({ sourceId: null, status: null });
  });

  it("не пишет дефолты в URL", () => {
    expect(serializeSourcesParams({ sourceId: null, status: null }).toString()).toBe("");
    const id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
    expect(serializeSourcesParams({ sourceId: id, status: "success" }).toString()).toBe(
      `source=${id}&status=success`,
    );
  });
});
