/**
 * Ключи react-query в одном месте: инвалидация по префиксу
 * (`["vacancies"]`, `["resumes"]`) задевает все производные запросы.
 */

import type { RunListParams } from "@/api/types";

/** Ключ ленты: параметры API или их стабильное представление (см. `useVacancyFeed`). */
export type ListKeyParams = Readonly<Record<string, unknown>>;

export const queryKeys = {
  health: ["health"] as const,
  vacancies: {
    all: ["vacancies"] as const,
    lists: ["vacancies", "list"] as const,
    list: (params: ListKeyParams) => ["vacancies", "list", params] as const,
    /** Все детали одной вакансии — с любым резюме. */
    detailsOf: (id: string) => ["vacancies", "detail", id] as const,
    detail: (id: string, resumeId: string | null) =>
      ["vacancies", "detail", id, resumeId] as const,
  },
  filtersMeta: ["filters-meta"] as const,
  resumes: {
    all: ["resumes"] as const,
    list: ["resumes", "list"] as const,
    detail: (id: string) => ["resumes", "detail", id] as const,
  },
  sources: {
    list: ["sources", "list"] as const,
    runs: (params: RunListParams) => ["sources", "runs", params] as const,
  },
};
