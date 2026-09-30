import { describe, expect, it } from "vitest";

import {
  clearFilters,
  countActiveFilters,
  DEFAULT_FILTERS,
  effectiveSort,
  feedKeyToApiParams,
  hasNarrowingFilters,
  parseFeedParams,
  publishedAfter,
  serializeFeedParams,
  toApiParams,
  toFeedKey,
  withFilters,
  withResume,
  withVacancy,
} from "@/features/vacancies/feed-state";
import type { FeedFilters, FeedState } from "@/features/vacancies/feed-state";

const NOW = new Date("2026-09-30T16:47:12.345Z");

const parse = (query: string) => parseFeedParams(new URLSearchParams(query));
const roundTrip = (state: FeedState) => parseFeedParams(serializeFeedParams(state));

const FULL: FeedFilters = {
  q: "python",
  experience_level: ["junior", "senior"],
  employment_type: ["full_time"],
  work_format: ["remote", "hybrid"],
  country: "Россия",
  city: "Москва",
  salary_min: 200000,
  salary_currency: "RUB",
  source: ["html_careerhub", "tg_it_jobs"],
  published: "7d",
  has_salary: true,
  relocation_support: false,
  show_hidden: true,
  saved: true,
  sort: "salary",
  page: 3,
};

describe("parseFeedParams", () => {
  it("пустой URL — значения по умолчанию", () => {
    expect(parse("")).toEqual({ filters: DEFAULT_FILTERS, resumeId: null, vacancyId: null });
  });

  it("читает все параметры", () => {
    const state = parse(
      "resume=r1&vacancy=v1&q=python&experience_level=senior&experience_level=junior" +
        "&employment_type=full_time&work_format=hybrid&work_format=remote&country=Россия&city=Москва" +
        "&salary_min=200000&salary_currency=rub&source=tg_it_jobs&source=html_careerhub" +
        "&published=7d&has_salary=true&relocation_support=false&show_hidden=true&saved=true" +
        "&sort=salary&page=3",
    );
    expect(state.resumeId).toBe("r1");
    expect(state.vacancyId).toBe("v1");
    // Порядок массивов — канонический, а не порядок в URL.
    expect(state.filters).toEqual(FULL);
  });

  it("отбрасывает мусор", () => {
    const { filters } = parse(
      "experience_level=guru&experience_level=middle&experience_level=middle&work_format=moon" +
        "&salary_min=-5&salary_currency=RUBLE&published=1y&has_salary=yes&show_hidden=1" +
        "&sort=random&page=0&country=%20%20&source=&source=a&source=a",
    );
    expect(filters.experience_level).toEqual(["middle"]);
    expect(filters.work_format).toEqual([]);
    expect(filters.salary_min).toBeNull();
    expect(filters.salary_currency).toBeNull();
    expect(filters.published).toBeNull();
    expect(filters.has_salary).toBeNull();
    expect(filters.show_hidden).toBe(false);
    expect(filters.sort).toBe("match");
    expect(filters.page).toBe(1);
    expect(filters.country).toBeNull();
    expect(filters.source).toEqual(["a"]);
  });

  it("page ≥ 1, дробные и нечисловые страницы — 1", () => {
    expect(parse("page=2").filters.page).toBe(2);
    expect(parse("page=-1").filters.page).toBe(1);
    expect(parse("page=1.5").filters.page).toBe(1);
    expect(parse("page=abc").filters.page).toBe(1);
    expect(parse("salary_min=1e5").filters.salary_min).toBeNull();
  });
});

describe("serializeFeedParams", () => {
  it("дефолты в URL не пишутся", () => {
    const state: FeedState = { filters: DEFAULT_FILTERS, resumeId: null, vacancyId: null };
    expect(serializeFeedParams(state).toString()).toBe("");
  });

  it("туда-обратно без потерь", () => {
    const state: FeedState = { filters: FULL, resumeId: "r1", vacancyId: "v1" };
    expect(roundTrip(state)).toEqual(state);
  });

  it("имена параметров совпадают с API, кроме собственных", () => {
    const params = serializeFeedParams({ filters: FULL, resumeId: "r1", vacancyId: "v1" });
    expect([...new Set(params.keys())].sort()).toEqual(
      [
        "city",
        "country",
        "employment_type",
        "experience_level",
        "has_salary",
        "page",
        "published",
        "q",
        "relocation_support",
        "resume",
        "salary_currency",
        "salary_min",
        "saved",
        "show_hidden",
        "sort",
        "source",
        "vacancy",
        "work_format",
      ].sort(),
    );
    expect(params.getAll("work_format")).toEqual(["remote", "hybrid"]);
  });

  it("булевы false пишутся явно, show_hidden/saved — только true", () => {
    const params = serializeFeedParams({
      filters: { ...DEFAULT_FILTERS, has_salary: false, relocation_support: false },
      resumeId: null,
      vacancyId: null,
    });
    expect(params.toString()).toBe("has_salary=false&relocation_support=false");
  });
});

describe("изменения состояния", () => {
  const base: FeedState = { filters: { ...FULL }, resumeId: "r1", vacancyId: null };

  it("любая смена фильтра сбрасывает страницу", () => {
    expect(withFilters(base, { city: null }).filters.page).toBe(1);
    expect(withFilters(base, { sort: "date" }).filters.page).toBe(1);
    expect(withFilters(base, { saved: false }).filters.page).toBe(1);
  });

  it("смена страницы страницу сохраняет", () => {
    expect(withFilters(base, { page: 5 }).filters.page).toBe(5);
  });

  it("смена резюме сбрасывает страницу, фильтры не трогает", () => {
    const next = withResume(base, "r2");
    expect(next.resumeId).toBe("r2");
    expect(next.filters).toEqual({ ...FULL, page: 1 });
  });

  it("открытие вакансии не трогает фильтры", () => {
    expect(withVacancy(base, "v9")).toEqual({ ...base, vacancyId: "v9" });
  });

  it("сброс оставляет вкладку и сортировку", () => {
    const next = clearFilters(base);
    expect(next.filters).toEqual({ ...DEFAULT_FILTERS, sort: "salary", saved: true });
    expect(next.resumeId).toBe("r1");
  });
});

describe("счётчик фильтров", () => {
  it("по умолчанию — 0, поиск и вкладка не считаются", () => {
    expect(countActiveFilters(DEFAULT_FILTERS)).toBe(0);
    expect(countActiveFilters({ ...DEFAULT_FILTERS, q: "go", saved: true, sort: "date", page: 4 })).toBe(0);
  });

  it("каждая группа — одна единица", () => {
    expect(countActiveFilters(FULL)).toBe(12);
    expect(countActiveFilters({ ...DEFAULT_FILTERS, work_format: ["remote", "office"] })).toBe(1);
    expect(countActiveFilters({ ...DEFAULT_FILTERS, has_salary: false })).toBe(1);
  });

  it("поиск сужает выдачу", () => {
    expect(hasNarrowingFilters(DEFAULT_FILTERS)).toBe(false);
    expect(hasNarrowingFilters({ ...DEFAULT_FILTERS, q: "go" })).toBe(true);
    expect(hasNarrowingFilters({ ...DEFAULT_FILTERS, q: "   " })).toBe(false);
  });
});

describe("effectiveSort", () => {
  it("match без резюме и relevance без запроса — date", () => {
    expect(effectiveSort(DEFAULT_FILTERS, null)).toBe("date");
    expect(effectiveSort(DEFAULT_FILTERS, "r1")).toBe("match");
    expect(effectiveSort({ ...DEFAULT_FILTERS, sort: "relevance" }, "r1")).toBe("date");
    expect(effectiveSort({ ...DEFAULT_FILTERS, sort: "relevance", q: "go" }, null)).toBe("relevance");
    expect(effectiveSort({ ...DEFAULT_FILTERS, sort: "salary" }, null)).toBe("salary");
  });
});

describe("toApiParams", () => {
  it("по умолчанию: дата, первая страница, скрытые исключены", () => {
    expect(toApiParams(DEFAULT_FILTERS, null, NOW)).toEqual({
      sort: "date",
      page: 1,
      page_size: 20,
      exclude_hidden: true,
      saved_only: false,
    });
  });

  it("все фильтры сразу", () => {
    expect(toApiParams(FULL, "r1", NOW)).toEqual({
      q: "python",
      resume_id: "r1",
      experience_level: ["junior", "senior"],
      employment_type: ["full_time"],
      work_format: ["remote", "hybrid"],
      country: "Россия",
      city: "Москва",
      salary_min: 200000,
      salary_currency: "RUB",
      source: ["html_careerhub", "tg_it_jobs"],
      published_after: "2026-09-23T16:00:00.000Z",
      has_salary: true,
      relocation_support: false,
      exclude_hidden: false,
      saved_only: true,
      sort: "salary",
      page: 3,
      page_size: 20,
    });
  });

  it("remote + с зарплатой + USD + match при выбранном резюме", () => {
    const filters = { ...DEFAULT_FILTERS, work_format: ["remote" as const], has_salary: true, salary_currency: "USD" };
    expect(toApiParams(filters, "r1", NOW)).toEqual({
      resume_id: "r1",
      work_format: ["remote"],
      has_salary: true,
      salary_currency: "USD",
      sort: "match",
      page: 1,
      page_size: 20,
      exclude_hidden: true,
      saved_only: false,
    });
  });

  it("нулевая зарплата и has_salary=false передаются", () => {
    const params = toApiParams({ ...DEFAULT_FILTERS, salary_min: 0, has_salary: false }, null, NOW);
    expect(params.salary_min).toBe(0);
    expect(params.has_salary).toBe(false);
  });

  it("пресеты даты публикации округляются вниз до часа", () => {
    expect(publishedAfter("3d", NOW)).toBe("2026-09-27T16:00:00.000Z");
    expect(publishedAfter("7d", NOW)).toBe("2026-09-23T16:00:00.000Z");
    expect(publishedAfter("30d", NOW)).toBe("2026-08-31T16:00:00.000Z");
  });

  it("ключ запроса хранит пресет, а не дату, и не зависит от времени", () => {
    const filters = { ...DEFAULT_FILTERS, published: "3d" as const };
    const key = toFeedKey(filters, null);
    expect(key).not.toHaveProperty("published_after");
    expect(key.published).toBe("3d");
    expect(toFeedKey(filters, null)).toEqual(key);
    const later = new Date(NOW.getTime() + 2 * 60 * 60 * 1000);
    expect(feedKeyToApiParams(key, later).published_after).toBe("2026-09-27T18:00:00.000Z");
    expect(feedKeyToApiParams(key, later)).not.toHaveProperty("published");
  });
});
