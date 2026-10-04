import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { API_PREFIX, apiFetch, buildQuery } from "@/api/client";
import { queryKeys } from "@/api/query-keys";
import type {
  ParseRunListResponse,
  RunListParams,
  SourceListResponse,
  SourceRunAccepted,
} from "@/api/types";

const SOURCES = `${API_PREFIX}/sources`;

export function useSources() {
  return useQuery({
    queryKey: queryKeys.sources.list,
    queryFn: ({ signal }) => apiFetch<SourceListResponse>(SOURCES, { signal }),
  });
}

export function useRuns(params: RunListParams) {
  return useQuery({
    queryKey: queryKeys.sources.runs(params),
    queryFn: ({ signal }) =>
      apiFetch<ParseRunListResponse>(`${SOURCES}/runs${buildQuery(params)}`, { signal }),
  });
}

export function useRunSource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sourceId: string) =>
      apiFetch<SourceRunAccepted>(`${SOURCES}/${sourceId}/run`, { method: "POST" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
  });
}
