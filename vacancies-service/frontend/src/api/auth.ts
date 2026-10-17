import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { API_PREFIX, apiFetch, jsonBody } from "@/api/client";

export interface CurrentUser {
  id: string;
  email: string;
}

const AUTH = `${API_PREFIX}/auth`;

export function useCurrentUser() {
  return useQuery({
    queryKey: ["auth", "me"],
    queryFn: ({ signal }) => apiFetch<CurrentUser>(`${AUTH}/me`, { signal }),
  });
}

export function useRegister() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; password: string }) =>
      apiFetch<CurrentUser>(`${AUTH}/register`, jsonBody("POST", body)),
    onSuccess: (user) => {
      queryClient.setQueryData(["auth", "me"], user);
    },
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; password: string }) =>
      apiFetch<CurrentUser>(`${AUTH}/login`, jsonBody("POST", body)),
    onSuccess: (user) => {
      queryClient.setQueryData(["auth", "me"], user);
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<void>(`${AUTH}/logout`, { method: "POST" }),
    onSuccess: () => {
      queryClient.clear();
    },
  });
}
