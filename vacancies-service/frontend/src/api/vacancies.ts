import { useQuery } from "@tanstack/react-query";

import { API_PREFIX, apiFetch, buildQuery } from "@/api/client";
import { queryKeys } from "@/api/query-keys";
import type {
  FiltersMeta,
  UserAction,
  VacancyDetail,
  VacancyListParams,
  VacancyListResponse,
  VacancyUserState,
} from "@/api/types";

const VACANCIES = `${API_PREFIX}/vacancies`;

export function fetchVacancies(
  params: VacancyListParams,
  signal?: AbortSignal,
): Promise<VacancyListResponse> {
  return apiFetch<VacancyListResponse>(`${VACANCIES}${buildQuery(params)}`, { signal });
}

export function useVacancyFeed(params: VacancyListParams) {
  return useQuery({
    queryKey: queryKeys.vacancies.list(params),
    queryFn: ({ signal }) => fetchVacancies(params, signal),
  });
}

export function useVacancy(id: string | null, resumeId: string | null) {
  return useQuery({
    queryKey: queryKeys.vacancies.detail(id ?? "", resumeId),
    queryFn: ({ signal }) =>
      apiFetch<VacancyDetail>(
        `${VACANCIES}/${encodeURIComponent(id ?? "")}${buildQuery({ resume_id: resumeId })}`,
        { signal },
      ),
    enabled: id !== null,
  });
}

export function useFiltersMeta() {
  return useQuery({
    queryKey: queryKeys.filtersMeta,
    queryFn: ({ signal }) => apiFetch<FiltersMeta>(`${VACANCIES}/filters/meta`, { signal }),
    staleTime: 5 * 60_000,
  });
}

/** Поставить (`on=true`) или снять действие пользователя над вакансией. */
export function setVacancyAction(
  id: string,
  action: UserAction,
  on: boolean,
): Promise<VacancyUserState> {
  const base = `${VACANCIES}/${encodeURIComponent(id)}/action`;
  return on
    ? apiFetch<VacancyUserState>(base, {
        method: "POST",
        body: JSON.stringify({ action }),
      })
    : apiFetch<VacancyUserState>(`${base}/${action}`, { method: "DELETE" });
}
