import { useEffect, useRef, useState } from "react";

import type { ResumeRead } from "@/api/types";
import type { ResumeDraft, StoredResumeDraft } from "@/features/editor/draft";
import {
  draftMatchesResume,
  draftStorageKey,
  fromResume,
  isStoredResumeDraft,
} from "@/features/editor/draft";
import { readStorageJson, removeStorage, writeStorageJson } from "@/lib/storage";

const DEBOUNCE_MS = 500;

export type DraftBanner = null | { kind: "restore"; stale: boolean };

interface LocalState {
  draft: ResumeDraft;
  baseUpdatedAt: string;
  banner: DraftBanner;
}

function initState(resume: ResumeRead): LocalState {
  const stored = readStorageJson<unknown>(draftStorageKey(resume.id));
  if (isStoredResumeDraft(stored) && !draftMatchesResume(stored.draft, resume)) {
    return {
      draft: stored.draft,
      baseUpdatedAt: stored.baseUpdatedAt,
      banner: { kind: "restore", stale: stored.baseUpdatedAt !== resume.updated_at },
    };
  }
  if (isStoredResumeDraft(stored) && draftMatchesResume(stored.draft, resume)) {
    removeStorage(draftStorageKey(resume.id));
  }
  return {
    draft: fromResume(resume),
    baseUpdatedAt: resume.updated_at,
    banner: null,
  };
}

interface UseLocalDraftResult {
  draft: ResumeDraft;
  baseUpdatedAt: string;
  banner: DraftBanner;
  setDraft: (next: ResumeDraft) => void;
  continueDraft: () => void;
  discardDraft: () => void;
  rehydrateFromResume: (resume: ResumeRead) => void;
}

/**
 * Локальная персистентность черновика в localStorage.
 * На сервер не пишет — только debounce ~500 мс в браузер.
 * Смена резюме — через `key={resume.id}` у родителя (полный remount).
 */
export function useLocalDraft(resume: ResumeRead): UseLocalDraftResult {
  const resumeId = resume.id;
  const [state, setState] = useState<LocalState>(() => initState(resume));
  const dirtyLocal = useRef(state.banner !== null);

  useEffect(() => {
    if (!dirtyLocal.current) {
      return;
    }
    const timer = window.setTimeout(() => {
      const payload: StoredResumeDraft = {
        baseUpdatedAt: state.baseUpdatedAt,
        draft: state.draft,
        savedAt: new Date().toISOString(),
      };
      writeStorageJson(draftStorageKey(resumeId), payload);
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [state.draft, state.baseUpdatedAt, resumeId]);

  const setDraft = (next: ResumeDraft) => {
    dirtyLocal.current = true;
    setState((prev) => ({ ...prev, draft: next }));
  };

  const continueDraft = () => setState((prev) => ({ ...prev, banner: null }));

  const discardDraft = () => {
    removeStorage(draftStorageKey(resume.id));
    dirtyLocal.current = false;
    setState({
      draft: fromResume(resume),
      baseUpdatedAt: resume.updated_at,
      banner: null,
    });
  };

  const rehydrateFromResume = (next: ResumeRead) => {
    dirtyLocal.current = false;
    removeStorage(draftStorageKey(next.id));
    setState({
      draft: fromResume(next),
      baseUpdatedAt: next.updated_at,
      banner: null,
    });
  };

  return {
    draft: state.draft,
    baseUpdatedAt: state.baseUpdatedAt,
    banner: state.banner,
    setDraft,
    continueDraft,
    discardDraft,
    rehydrateFromResume,
  };
}
