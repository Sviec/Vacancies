/**
 * Общие поля профиля: контакты, место жительства, образование, языки.
 * Источник для формы — основное резюме. Сохранение записывает их во все резюме.
 * Фото живёт только в браузере: в схеме резюме колонки нет.
 * // TODO: этап 9 — эти поля должен отдавать адаптер профиля, а не копия в каждом резюме.
 */

import type { ResumeRead, ResumeUpdate } from "@/api/types";
import type { DraftEducation, DraftLanguage, ResumeDraft, StoredResumeDraft } from "@/features/editor/draft";
import {
  draftStorageKey,
  fromResume,
  isStoredResumeDraft,
  toPayload,
  validateDraft,
} from "@/features/editor/draft";
import { readStorage, readStorageJson, removeStorage, writeStorage, writeStorageJson } from "@/lib/storage";

export const PROFILE_PHOTO_KEY = "vacancies.profilePhoto";

export interface ProfileForm {
  contacts: ResumeDraft["contacts"];
  country: string;
  city: string;
  education: DraftEducation[];
  languages: DraftLanguage[];
}

export function emptyProfile(): ProfileForm {
  return {
    contacts: {
      email: "",
      phone: "",
      telegram: "",
      linkedin: "",
      github: "",
      website: "",
    },
    country: "",
    city: "",
    education: [],
    languages: [],
  };
}

export function profileFromResume(resume: ResumeRead): ProfileForm {
  const draft = fromResume(resume);
  return {
    contacts: draft.contacts,
    country: draft.desired_country,
    city: draft.desired_city,
    education: draft.education,
    languages: draft.languages,
  };
}

function isBlankEducation(item: DraftEducation): boolean {
  return (
    item.institution.trim() === "" &&
    item.degree.trim() === "" &&
    item.field.trim() === "" &&
    item.start_year.trim() === "" &&
    item.end_year.trim() === ""
  );
}

function isBlankLanguage(item: DraftLanguage): boolean {
  return item.language.trim() === "" && item.level === "";
}

function asDraft(form: ProfileForm): ResumeDraft {
  return {
    title: "Профиль",
    is_primary: false,
    target_position: "",
    desired_salary_min: "",
    desired_salary_currency: "",
    desired_country: form.country,
    desired_city: form.city,
    desired_work_format: "",
    summary: "",
    contacts: form.contacts,
    experience: [],
    education: form.education.filter((item) => !isBlankEducation(item)),
    skills: [],
    courses: [],
    languages: form.languages.filter((item) => !isBlankLanguage(item)),
  };
}

/** Поля, которые профиль записывает в каждое резюме. */
export function profileToUpdate(form: ProfileForm): ResumeUpdate {
  const payload = toPayload(asDraft(form));
  return {
    contacts: payload.contacts,
    education: payload.education,
    languages: payload.languages,
    desired_city: payload.desired_city,
    desired_country: payload.desired_country,
  };
}

/** Ошибки только по общим полям. Пустые новые строки образования и языков отбрасываются. */
export function validateProfile(form: ProfileForm, today: Date): Record<string, string> {
  const errors = validateDraft(asDraft(form), today);
  const kept: Record<string, string> = {};
  for (const [key, message] of Object.entries(errors)) {
    if (
      key.startsWith("contacts.") ||
      key.startsWith("education.") ||
      key.startsWith("languages.") ||
      key === "desired_city" ||
      key === "desired_country"
    ) {
      kept[key] = message;
    }
  }
  return kept;
}

export function applyProfileToDraft(draft: ResumeDraft, form: ProfileForm): ResumeDraft {
  const next = asDraft(form);
  return {
    ...draft,
    contacts: { ...next.contacts },
    desired_city: next.desired_city,
    desired_country: next.desired_country,
    education: next.education,
    languages: next.languages,
  };
}

/** Подмешать профиль в локальные черновики, чтобы сохранение резюме не вернуло старые контакты. */
export function mergeProfileIntoStoredDrafts(resumeIds: readonly string[], form: ProfileForm): void {
  for (const id of resumeIds) {
    const stored = readStorageJson<StoredResumeDraft>(draftStorageKey(id));
    if (!isStoredResumeDraft(stored)) {
      continue;
    }
    writeStorageJson(draftStorageKey(id), {
      ...stored,
      draft: applyProfileToDraft(stored.draft, form),
    });
  }
}

export function readProfilePhoto(): string | null {
  const value = readStorage(PROFILE_PHOTO_KEY);
  return value?.startsWith("data:image/") ? value : null;
}

export function writeProfilePhoto(dataUrl: string): void {
  writeStorage(PROFILE_PHOTO_KEY, dataUrl);
}

export function clearProfilePhoto(): void {
  removeStorage(PROFILE_PHOTO_KEY);
}
