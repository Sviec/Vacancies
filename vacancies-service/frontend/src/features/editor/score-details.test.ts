import { describe, expect, it } from "vitest";

import { parseScoreDetails } from "@/api/types";

const VALID = {
  version: 1 as const,
  score: 9.2,
  criteria: [
    { key: "completeness", name: "Полнота", weight: 1.5, points: 1.5, recommendation: null },
    {
      key: "experience_quality",
      name: "Качество опыта",
      weight: 2,
      points: 1.8,
      recommendation: "Добавьте контекст",
    },
    {
      key: "measurable_achievements",
      name: "Измеримые достижения",
      weight: 1.5,
      points: 1.5,
      recommendation: null,
    },
    { key: "skills_relevance", name: "Навыки", weight: 1.5, points: 1.4, recommendation: null },
    { key: "chronology", name: "Хронология", weight: 0.5, points: 0.5, recommendation: null },
    {
      key: "education_courses",
      name: "Образование",
      weight: 1,
      points: 0.8,
      recommendation: null,
    },
    { key: "languages", name: "Языки", weight: 0.5, points: 0.5, recommendation: null },
    {
      key: "goals_specificity",
      name: "Цели",
      weight: 1.5,
      points: 1.2,
      recommendation: "Уточните вилку",
    },
  ],
  recommendations: ["Добавьте контекст", "Уточните вилку"],
  market: {
    basis: "target_position" as const,
    sample_size: 42,
    top_skills: ["python", "fastapi", "postgresql"],
  },
};

describe("parseScoreDetails", () => {
  it("принимает валидную форму version=1 с 8 критериями", () => {
    const parsed = parseScoreDetails(VALID);
    expect(parsed).not.toBeNull();
    expect(parsed?.score).toBe(9.2);
    expect(parsed?.criteria).toHaveLength(8);
    expect(parsed?.market.top_skills).toContain("python");
  });

  it("отвергает битую и старую форму", () => {
    expect(parseScoreDetails(null)).toBeNull();
    expect(parseScoreDetails({ ...VALID, version: 2 })).toBeNull();
    expect(parseScoreDetails({ ...VALID, criteria: VALID.criteria.slice(0, 3) })).toBeNull();
    expect(parseScoreDetails({ ...VALID, market: { ...VALID.market, basis: "x" } })).toBeNull();
    expect(parseScoreDetails({ ...VALID, recommendations: "x" })).toBeNull();
  });
});
