/**
 * Состояние ленты «Вакансии» в URL: разбор, сериализация и перевод в
 * query-параметры `GET /api/v1/vacancies`. Чистые функции без React.
 *
 * Имена в URL совпадают с API, кроме `published` (пресет вместо даты),
 * `show_hidden`, `saved`, `resume` и `vacancy`. Значения по умолчанию в URL
 * не пишутся.
 */

import type {
  EmploymentType,
  ExperienceLevel,
  VacancyListParams,
  VacancySort,
  WorkFormat,
} from "@/api/types";

export const PAGE_SIZE = 20;

export const EXPERIENCE_LEVELS: readonly ExperienceLevel[] = [
  "intern",
  "junior",
  "middle",
  "senior",
  "lead",
  "unknown",
];
export const EMPLOYMENT_TYPES: readonly EmploymentType[] = [
  "full_time",
  "part_time",
  "contract",
  "internship",
  "unknown",
];
export const WORK_FORMATS: readonly WorkFormat[] = ["remote", "hybrid", "office", "unknown"];
export const FEED_SORTS: readonly VacancySort[] = ["match", "relevance", "date", "salary"];

export type PublishedPreset = "3d" | "7d" | "30d";
export const PUBLISHED_PRESETS: readonly PublishedPreset[] = ["3d", "7d", "30d"];

// TODO: пресеты даты публикации — 3, 7 и 30 дней; граница округляется вниз до часа.
const PUBLISHED_DAYS: Record<PublishedPreset, number> = { "3d": 3, "7d": 7, "30d": 30 };

export interface FeedFilters {
  q: string;
  experience_level: ExperienceLevel[];
  employment_type: EmploymentType[];
  work_format: WorkFormat[];
  country: string | null;
  city: string | null;
  salary_min: number | null;
  salary_currency: string | null;
  source: string[];
  published: PublishedPreset | null;
  has_salary: boolean | null;
  relocation_support: boolean | null;
  show_hidden: boolean;
  saved: boolean;
  sort: VacancySort;
  page: number;
}

export interface FeedState {
  filters: FeedFilters;
  resumeId: string | null;
  vacancyId: string | null;
}

export const DEFAULT_FILTERS: FeedFilters = {
  q: "",
  experience_level: [],
  employment_type: [],
  work_format: [],
  country: null,
  city: null,
  salary_min: null,
  salary_currency: null,
  source: [],
  published: null,
  has_salary: null,
  relocation_support: null,
  show_hidden: false,
  saved: false,
  sort: "match",
  page: 1,
};

const CURRENCY_RE = /^[A-Z]{3}$/;
const INT_RE = /^\d+$/;

function text(params: URLSearchParams, key: string): string | null {
  const value = params.get(key)?.trim();
  return value ? value : null;
}

/** Значения из белого списка без повторов, в порядке списка. */
function enumList<T extends string>(params: URLSearchParams, key: string, allowed: readonly T[]): T[] {
  const values = new Set(params.getAll(key));
  return allowed.filter((item) => values.has(item));
}

function enumValue<T extends string>(value: string | null, allowed: readonly T[]): T | null {
  return value !== null && (allowed as readonly string[]).includes(value) ? (value as T) : null;
}

function bool(params: URLSearchParams, key: string): boolean | null {
  const value = params.get(key);
  return value === "true" ? true : value === "false" ? false : null;
}

function nonNegativeInt(value: string | null): number | null {
  if (value === null || !INT_RE.test(value)) {
    return null;
  }
  const number = Number(value);
  return Number.isSafeInteger(number) ? number : null;
}

/** Разобрать URL ленты; значения вне допустимых отбрасываются. */
export function parseFeedParams(params: URLSearchParams): FeedState {
  const currency = text(params, "salary_currency")?.toUpperCase() ?? null;
  const page = nonNegativeInt(params.get("page"));
  const sources = [...new Set(params.getAll("source").map((item) => item.trim()).filter(Boolean))].sort();
  return {
    filters: {
      q: params.get("q")?.trim() ?? "",
      experience_level: enumList(params, "experience_level", EXPERIENCE_LEVELS),
      employment_type: enumList(params, "employment_type", EMPLOYMENT_TYPES),
      work_format: enumList(params, "work_format", WORK_FORMATS),
      country: text(params, "country"),
      city: text(params, "city"),
      salary_min: nonNegativeInt(params.get("salary_min")),
      salary_currency: currency !== null && CURRENCY_RE.test(currency) ? currency : null,
      source: sources,
      published: enumValue(params.get("published"), PUBLISHED_PRESETS),
      has_salary: bool(params, "has_salary"),
      relocation_support: bool(params, "relocation_support"),
      show_hidden: params.get("show_hidden") === "true",
      saved: params.get("saved") === "true",
      sort: enumValue(params.get("sort"), FEED_SORTS) ?? DEFAULT_FILTERS.sort,
      page: page !== null && page >= 1 ? page : 1,
    },
    resumeId: text(params, "resume"),
    vacancyId: text(params, "vacancy"),
  };
}

/** Состояние → URL; дефолтные значения не пишутся. */
export function serializeFeedParams(state: FeedState): URLSearchParams {
  const { filters: f } = state;
  const params = new URLSearchParams();
  const set = (key: string, value: string | null) => {
    if (value !== null && value !== "") {
      params.set(key, value);
    }
  };
  set("resume", state.resumeId);
  set("q", f.q.trim());
  for (const key of ["experience_level", "employment_type", "work_format", "source"] as const) {
    for (const value of f[key]) {
      params.append(key, value);
    }
  }
  set("country", f.country);
  set("city", f.city);
  set("salary_min", f.salary_min === null ? null : String(f.salary_min));
  set("salary_currency", f.salary_currency);
  set("published", f.published);
  set("has_salary", f.has_salary === null ? null : String(f.has_salary));
  set("relocation_support", f.relocation_support === null ? null : String(f.relocation_support));
  set("show_hidden", f.show_hidden ? "true" : null);
  set("saved", f.saved ? "true" : null);
  set("sort", f.sort === DEFAULT_FILTERS.sort ? null : f.sort);
  set("page", f.page > 1 ? String(f.page) : null);
  set("vacancy", state.vacancyId);
  return params;
}

/** Изменить фильтры. Любая правка, кроме самой страницы, сбрасывает `page` в 1. */
export function withFilters(state: FeedState, patch: Partial<FeedFilters>): FeedState {
  return {
    ...state,
    filters: { ...state.filters, ...patch, page: patch.page ?? 1 },
  };
}

/** Смена резюме тоже возвращает на первую страницу. */
export function withResume(state: FeedState, resumeId: string | null): FeedState {
  return { ...state, resumeId, filters: { ...state.filters, page: 1 } };
}

export function withVacancy(state: FeedState, vacancyId: string | null): FeedState {
  return { ...state, vacancyId };
}

/** «Сбросить всё»: фильтры панели и поиск; вкладка и сортировка остаются. */
export function clearFilters(state: FeedState): FeedState {
  return withFilters(state, {
    ...DEFAULT_FILTERS,
    sort: state.filters.sort,
    saved: state.filters.saved,
  });
}

/** Сколько фильтров панели активно (бейдж на кнопке «Фильтры» в мобильной раскладке). */
export function countActiveFilters(f: FeedFilters): number {
  const flags = [
    f.experience_level.length > 0,
    f.employment_type.length > 0,
    f.work_format.length > 0,
    f.country !== null,
    f.city !== null,
    f.salary_min !== null,
    f.salary_currency !== null,
    f.source.length > 0,
    f.published !== null,
    f.has_salary !== null,
    f.relocation_support !== null,
    f.show_hidden,
  ];
  return flags.filter(Boolean).length;
}

/** Фильтры панели или поиск сужают выдачу — пустой результат объясняется ими. */
export function hasNarrowingFilters(f: FeedFilters): boolean {
  return countActiveFilters(f) > 0 || f.q.trim() !== "";
}

/** Фактическая сортировка: `match` без резюме и `relevance` без запроса дают `date`. */
export function effectiveSort(f: FeedFilters, resumeId: string | null): VacancySort {
  if (f.sort === "match" && resumeId === null) {
    return "date";
  }
  if (f.sort === "relevance" && f.q.trim() === "") {
    return "date";
  }
  return f.sort;
}

/**
 * Ключ запроса ленты: API-параметры, но вместо `published_after` — пресет.
 * Дата вычисляется в `queryFn` (`feedKeyToApiParams`), иначе ключ менялся бы
 * на каждом рендере.
 */
export type FeedKey = Omit<VacancyListParams, "published_after"> & {
  published?: PublishedPreset;
};

export function toFeedKey(f: FeedFilters, resumeId: string | null): FeedKey {
  const key: FeedKey = {
    sort: effectiveSort(f, resumeId),
    page: f.page,
    page_size: PAGE_SIZE,
    exclude_hidden: !f.show_hidden,
    saved_only: f.saved,
  };
  const q = f.q.trim();
  if (q) key.q = q;
  if (resumeId !== null) key.resume_id = resumeId;
  if (f.experience_level.length) key.experience_level = f.experience_level;
  if (f.employment_type.length) key.employment_type = f.employment_type;
  if (f.work_format.length) key.work_format = f.work_format;
  if (f.country !== null) key.country = f.country;
  if (f.city !== null) key.city = f.city;
  if (f.salary_min !== null) key.salary_min = f.salary_min;
  if (f.salary_currency !== null) key.salary_currency = f.salary_currency;
  if (f.source.length) key.source = f.source;
  if (f.published !== null) key.published = f.published;
  if (f.has_salary !== null) key.has_salary = f.has_salary;
  if (f.relocation_support !== null) key.relocation_support = f.relocation_support;
  return key;
}

const HOUR_MS = 60 * 60 * 1000;
const DAY_MS = 24 * HOUR_MS;

/** Граница `published_after`: `now − N дней`, округлённая вниз до часа (UTC). */
export function publishedAfter(preset: PublishedPreset, now: Date): string {
  const border = now.getTime() - PUBLISHED_DAYS[preset] * DAY_MS;
  return new Date(Math.floor(border / HOUR_MS) * HOUR_MS).toISOString();
}

export function feedKeyToApiParams(key: FeedKey, now: Date): VacancyListParams {
  const { published, ...params } = key;
  return published ? { ...params, published_after: publishedAfter(published, now) } : params;
}

export function toApiParams(f: FeedFilters, resumeId: string | null, now: Date): VacancyListParams {
  return feedKeyToApiParams(toFeedKey(f, resumeId), now);
}
