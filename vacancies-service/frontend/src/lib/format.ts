/** Чистые функции форматирования для интерфейса (локаль ru-RU). */

import type { SalaryPeriod, WorkFormat } from "@/api/types";
import { SALARY_PERIOD_SUFFIX, WORK_FORMAT_LABELS } from "@/lib/labels";

const NUMBER = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
const SCORE10 = new Intl.NumberFormat("ru-RU", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});
const SHORT_DATE = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short" });
const SHORT_DATE_YEAR = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

const CURRENCY_SYMBOLS: Record<string, string> = {
  RUB: "₽",
  USD: "$",
  EUR: "€",
  GBP: "£",
  KZT: "₸",
};

const DAY_MS = 24 * 60 * 60 * 1000;
const RELATIVE_DAYS_LIMIT = 30;

/** Русское множественное число: `pluralRu(5, ["день", "дня", "дней"])` → «дней». */
export function pluralRu(n: number, forms: readonly [string, string, string]): string {
  const abs = Math.abs(Math.trunc(n));
  const mod10 = abs % 10;
  const mod100 = abs % 100;
  if (mod10 === 1 && mod100 !== 11) {
    return forms[0];
  }
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return forms[1];
  }
  return forms[2];
}

export interface SalaryInput {
  min: number | null;
  max: number | null;
  currency: string | null;
  period: SalaryPeriod | null;
}

/** «от 200 000 ₽», «до 5 000 $ / час», «150 000 – 250 000 ₽» или «Зарплата не указана». */
export function formatSalary({ min, max, currency, period }: SalaryInput): string {
  if (min === null && max === null) {
    return "Зарплата не указана";
  }
  const unit = currency ? ` ${CURRENCY_SYMBOLS[currency] ?? currency}` : "";
  const suffix = period ? SALARY_PERIOD_SUFFIX[period] : "";
  let amount: string;
  if (min !== null && max !== null) {
    amount = min === max ? NUMBER.format(min) : `${NUMBER.format(min)} – ${NUMBER.format(max)}`;
  } else if (min !== null) {
    amount = `от ${NUMBER.format(min)}`;
  } else {
    amount = `до ${NUMBER.format(max as number)}`;
  }
  return `${amount}${unit}${suffix}`;
}

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

/** «сегодня», «вчера», «N дней назад» до 30 дней, дальше «5 сент.»; `null` — «дата не указана». */
export function formatRelativeDate(iso: string | null, now: Date): string {
  if (iso === null) {
    return "дата не указана";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "дата не указана";
  }
  const days = Math.round((startOfDay(now) - startOfDay(date)) / DAY_MS);
  if (days <= 0) {
    return "сегодня";
  }
  if (days === 1) {
    return "вчера";
  }
  if (days <= RELATIVE_DAYS_LIMIT) {
    return `${days} ${pluralRu(days, ["день", "дня", "дней"])} назад`;
  }
  return (date.getFullYear() === now.getFullYear() ? SHORT_DATE : SHORT_DATE_YEAR).format(date);
}

/** Оценка резюме 0–10 с одной десятичной: 6.31 → «6,3». */
export function formatScore10(score: number): string {
  return SCORE10.format(score);
}

/** Балл соответствия 0–100 → «87%». */
export function formatPercent(score: number): string {
  return `${Math.round(score)}%`;
}

/** Длительность запуска: «42 с», «1 мин 58 с», «2 ч 5 мин»; без конца — «идёт». */
export function formatDuration(start: string, end: string | null): string {
  if (end === null) {
    return "идёт";
  }
  const seconds = Math.max(0, Math.round((Date.parse(end) - Date.parse(start)) / 1000));
  if (Number.isNaN(seconds)) {
    return "—";
  }
  if (seconds < 60) {
    return `${seconds} с`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    const rest = seconds % 60;
    return rest ? `${minutes} мин ${rest} с` : `${minutes} мин`;
  }
  const hours = Math.floor(minutes / 60);
  const restMinutes = minutes % 60;
  return restMinutes ? `${hours} ч ${restMinutes} мин` : `${hours} ч`;
}

/** «Москва, Россия · Гибрид»; формат `unknown` не пишется. */
export function formatLocation(
  city: string | null,
  country: string | null,
  workFormat: WorkFormat | null,
): string {
  const place = [city, country].filter((part): part is string => Boolean(part)).join(", ");
  const format = workFormat && workFormat !== "unknown" ? WORK_FORMAT_LABELS[workFormat] : "";
  const parts = [place, format].filter(Boolean);
  return parts.length ? parts.join(" · ") : "Локация не указана";
}
