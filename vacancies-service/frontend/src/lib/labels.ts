/** Русские подписи enum-значений API. */

import type {
  EmploymentType,
  ExperienceLevel,
  LanguageLevel,
  ResumeOrigin,
  RunStatus,
  SalaryPeriod,
  SourceType,
  UserAction,
  VacancySort,
  WorkFormat,
} from "@/api/types";

export const WORK_FORMAT_LABELS: Record<WorkFormat, string> = {
  remote: "Удалённо",
  office: "Офис",
  hybrid: "Гибрид",
  unknown: "Формат не указан",
};

export const EXPERIENCE_LEVEL_LABELS: Record<ExperienceLevel, string> = {
  intern: "Стажёр",
  junior: "Junior",
  middle: "Middle",
  senior: "Senior",
  lead: "Lead",
  unknown: "Уровень не указан",
};

export const EMPLOYMENT_TYPE_LABELS: Record<EmploymentType, string> = {
  full_time: "Полная занятость",
  part_time: "Частичная занятость",
  contract: "Контракт",
  internship: "Стажировка",
  unknown: "Занятость не указана",
};

export const USER_ACTION_LABELS: Record<UserAction, string> = {
  viewed: "Просмотрено",
  saved: "Сохранено",
  hidden: "Скрыто",
  applied: "Отклик",
};

export const RUN_STATUS_LABELS: Record<RunStatus, string> = {
  running: "Выполняется",
  success: "Успешно",
  failed: "Ошибка",
};

export const LANGUAGE_LEVEL_LABELS: Record<LanguageLevel, string> = {
  A1: "A1 — начальный",
  A2: "A2 — элементарный",
  B1: "B1 — средний",
  B2: "B2 — выше среднего",
  C1: "C1 — продвинутый",
  C2: "C2 — в совершенстве",
  native: "Родной",
};

export const SOURCE_TYPE_LABELS: Record<SourceType, string> = {
  telegram: "Telegram",
  html: "Сайт",
  api: "API",
};

export const RESUME_ORIGIN_LABELS: Record<ResumeOrigin, string> = {
  manual: "Вручную",
  generated: "ИИ",
  duplicated: "Копия",
};

export const VACANCY_SORT_LABELS: Record<VacancySort, string> = {
  match: "По соответствию",
  relevance: "По релевантности",
  date: "По дате",
  salary: "По зарплате",
};

export const SALARY_PERIOD_SUFFIX: Record<SalaryPeriod, string> = {
  month: "",
  year: " / год",
  hour: " / час",
};
