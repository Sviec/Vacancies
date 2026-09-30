import { useCallback, useEffect, useMemo, useState } from "react";
import { useBlocker } from "react-router";

import { ApiError } from "@/api/client";
import { useUpdateResume } from "@/api/resumes";
import type { ResumeRead } from "@/api/types";
import { useToast } from "@/components/ui/Toaster";
import type { ResumeDraft } from "@/features/editor/draft";
import {
  diffPayload,
  fromResume,
  mapServerErrors,
  toPayload,
  validateDraft,
} from "@/features/editor/draft";

export type SaveStatus = "saved" | "dirty" | "saving" | "invalid" | "error";

interface UseSaveResumeArgs {
  resume: ResumeRead;
  draft: ResumeDraft;
  setFieldErrors: (errors: Record<string, string>) => void;
  onSaved: (resume: ResumeRead) => void;
}

interface UseSaveResumeResult {
  status: SaveStatus;
  dirty: boolean;
  saving: boolean;
  save: () => void;
  retry: () => void;
}

/**
 * Явное сохранение на сервер: кнопка «Сохранить» и Ctrl/Cmd+S.
 * Автосохранения PATCH нет — только локальный черновик.
 */
export function useSaveResume({
  resume,
  draft,
  setFieldErrors,
  onSaved,
}: UseSaveResumeArgs): UseSaveResumeResult {
  const toast = useToast();
  const update = useUpdateResume();
  /** Снимок payload на момент ошибки — сбрасывается, когда черновик изменился. */
  const [errorSnapshot, setErrorSnapshot] = useState<string | null>(null);

  const serverPayload = useMemo(() => toPayload(fromResume(resume)), [resume]);
  const draftPayload = useMemo(() => toPayload(draft), [draft]);
  const draftKey = useMemo(() => JSON.stringify(draftPayload), [draftPayload]);
  const diff = useMemo(
    () => diffPayload(serverPayload, draftPayload),
    [serverPayload, draftPayload],
  );
  const dirty = Object.keys(diff).length > 0;
  const clientErrors = useMemo(() => validateDraft(draft, new Date()), [draft]);
  const hasClientErrors = Object.keys(clientErrors).length > 0;
  const holdError = errorSnapshot !== null && errorSnapshot === draftKey;

  const status: SaveStatus = update.isPending
    ? "saving"
    : holdError
      ? "error"
      : !dirty
        ? "saved"
        : hasClientErrors
          ? "invalid"
          : "dirty";

  const save = useCallback(() => {
    if (hasClientErrors) {
      setFieldErrors(clientErrors);
      toast({ message: "Исправьте ошибки в форме перед сохранением", tone: "danger" });
      return;
    }
    if (!dirty) {
      return;
    }
    setFieldErrors({});
    setErrorSnapshot(null);
    update.mutate(
      { id: resume.id, body: diff },
      {
        onSuccess: (next) => {
          onSaved(next);
          toast({ message: "Сохранено" });
        },
        onError: (error) => {
          setErrorSnapshot(draftKey);
          if (error instanceof ApiError && error.status === 422) {
            setFieldErrors(mapServerErrors(error));
          }
          toast({
            message: error instanceof ApiError ? error.message : "Ошибка сохранения",
            tone: "danger",
          });
        },
      },
    );
  }, [
    clientErrors,
    draftKey,
    diff,
    dirty,
    hasClientErrors,
    onSaved,
    resume.id,
    setFieldErrors,
    toast,
    update,
  ]);

  const retry = useCallback(() => {
    setErrorSnapshot(null);
    save();
  }, [save]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        save();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [save]);

  useEffect(() => {
    if (!dirty && !update.isPending) {
      return;
    }
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty, update.isPending]);

  const blocker = useBlocker(dirty || update.isPending);
  useEffect(() => {
    if (blocker.state !== "blocked") {
      return;
    }
    const leave = window.confirm(
      "Есть несохранённые на сервере изменения. Черновик останется в браузере. Уйти со страницы?",
    );
    if (leave) {
      blocker.proceed();
    } else {
      blocker.reset();
    }
  }, [blocker]);

  return {
    status,
    dirty,
    saving: update.isPending,
    save,
    retry,
  };
}

export function saveStatusLabel(status: SaveStatus): string {
  switch (status) {
    case "saved":
      return "Все изменения сохранены";
    case "dirty":
      return "Есть несохранённые изменения (сохранены локально)";
    case "saving":
      return "Сохранение…";
    case "invalid":
      return "Есть ошибки — не сохранено";
    case "error":
      return "Ошибка сохранения";
  }
}
