import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/api/client";
import { queryKeys } from "@/api/query-keys";
import type { HealthResponse } from "@/api/types";

// TODO: /health отдаёт 503 при деградации — apiFetch бросает ApiError, и
// индикатор показывает «недоступен», не различая, какая зависимость упала.
export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: ({ signal }) => apiFetch<HealthResponse>("/health", { signal }),
    // Один запрос при загрузке страницы, без опроса.
    staleTime: Infinity,
  });
}
