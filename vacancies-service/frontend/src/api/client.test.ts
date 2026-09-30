import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch, buildQuery } from "@/api/client";
import { parseScoreDetails } from "@/api/types";

describe("buildQuery", () => {
  it("повторяет ключ для массивов", () => {
    expect(buildQuery({ work_format: ["remote", "hybrid"], page: 2 })).toBe(
      "?work_format=remote&work_format=hybrid&page=2",
    );
  });

  it("пропускает undefined, null, пустые строки и пустые массивы", () => {
    expect(buildQuery({ q: "", city: null, country: undefined, source: [], page: 1 })).toBe("?page=1");
    expect(buildQuery({ q: undefined })).toBe("");
  });

  it("пишет булевы как true/false, ноль сохраняет", () => {
    expect(buildQuery({ has_salary: false, saved_only: true, salary_min: 0 })).toBe(
      "?has_salary=false&saved_only=true&salary_min=0",
    );
  });

  it("кодирует спецсимволы", () => {
    expect(buildQuery({ q: "c++ & go" })).toBe("?q=c%2B%2B+%26+go");
  });
});

describe("apiFetch", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("сетевую ошибку превращает в NETWORK_ERROR", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(apiFetch("/health")).rejects.toMatchObject({
      code: "NETWORK_ERROR",
      status: 0,
    });
  });

  it("разбирает конверт ошибки API", async () => {
    const body = { error: { code: "NOT_FOUND", message: "Resume not found", details: { id: "x" } } };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 404 })));
    const error = await apiFetch("/api/v1/resumes/x").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ code: "NOT_FOUND", status: 404, details: { id: "x" } });
  });

  it("тело не JSON — UNKNOWN_ERROR со статусом", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("Bad gateway", { status: 502 })));
    await expect(apiFetch("/health")).rejects.toMatchObject({ code: "UNKNOWN_ERROR", status: 502 });
  });

  it("204 не парсит", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(apiFetch("/api/v1/resumes/x", { method: "DELETE" })).resolves.toBeUndefined();
  });
});

describe("parseScoreDetails", () => {
  const criterion = (key: string) => ({ key, name: key, weight: 1.25, points: 1, issues: [], recommendation: null });
  const valid = {
    version: 1,
    score: 6.31,
    criteria: [
      "completeness",
      "experience_quality",
      "measurable_achievements",
      "skills_relevance",
      "chronology",
      "education_courses",
      "languages",
      "goals_specificity",
    ].map(criterion),
    recommendations: ["Добавьте метрики"],
    market: { basis: "target_position", sample_size: 12, top_skills: ["python"] },
  };

  it("принимает валидную форму", () => {
    expect(parseScoreDetails(valid)?.score).toBe(6.31);
  });

  it("отвергает битую форму", () => {
    expect(parseScoreDetails(null)).toBeNull();
    expect(parseScoreDetails({})).toBeNull();
    expect(parseScoreDetails({ ...valid, version: 2 })).toBeNull();
    expect(parseScoreDetails({ ...valid, criteria: valid.criteria.slice(1) })).toBeNull();
    expect(parseScoreDetails({ ...valid, market: { ...valid.market, basis: "x" } })).toBeNull();
  });
});
