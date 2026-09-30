import { useCallback, useEffect } from "react";

import { useResumes } from "@/api/resumes";
import type { ResumeListItem } from "@/api/types";
import { withResume } from "@/features/vacancies/feed-state";
import type { FeedState } from "@/features/vacancies/feed-state";
import type { UpdateFeed } from "@/features/vacancies/use-feed-params";
import { readStorage, writeStorage } from "@/lib/storage";

export const ACTIVE_RESUME_KEY = "vacancies.activeResumeId";

/**
 * Активное резюме ленты: `?resume=`, затем выбор из localStorage, затем
 * основное. Id, которого нет в списке (резюме удалили), пропускается.
 * TODO: активное резюме — только выбор в интерфейсе (URL и localStorage),
 * флаг `is_primary` на сервере при этом не меняется.
 */
export function pickActiveResume(
  items: readonly ResumeListItem[],
  urlId: string | null,
  storedId: string | null,
): string | null {
  const exists = (id: string | null): id is string => id !== null && items.some((item) => item.id === id);
  if (exists(urlId)) {
    return urlId;
  }
  if (exists(storedId)) {
    return storedId;
  }
  // Основное резюме на сервере есть всегда, пока есть хоть одно; первое — страховка.
  return (items.find((item) => item.is_primary) ?? items[0])?.id ?? null;
}

export function useActiveResume(state: FeedState, update: UpdateFeed) {
  const resumes = useResumes();
  const items = resumes.data?.items;
  const activeId = items ? pickActiveResume(items, state.resumeId, readStorage(ACTIVE_RESUME_KEY)) : null;
  const active = items?.find((item) => item.id === activeId) ?? null;
  // Лента ждёт списка резюме: иначе первая выдача ушла бы без процента и сразу
  // перезапросилась бы. При ошибке списка лента работает без резюме.
  const resolved = !resumes.isPending;

  useEffect(() => {
    if (!items) {
      return;
    }
    if (activeId !== null) {
      writeStorage(ACTIVE_RESUME_KEY, activeId);
    }
    if (state.resumeId !== null && state.resumeId !== activeId) {
      update((current) => ({ ...current, resumeId: activeId }), { replace: true });
    }
  }, [items, activeId, state.resumeId, update]);

  const select = useCallback(
    (id: string) => {
      writeStorage(ACTIVE_RESUME_KEY, id);
      update((current) => withResume(current, id));
    },
    [update],
  );

  return { resumes, items: items ?? [], activeId, active, resolved, select };
}
