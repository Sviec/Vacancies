/**
 * Модель черновика редактора резюме: строки/булевы для формы,
 * преобразование в ResumeUpdate и клиентская валидация (зеркало бэкенда).
 *
 * Автосохранения на сервер нет: локальный черновик живёт в localStorage
 * (см. use-local-draft.ts), PATCH — только по явной кнопке «Сохранить».
 */

import type { ApiError } from "@/api/client";
import type {
  LanguageLevel,
  ResumeRead,
  ResumeUpdate,
  WorkFormat,
} from "@/api/types";

const CONTACT_KEYS = ["email", "phone", "telegram", "linkedin", "github", "website"] as const;
const LANGUAGE_LEVELS = new Set<LanguageLevel>(["A1", "A2", "B1", "B2", "C1", "C2", "native"]);
const WORK_FORMATS = new Set<WorkFormat>(["remote", "office", "hybrid", "unknown"]);
const CURRENCY_RE = /^[A-Z]{3}$/;
const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

let keyCounter = 0;

/** Локальный ключ строки секции для React (не уходит на сервер). */
export function newItemKey(): string {
  keyCounter += 1;
  return `k-${keyCounter}-${Math.random().toString(36).slice(2, 8)}`;
}

export type DraftContacts = Record<(typeof CONTACT_KEYS)[number], string>;

export interface DraftExperience {
  key: string;
  company: string;
  position: string;
  start_date: string;
  end_date: string;
  is_current: boolean;
  description: string;
  achievements: string;
}

export interface DraftEducation {
  key: string;
  institution: string;
  degree: string;
  field: string;
  start_year: string;
  end_year: string;
}

export interface DraftSkill {
  key: string;
  skill: string;
  level: string;
}

export interface DraftCourse {
  key: string;
  title: string;
  provider: string;
  year: string;
  certificate_url: string;
}

export interface DraftLanguage {
  key: string;
  language: string;
  level: LanguageLevel | "";
}

export interface ResumeDraft {
  title: string;
  is_primary: boolean;
  target_position: string;
  desired_salary_min: string;
  desired_salary_currency: string;
  desired_country: string;
  desired_city: string;
  desired_work_format: WorkFormat | "";
  summary: string;
  contacts: DraftContacts;
  experience: DraftExperience[];
  education: DraftEducation[];
  skills: DraftSkill[];
  courses: DraftCourse[];
  languages: DraftLanguage[];
}

/** Конверт localStorage: `vacancies.resumeDraft.<resumeId>`. */
export interface StoredResumeDraft {
  baseUpdatedAt: string;
  draft: ResumeDraft;
  savedAt: string;
}

export function draftStorageKey(resumeId: string): string {
  return `vacancies.resumeDraft.${resumeId}`;
}

function emptyContacts(): DraftContacts {
  return {
    email: "",
    phone: "",
    telegram: "",
    linkedin: "",
    github: "",
    website: "",
  };
}

function nullToEmpty(value: string | null | undefined): string {
  return value ?? "";
}

function emptyToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

function dateToInput(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  // ISO datetime → YYYY-MM-DD
  return value.slice(0, 10);
}

function numToInput(value: number | null | undefined): string {
  return value == null ? "" : String(value);
}

/** Собрать форму из ответа API. */
export function fromResume(resume: ResumeRead): ResumeDraft {
  const contacts = emptyContacts();
  for (const key of CONTACT_KEYS) {
    contacts[key] = nullToEmpty(resume.contacts?.[key]);
  }
  return {
    title: resume.title,
    is_primary: resume.is_primary,
    target_position: nullToEmpty(resume.target_position),
    desired_salary_min: numToInput(resume.desired_salary_min),
    desired_salary_currency: nullToEmpty(resume.desired_salary_currency),
    desired_country: nullToEmpty(resume.desired_country),
    desired_city: nullToEmpty(resume.desired_city),
    desired_work_format: resume.desired_work_format ?? "",
    summary: nullToEmpty(resume.summary),
    contacts,
    experience: (resume.experience ?? []).map((item) => ({
      key: newItemKey(),
      company: item.company,
      position: item.position,
      start_date: dateToInput(item.start_date),
      end_date: dateToInput(item.end_date),
      is_current: item.is_current,
      description: nullToEmpty(item.description),
      achievements: nullToEmpty(item.achievements),
    })),
    education: (resume.education ?? []).map((item) => ({
      key: newItemKey(),
      institution: item.institution,
      degree: nullToEmpty(item.degree),
      field: nullToEmpty(item.field),
      start_year: numToInput(item.start_year),
      end_year: numToInput(item.end_year),
    })),
    skills: (resume.skills ?? []).map((item) => ({
      key: newItemKey(),
      skill: item.skill,
      level: numToInput(item.level),
    })),
    courses: (resume.courses ?? []).map((item) => ({
      key: newItemKey(),
      title: item.title,
      provider: nullToEmpty(item.provider),
      year: numToInput(item.year),
      certificate_url: nullToEmpty(item.certificate_url),
    })),
    languages: (resume.languages ?? []).map((item) => ({
      key: newItemKey(),
      language: item.language,
      level: item.level,
    })),
  };
}

function parseOptionalInt(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") {
    return null;
  }
  const n = Number(trimmed);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

function parseLevel(raw: string): number | null {
  return parseOptionalInt(raw);
}

/** Полный payload для PATCH (все секции целиком). */
export function toPayload(draft: ResumeDraft): ResumeUpdate {
  const format = draft.desired_work_format;
  return {
    title: draft.title.trim() || null,
    is_primary: draft.is_primary,
    target_position: emptyToNull(draft.target_position),
    desired_salary_min: parseOptionalInt(draft.desired_salary_min),
    desired_salary_currency: emptyToNull(draft.desired_salary_currency),
    desired_country: emptyToNull(draft.desired_country),
    desired_city: emptyToNull(draft.desired_city),
    desired_work_format: format === "" ? null : format,
    summary: emptyToNull(draft.summary),
    contacts: {
      email: emptyToNull(draft.contacts.email),
      phone: emptyToNull(draft.contacts.phone),
      telegram: emptyToNull(draft.contacts.telegram),
      linkedin: emptyToNull(draft.contacts.linkedin),
      github: emptyToNull(draft.contacts.github),
      website: emptyToNull(draft.contacts.website),
    },
    experience: draft.experience.map((item) => ({
      company: item.company.trim(),
      position: item.position.trim(),
      start_date: item.start_date,
      end_date: item.is_current ? null : emptyToNull(item.end_date),
      is_current: item.is_current,
      description: emptyToNull(item.description),
      achievements: emptyToNull(item.achievements),
    })),
    education: draft.education.map((item) => ({
      institution: item.institution.trim(),
      degree: emptyToNull(item.degree),
      field: emptyToNull(item.field),
      start_year: parseOptionalInt(item.start_year),
      end_year: parseOptionalInt(item.end_year),
    })),
    skills: draft.skills
      .map((item) => ({
        skill: item.skill.trim(),
        level: parseLevel(item.level),
      }))
      .filter((item) => item.skill !== ""),
    courses: draft.courses.map((item) => ({
      title: item.title.trim(),
      provider: emptyToNull(item.provider),
      year: parseOptionalInt(item.year),
      certificate_url: emptyToNull(item.certificate_url),
    })),
    languages: draft.languages
      .filter((item) => item.language.trim() !== "" && item.level !== "")
      .map((item) => ({
        language: item.language.trim(),
        level: item.level as LanguageLevel,
      })),
  };
}

function deepEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/**
 * Только изменившиеся ключи верхнего уровня.
 * Секции (experience, skills, …) уходят целиком: PATCH заменяет список.
 */
export function diffPayload(prev: ResumeUpdate, next: ResumeUpdate): ResumeUpdate {
  const result: ResumeUpdate = {};
  const keys = new Set([...Object.keys(prev), ...Object.keys(next)]) as Set<keyof ResumeUpdate>;
  for (const key of keys) {
    const left = prev[key];
    const right = next[key];
    if (!deepEqual(left, right)) {
      (result as Record<string, unknown>)[key] = right;
    }
  }
  return result;
}

/** Черновик совпадает с сервером → восстанавливать из localStorage не нужно. */
export function draftMatchesResume(draft: ResumeDraft, resume: ResumeRead): boolean {
  const fromServer = toPayload(fromResume(resume));
  const fromDraft = toPayload(draft);
  return deepEqual(fromServer, fromDraft);
}

function parseIsoDate(value: string): Date | null {
  if (!ISO_DATE_RE.test(value)) {
    return null;
  }
  const [y, m, d] = value.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  if (date.getUTCFullYear() !== y || date.getUTCMonth() !== m - 1 || date.getUTCDate() !== d) {
    return null;
  }
  return date;
}

function todayUtc(today: Date): Date {
  return new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate()));
}

/**
 * Клиентская валидация — зеркало правил бэкенда.
 * Путь: `title`, `experience.0.end_date`, `skills.1.skill`, …
 */
export function validateDraft(draft: ResumeDraft, today: Date): Record<string, string> {
  const errors: Record<string, string> = {};
  const todayDate = todayUtc(today);

  const title = draft.title.trim();
  if (!title) {
    errors.title = "Укажите название резюме";
  } else if (title.length > 255) {
    errors.title = "Не длиннее 255 символов";
  }

  const salary = draft.desired_salary_min.trim();
  if (salary !== "") {
    const n = Number(salary);
    if (!Number.isFinite(n) || n < 0 || !Number.isInteger(n)) {
      errors.desired_salary_min = "Зарплата — целое число ≥ 0";
    }
  }

  const currency = draft.desired_salary_currency.trim();
  if (currency !== "" && !CURRENCY_RE.test(currency)) {
    errors.desired_salary_currency = "Валюта — ровно три латинские буквы (например RUB)";
  }

  if (draft.desired_work_format !== "" && !WORK_FORMATS.has(draft.desired_work_format)) {
    errors.desired_work_format = "Неизвестный формат работы";
  }

  draft.experience.forEach((item, index) => {
    const prefix = `experience.${index}`;
    if (!item.company.trim()) {
      errors[`${prefix}.company`] = "Укажите компанию";
    } else if (item.company.trim().length > 255) {
      errors[`${prefix}.company`] = "Не длиннее 255 символов";
    }
    if (!item.position.trim()) {
      errors[`${prefix}.position`] = "Укажите должность";
    } else if (item.position.trim().length > 255) {
      errors[`${prefix}.position`] = "Не длиннее 255 символов";
    }

    const start = parseIsoDate(item.start_date);
    if (!item.start_date.trim()) {
      errors[`${prefix}.start_date`] = "Укажите дату начала";
    } else if (!start) {
      errors[`${prefix}.start_date`] = "Некорректная дата";
    } else if (start > todayDate) {
      errors[`${prefix}.start_date`] = "Дата не может быть в будущем";
    }

    if (item.is_current) {
      if (item.end_date.trim()) {
        errors[`${prefix}.end_date`] = "При «по настоящее время» дату окончания очистите";
      }
    } else if (item.end_date.trim()) {
      const end = parseIsoDate(item.end_date);
      if (!end) {
        errors[`${prefix}.end_date`] = "Некорректная дата";
      } else if (end > todayDate) {
        errors[`${prefix}.end_date`] = "Дата не может быть в будущем";
      } else if (start && end <= start) {
        errors[`${prefix}.end_date`] = "Дата окончания должна быть позже начала";
      }
    }
  });

  draft.education.forEach((item, index) => {
    const prefix = `education.${index}`;
    if (!item.institution.trim()) {
      errors[`${prefix}.institution`] = "Укажите учебное заведение";
    }
    const startYear = parseOptionalInt(item.start_year);
    const endYear = parseOptionalInt(item.end_year);
    if (item.start_year.trim() && (startYear == null || startYear < 1900 || startYear > 2100)) {
      errors[`${prefix}.start_year`] = "Год 1900–2100";
    }
    if (item.end_year.trim() && (endYear == null || endYear < 1900 || endYear > 2100)) {
      errors[`${prefix}.end_year`] = "Год 1900–2100";
    }
    if (startYear != null && endYear != null && endYear < startYear) {
      errors[`${prefix}.end_year`] = "Год окончания не раньше начала";
    }
  });

  draft.courses.forEach((item, index) => {
    const prefix = `courses.${index}`;
    if (!item.title.trim()) {
      errors[`${prefix}.title`] = "Укажите название курса";
    }
    const year = parseOptionalInt(item.year);
    if (item.year.trim() && (year == null || year < 1900 || year > 2100)) {
      errors[`${prefix}.year`] = "Год 1900–2100";
    }
  });

  const skillNames = new Set<string>();
  draft.skills.forEach((item, index) => {
    const prefix = `skills.${index}`;
    const name = item.skill.trim();
    if (!name) {
      errors[`${prefix}.skill`] = "Укажите навык";
      return;
    }
    if (name.length > 100) {
      errors[`${prefix}.skill`] = "Не длиннее 100 символов";
    }
    const fold = name.toLocaleLowerCase("en");
    if (skillNames.has(fold)) {
      errors[`${prefix}.skill`] = "Навык уже добавлен";
    }
    skillNames.add(fold);

    if (item.level.trim()) {
      const level = parseLevel(item.level);
      if (level == null || level < 1 || level > 5) {
        errors[`${prefix}.level`] = "Уровень — число от 1 до 5";
      }
    }
  });

  const langNames = new Set<string>();
  draft.languages.forEach((item, index) => {
    const prefix = `languages.${index}`;
    const name = item.language.trim();
    if (!name) {
      errors[`${prefix}.language`] = "Укажите язык";
      return;
    }
    const fold = name.toLocaleLowerCase("en");
    if (langNames.has(fold)) {
      errors[`${prefix}.language`] = "Язык уже добавлен";
    }
    langNames.add(fold);
    if (!item.level || !LANGUAGE_LEVELS.has(item.level)) {
      errors[`${prefix}.level`] = "Выберите уровень";
    }
  });

  return errors;
}

/**
 * `details.errors[].loc` вида `["body","experience",0,"end_date"]`
 * → путь `experience.0.end_date`.
 */
export function mapServerErrors(error: ApiError): Record<string, string> {
  const raw = error.details.errors;
  if (!Array.isArray(raw)) {
    return {};
  }
  const result: Record<string, string> = {};
  for (const item of raw) {
    if (typeof item !== "object" || item === null) {
      continue;
    }
    const loc = (item as { loc?: unknown }).loc;
    const msg = (item as { msg?: unknown }).msg;
    if (!Array.isArray(loc) || typeof msg !== "string") {
      continue;
    }
    const parts = loc.filter((part) => part !== "body" && typeof part !== "object");
    if (parts.length === 0) {
      continue;
    }
    const path = parts.join(".");
    if (!(path in result)) {
      result[path] = msg;
    }
  }
  return result;
}

/** Пустая позиция опыта для «+ Добавить». */
export function emptyExperience(): DraftExperience {
  return {
    key: newItemKey(),
    company: "",
    position: "",
    start_date: "",
    end_date: "",
    is_current: false,
    description: "",
    achievements: "",
  };
}

export function emptyEducation(): DraftEducation {
  return {
    key: newItemKey(),
    institution: "",
    degree: "",
    field: "",
    start_year: "",
    end_year: "",
  };
}

export function emptyCourse(): DraftCourse {
  return {
    key: newItemKey(),
    title: "",
    provider: "",
    year: "",
    certificate_url: "",
  };
}

export function emptySkill(skill = "", level = "3"): DraftSkill {
  return { key: newItemKey(), skill, level };
}

export function emptyLanguage(): DraftLanguage {
  return { key: newItemKey(), language: "", level: "" };
}

export function isStoredResumeDraft(value: unknown): value is StoredResumeDraft {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const obj = value as Record<string, unknown>;
  return (
    typeof obj.baseUpdatedAt === "string" &&
    typeof obj.savedAt === "string" &&
    typeof obj.draft === "object" &&
    obj.draft !== null
  );
}
