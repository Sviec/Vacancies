import { describe, expect, it } from "vitest";

import type { MatchCriterionBreakdown, MatchSkillsBreakdown } from "@/api/types";
import { describeCriterion, formatPoints, matchTone } from "@/lib/match-reasons";

function criterion(
  reason: string,
  points = 5,
  maxPoints = 10,
  context: MatchCriterionBreakdown["context"] = {},
): MatchCriterionBreakdown {
  return { points, max_points: maxPoints, reason, context };
}

function skills(
  reason: string,
  matched: string[] = [],
  missing: string[] = [],
  context?: MatchSkillsBreakdown["context"],
): MatchSkillsBreakdown {
  return {
    matched,
    missing,
    points: 20,
    max_points: 45,
    reason,
    context,
  };
}

describe("matchTone", () => {
  it("пороги 75 и 50", () => {
    expect(matchTone(100)).toBe("positive");
    expect(matchTone(75)).toBe("positive");
    expect(matchTone(74)).toBe("accent");
    expect(matchTone(50)).toBe("accent");
    expect(matchTone(49)).toBe("muted");
    expect(matchTone(0)).toBe("muted");
  });
});

describe("formatPoints", () => {
  it("форматирует через запятую", () => {
    expect(formatPoints(12.5, 20)).toBe("12,5 из 20");
  });
});

describe("describeCriterion", () => {
  it("skills: vacancy_skills_unknown и ratio", () => {
    expect(describeCriterion("skills", skills("vacancy_skills_unknown"))).toBe(
      "В вакансии не указаны навыки — нейтральная оценка",
    );
    expect(
      describeCriterion(
        "skills",
        skills("ratio", ["Python", "SQL"], ["Go"], {
          matched_count: 2,
          vacancy_count: 3,
        }),
      ),
    ).toBe("Совпало 2 из 3 навыков");
  });

  it("skills: неизвестный код — нейтральный fallback", () => {
    expect(describeCriterion("skills", skills("weird_code"))).toBe("20 из 45 баллов");
  });

  it("level: exact / adjacent / gap / unknown / fallback", () => {
    expect(
      describeCriterion(
        "level",
        criterion("exact", 15, 15, { resume_level: "middle", vacancy_level: "middle" }),
      ),
    ).toBe("Уровень совпадает: Middle");
    expect(
      describeCriterion(
        "level",
        criterion("adjacent", 10, 15, { resume_level: "middle", vacancy_level: "senior" }),
      ),
    ).toBe("Соседний уровень: в резюме Middle, в вакансии Senior");
    expect(
      describeCriterion(
        "level",
        criterion("gap", 0, 15, { resume_level: "junior", vacancy_level: "lead" }),
      ),
    ).toBe("Уровень далеко: в резюме Junior, в вакансии Lead");
    expect(describeCriterion("level", criterion("level_unknown"))).toBe(
      "Уровень не определён — нейтральная оценка",
    );
    expect(describeCriterion("level", criterion("no_such_reason", 3, 15))).toBe(
      "3 из 15 баллов",
    );
  });

  it("salary: все известные коды", () => {
    const cases: Record<string, string> = {
      covers: "Вилка покрывает желаемую зарплату",
      partial: "Нижняя граница ниже желаемой, верх не указан",
      below: "Верх вилки ниже желаемой зарплаты",
      vacancy_salary_unknown: "Зарплата в вакансии не указана",
      resume_salary_unknown: "В резюме не указана желаемая зарплата",
      currency_unknown: "Валюта не указана — сравнить нельзя",
      currency_mismatch: "Валюта вакансии отличается от желаемой",
      period_not_comparable: "Вилка указана не за месяц — сравнить нельзя",
    };
    for (const [reason, text] of Object.entries(cases)) {
      expect(describeCriterion("salary", criterion(reason))).toBe(text);
    }
    expect(describeCriterion("salary", criterion("unknown_salary", 1, 10))).toBe(
      "1 из 10 баллов",
    );
  });

  it("location: все известные коды", () => {
    const cases: Record<string, string> = {
      remote: "Удалённая работа",
      remote_wanted: "Нужна удалёнка, а вакансия в офисе",
      city: "Тот же город",
      country: "Та же страна, другой город",
      relocation: "Другая локация, но есть релокация",
      mismatch: "Локация не совпадает",
      resume_location_unknown: "В резюме не указана желаемая локация",
      vacancy_location_unknown: "В вакансии не указана локация",
    };
    for (const [reason, text] of Object.entries(cases)) {
      expect(describeCriterion("location", criterion(reason))).toBe(text);
    }
    expect(describeCriterion("location", criterion("weird", 0, 10))).toBe("0 из 10 баллов");
  });

  it("freshness: все известные коды", () => {
    const cases: Record<string, string> = {
      le_3d: "Свежая — до 3 дней",
      le_7d: "Опубликована в течение недели",
      le_14d: "Опубликована в течение двух недель",
      le_30d: "Опубликована в течение месяца",
      older: "Опубликована больше месяца назад",
      date_unknown: "Дата публикации неизвестна",
    };
    for (const [reason, text] of Object.entries(cases)) {
      expect(describeCriterion("freshness", criterion(reason))).toBe(text);
    }
    expect(describeCriterion("freshness", criterion("mystery", 2, 5))).toBe("2 из 5 баллов");
  });
});
