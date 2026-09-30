/**
 * Русские тексты разбивки матчинга. Бэкенд отдаёт машинные коды `reason` и
 * `context` (matching.py), текст собирается здесь.
 */

import type {
  ExperienceLevel,
  MatchCriterionBreakdown,
  MatchDetails,
  MatchSkillsBreakdown,
} from "@/api/types";
import { EXPERIENCE_LEVEL_LABELS } from "@/lib/labels";

export type MatchCriterionKey = keyof MatchDetails;

export const MATCH_CRITERION_TITLES: Record<MatchCriterionKey, string> = {
  skills: "Навыки",
  level: "Уровень",
  salary: "Зарплата",
  location: "Локация",
  freshness: "Свежесть",
};

const POINTS = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 });

const STATIC_REASONS: Record<Exclude<MatchCriterionKey, "skills">, Record<string, string>> = {
  level: {
    level_unknown: "Уровень не определён — нейтральная оценка",
  },
  salary: {
    covers: "Вилка покрывает желаемую зарплату",
    partial: "Нижняя граница ниже желаемой, верх не указан",
    below: "Верх вилки ниже желаемой зарплаты",
    vacancy_salary_unknown: "Зарплата в вакансии не указана",
    resume_salary_unknown: "В резюме не указана желаемая зарплата",
    currency_unknown: "Валюта не указана — сравнить нельзя",
    currency_mismatch: "Валюта вакансии отличается от желаемой",
    period_not_comparable: "Вилка указана не за месяц — сравнить нельзя",
  },
  location: {
    remote: "Удалённая работа",
    remote_wanted: "Нужна удалёнка, а вакансия в офисе",
    city: "Тот же город",
    country: "Та же страна, другой город",
    relocation: "Другая локация, но есть релокация",
    mismatch: "Локация не совпадает",
    resume_location_unknown: "В резюме не указана желаемая локация",
    vacancy_location_unknown: "В вакансии не указана локация",
  },
  freshness: {
    le_3d: "Свежая — до 3 дней",
    le_7d: "Опубликована в течение недели",
    le_14d: "Опубликована в течение двух недель",
    le_30d: "Опубликована в течение месяца",
    older: "Опубликована больше месяца назад",
    date_unknown: "Дата публикации неизвестна",
  },
};

function levelLabel(value: unknown): string {
  return typeof value === "string" && value in EXPERIENCE_LEVEL_LABELS
    ? EXPERIENCE_LEVEL_LABELS[value as ExperienceLevel]
    : "—";
}

/** «12,5 из 20 баллов». */
export function formatPoints(points: number, maxPoints: number): string {
  return `${POINTS.format(points)} из ${POINTS.format(maxPoints)}`;
}

// TODO: для неизвестного кода — нейтральный текст по баллам.
function fallback(breakdown: MatchCriterionBreakdown | MatchSkillsBreakdown): string {
  return `${formatPoints(breakdown.points, breakdown.max_points ?? 0)} баллов`;
}

function describeSkills(breakdown: MatchSkillsBreakdown): string {
  if (breakdown.reason === "vacancy_skills_unknown") {
    return "В вакансии не указаны навыки — нейтральная оценка";
  }
  if (breakdown.reason === "ratio") {
    const matched = Number(breakdown.context?.matched_count ?? breakdown.matched.length);
    const total = Number(
      breakdown.context?.vacancy_count ?? breakdown.matched.length + breakdown.missing.length,
    );
    return `Совпало ${matched} из ${total} ${total === 1 ? "навыка" : "навыков"}`;
  }
  return fallback(breakdown);
}

function describeLevel(breakdown: MatchCriterionBreakdown): string {
  const resume = levelLabel(breakdown.context?.resume_level);
  const vacancy = levelLabel(breakdown.context?.vacancy_level);
  switch (breakdown.reason) {
    case "exact":
      return `Уровень совпадает: ${vacancy}`;
    case "adjacent":
      return `Соседний уровень: в резюме ${resume}, в вакансии ${vacancy}`;
    case "gap":
      return `Уровень далеко: в резюме ${resume}, в вакансии ${vacancy}`;
    default:
      return STATIC_REASONS.level[breakdown.reason] ?? fallback(breakdown);
  }
}

export function describeCriterion(key: "skills", breakdown: MatchSkillsBreakdown): string;
export function describeCriterion(
  key: Exclude<MatchCriterionKey, "skills">,
  breakdown: MatchCriterionBreakdown,
): string;
export function describeCriterion(
  key: MatchCriterionKey,
  breakdown: MatchCriterionBreakdown | MatchSkillsBreakdown,
): string {
  if (key === "skills") {
    return describeSkills(breakdown as MatchSkillsBreakdown);
  }
  if (key === "level") {
    return describeLevel(breakdown);
  }
  return STATIC_REASONS[key][breakdown.reason] ?? fallback(breakdown);
}

export type MatchTone = "positive" | "accent" | "muted";

// TODO: пороги цвета процента соответствия — 75 и 50.
export function matchTone(score: number): MatchTone {
  if (score >= 75) {
    return "positive";
  }
  if (score >= 50) {
    return "accent";
  }
  return "muted";
}
