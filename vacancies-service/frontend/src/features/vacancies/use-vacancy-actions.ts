import { useCallback } from "react";

import { useVacancyAction } from "@/api/vacancies";
import type { VacancyActionInput } from "@/api/vacancies";
import type { UserAction } from "@/api/types";
import { describeError } from "@/components/ui/ErrorState";
import { useToast } from "@/components/ui/Toaster";

export interface VacancyActions {
  toggleSaved: (id: string, actions: readonly UserAction[] | undefined) => void;
  /** Скрыть; `onHidden` — например, закрыть drawer. Тост предлагает вернуть. */
  hide: (id: string, onHidden?: () => void) => void;
  unhide: (id: string) => void;
  /** Id вакансии, над которой сейчас выполняется действие. */
  pendingId: string | null;
}

/** Действия над вакансией с тостами: ошибка — текстом API, скрытие — с «Вернуть». */
export function useVacancyActions(): VacancyActions {
  const mutation = useVacancyAction();
  const { mutate } = mutation;
  const toast = useToast();

  const run = useCallback(
    (input: VacancyActionInput, onSuccess?: () => void) => {
      mutate(input, {
        onSuccess,
        onError: (error) => toast({ message: describeError(error), tone: "danger" }),
      });
    },
    [mutate, toast],
  );

  const unhide = useCallback(
    (id: string) => run({ id, action: "hidden", on: false }, () => toast({ message: "Вакансия возвращена в ленту" })),
    [run, toast],
  );

  const hide = useCallback(
    (id: string, onHidden?: () => void) =>
      run({ id, action: "hidden", on: true }, () => {
        onHidden?.();
        toast({ message: "Вакансия скрыта", action: { label: "Вернуть", onClick: () => unhide(id) } });
      }),
    [run, toast, unhide],
  );

  const toggleSaved = useCallback(
    (id: string, actions: readonly UserAction[] | undefined) => {
      const saved = actions?.includes("saved") ?? false;
      run({ id, action: "saved", on: !saved });
    },
    [run],
  );

  return {
    toggleSaved,
    hide,
    unhide,
    pendingId: mutation.isPending ? (mutation.variables?.id ?? null) : null,
  };
}
