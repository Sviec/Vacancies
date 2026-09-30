import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { API_PREFIX, apiFetch, jsonBody } from "@/api/client";
import { queryKeys } from "@/api/query-keys";
import type {
  ResumeCreate,
  ResumeListResponse,
  ResumeRead,
  ResumeScoreResponse,
  ResumeUpdate,
} from "@/api/types";

const RESUMES = `${API_PREFIX}/resumes`;

function resumePath(id: string): string {
  return `${RESUMES}/${encodeURIComponent(id)}`;
}

export function useResumes() {
  return useQuery({
    queryKey: queryKeys.resumes.list,
    queryFn: ({ signal }) => apiFetch<ResumeListResponse>(RESUMES, { signal }),
  });
}

export function useResume(id: string) {
  return useQuery({
    queryKey: queryKeys.resumes.detail(id),
    queryFn: ({ signal }) => apiFetch<ResumeRead>(resumePath(id), { signal }),
    enabled: Boolean(id),
  });
}

/** Любое изменение резюме меняет список, его оценку и матчи в ленте. */
function useInvalidateAfterResumeChange() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.resumes.list }),
      queryClient.invalidateQueries({ queryKey: queryKeys.vacancies.all }),
    ]);
}

export function useCreateResume() {
  const invalidate = useInvalidateAfterResumeChange();
  return useMutation({
    mutationFn: (body: ResumeCreate) => apiFetch<ResumeRead>(RESUMES, jsonBody("POST", body)),
    onSuccess: invalidate,
  });
}

export function useUpdateResume() {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateAfterResumeChange();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ResumeUpdate }) =>
      apiFetch<ResumeRead>(resumePath(id), jsonBody("PATCH", body)),
    onSuccess: async (resume) => {
      queryClient.setQueryData(queryKeys.resumes.detail(resume.id), resume);
      await invalidate();
    },
  });
}

export function useDuplicateResume() {
  const invalidate = useInvalidateAfterResumeChange();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<ResumeRead>(`${resumePath(id)}/duplicate`, { method: "POST" }),
    onSuccess: invalidate,
  });
}

export function useDeleteResume() {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateAfterResumeChange();
  return useMutation({
    mutationFn: (id: string) => apiFetch<void>(resumePath(id), { method: "DELETE" }),
    onSuccess: async (_data, id) => {
      queryClient.removeQueries({ queryKey: queryKeys.resumes.detail(id) });
      await invalidate();
    },
  });
}

/** Запасной путь: пересчитать оценку, если у резюме `score === null`. */
export function useScoreResume() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<ResumeScoreResponse>(`${resumePath(id)}/score`, { method: "POST" }),
    onSuccess: async (_data, id) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.resumes.detail(id) });
    },
  });
}
