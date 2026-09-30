/** Чистые помощники отображения карточки и drawer вакансии. */

import { pluralRu } from "@/lib/format";

/** Источники карточки: сначала победитель дедупликации, затем остальные. */
export function orderedSources(source: string, sources: readonly string[] | undefined): string[] {
  return [source, ...(sources ?? []).filter((item) => item !== source)];
}

export interface CardSkill {
  name: string;
  matched: boolean;
}

/**
 * Навыки на карточке: сначала совпавшие с резюме, затем остальные в исходном
 * порядке; не больше `limit`, остаток — числом для чипа «+N».
 */
export function cardSkills(
  skills: readonly string[],
  matched: readonly string[] | undefined,
  limit = 5,
): { shown: CardSkill[]; rest: number } {
  const matchedSet = new Set((matched ?? []).map((item) => item.toLowerCase()));
  const all = skills.map((name) => ({ name, matched: matchedSet.has(name.toLowerCase()) }));
  const ordered = [...all.filter((item) => item.matched), ...all.filter((item) => !item.matched)];
  return { shown: ordered.slice(0, limit), rest: Math.max(ordered.length - limit, 0) };
}

export function relocationLabel(value: boolean | null): string {
  if (value === true) {
    return "Есть релокация";
  }
  if (value === false) {
    return "Без релокации";
  }
  return "Релокация не указана";
}

export function experienceLabel(years: number | null): string {
  if (years === null) {
    return "Стаж не указан";
  }
  if (years === 0) {
    return "Без опыта";
  }
  return `Опыт от ${years} ${pluralRu(years, ["год", "года", "лет"])}`;
}

/** Адрес «Открыть оригинал»: `url` вакансии или первой публикации, где он есть. */
export function originalUrl(
  url: string | null,
  postings: readonly { url: string | null }[] | undefined,
): string | null {
  return url ?? postings?.find((posting) => posting.url)?.url ?? null;
}
