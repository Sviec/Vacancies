import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";

import { API_PREFIX, apiFetch, buildQuery } from "@/api/client";
import { queryKeys } from "@/api/query-keys";
import type { ListKeyParams } from "@/api/query-keys";
import type {
  FiltersMeta,
  UserAction,
  VacancyDetail,
  VacancyListItem,
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

/**
 * Лента. Ключ и параметры разделены: в ключе может лежать стабильное
 * представление (пресет даты), а `resolveParams` превращает его в запрос в
 * момент загрузки. Без `placeholderData`: смена ключа показывает skeleton.
 */
export function useVacancyFeed<K extends ListKeyParams>(
  key: K,
  resolveParams: (key: K) => VacancyListParams,
  enabled = true,
) {
  return useQuery({
    queryKey: queryKeys.vacancies.list(key),
    queryFn: ({ signal }) => fetchVacancies(resolveParams(key), signal),
    enabled,
  });
}

/**
 * Деталь вакансии. `placeholder` — карточка из кэша ленты для первого кадра
 * drawer, пока грузится полный ответ (не пишется в кэш как «настоящие» данные).
 */
export function useVacancy(
  id: string | null,
  resumeId: string | null,
  placeholder?: VacancyListItem | null,
) {
  const stub: VacancyDetail | undefined =
    placeholder && id !== null && placeholder.id === id
      ? {
          ...placeholder,
          description_clean: "",
          url: null,
          relocation_support: null,
          experience_min_years: null,
          experience_level: "unknown",
          employment_type: "unknown",
          education_required: null,
          languages: [],
          last_seen_at: new Date(0).toISOString(),
          source_type: "api",
          is_active: true,
          postings: [],
        }
      : undefined;

  return useQuery({
    queryKey: queryKeys.vacancies.detail(id ?? "", resumeId),
    queryFn: ({ signal }) =>
      apiFetch<VacancyDetail>(
        `${VACANCIES}/${encodeURIComponent(id ?? "")}${buildQuery({ resume_id: resumeId })}`,
        { signal },
      ),
    enabled: id !== null,
    placeholderData: stub,
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

export interface VacancyActionInput {
  id: string;
  action: UserAction;
  on: boolean;
}

/** Найти карточку в закэшированных страницах ленты (первичный кадр drawer). */
export function findCachedCard(queryClient: QueryClient, id: string): VacancyListItem | null {
  for (const [, page] of queryClient.getQueriesData<VacancyListResponse>({
    queryKey: queryKeys.vacancies.lists,
  })) {
    const card = page?.items.find((item) => item.id === id);
    if (card) {
      return card;
    }
  }
  return null;
}

/** Записать актуальные действия во все закэшированные ленты и детали. */
export function applyUserState(queryClient: QueryClient, state: VacancyUserState): void {
  queryClient.setQueriesData<VacancyListResponse>({ queryKey: queryKeys.vacancies.lists }, (page) =>
    page && page.items.some((item) => item.id === state.vacancy_id)
      ? {
          ...page,
          items: page.items.map((item) =>
            item.id === state.vacancy_id ? { ...item, user_actions: state.actions } : item,
          ),
        }
      : page,
  );
  queryClient.setQueriesData<VacancyDetail>(
    { queryKey: queryKeys.vacancies.detailsOf(state.vacancy_id) },
    (detail) => (detail ? { ...detail, user_actions: state.actions } : detail),
  );
}

/**
 * Действие над вакансией. Ответ сразу пишется в кэш; `saved` и `hidden`
 * меняют состав выдачи (вкладка «Сохранённые», исключение скрытых), поэтому
 * ленты после них перезапрашиваются.
 */
export function useVacancyAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action, on }: VacancyActionInput) => setVacancyAction(id, action, on),
    onSuccess: async (state, { action }) => {
      applyUserState(queryClient, state);
      if (action === "saved" || action === "hidden") {
        void queryClient.invalidateQueries({ queryKey: queryKeys.vacancies.lists });
      }
    },
  });
}
