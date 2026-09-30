/**
 * Ключи react-query в одном месте: инвалидация по префиксу
 * (`["vacancies"]`, `["resumes"]`) задевает все производные запросы.
 */

import type { RunListParams, VacancyListParams } from "@/api/types";

export const queryKeys = {
  health: ["health"] as const,
  vacancies: {
    all: ["vacancies"] as const,
    lists: ["vacancies", "list"] as const,
    list: (params: VacancyListParams) => ["vacancies", "list", params] as const,
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
