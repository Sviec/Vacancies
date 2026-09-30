import { describe, expect, it } from "vitest";

import {
  formatDuration,
  formatLocation,
  formatPercent,
  formatRelativeDate,
  formatSalary,
  formatScore10,
  pluralRu,
} from "@/lib/format";

// Intl в ru-RU разделяет разряды неразрывным пробелом.
const plain = (value: string) => value.replace(/[\u00a0\u202f]/g, " ");

describe("formatSalary", () => {
  const salary = (min: number | null, max: number | null, currency: string | null = "RUB", period: "month" | "year" | "hour" | null = "month") =>
    plain(formatSalary({ min, max, currency, period }));

  it("вилка, от и до", () => {
    expect(salary(150000, 250000)).toBe("150 000 – 250 000 ₽");
    expect(salary(200000, null)).toBe("от 200 000 ₽");
    expect(salary(null, 300000)).toBe("до 300 000 ₽");
    expect(salary(100000, 100000)).toBe("100 000 ₽");
  });

  it("символы валют и ISO-код для прочих", () => {
    expect(salary(5000, null, "USD")).toBe("от 5 000 $");
    expect(salary(5000, null, "EUR")).toBe("от 5 000 €");
    expect(salary(5000, null, "GBP")).toBe("от 5 000 £");
    expect(salary(500000, null, "KZT")).toBe("от 500 000 ₸");
    expect(salary(5000, null, "CHF")).toBe("от 5 000 CHF");
    expect(salary(5000, null, null)).toBe("от 5 000");
  });

  it("суффикс периода, для месяца его нет", () => {
    expect(salary(60000, 90000, "USD", "year")).toBe("60 000 – 90 000 $ / год");
    expect(salary(40, null, "EUR", "hour")).toBe("от 40 € / час");
    expect(salary(40, null, "EUR", null)).toBe("от 40 €");
  });

  it("без суммы", () => {
    expect(salary(null, null)).toBe("Зарплата не указана");
  });
});

describe("formatRelativeDate", () => {
  const now = new Date(2026, 8, 30, 15, 0);
  const daysAgo = (days: number, hour = 12) => new Date(2026, 8, 30 - days, hour).toISOString();

  it("сегодня, вчера, N дней назад", () => {
    expect(formatRelativeDate(daysAgo(0, 1), now)).toBe("сегодня");
    expect(formatRelativeDate(daysAgo(1, 23), now)).toBe("вчера");
    expect(formatRelativeDate(daysAgo(2), now)).toBe("2 дня назад");
    expect(formatRelativeDate(daysAgo(5), now)).toBe("5 дней назад");
    expect(formatRelativeDate(daysAgo(21), now)).toBe("21 день назад");
    expect(formatRelativeDate(daysAgo(30), now)).toBe("30 дней назад");
  });

  it("дальше 30 дней — дата, в другом году — с годом", () => {
    expect(formatRelativeDate(new Date(2026, 5, 5, 12).toISOString(), now)).toMatch(/^5 июн/);
    expect(formatRelativeDate(new Date(2025, 11, 1, 12).toISOString(), now)).toMatch(/2025/);
  });

  it("будущая дата — сегодня, пустая и битая — не указана", () => {
    expect(formatRelativeDate(new Date(2026, 9, 2).toISOString(), now)).toBe("сегодня");
    expect(formatRelativeDate(null, now)).toBe("дата не указана");
    expect(formatRelativeDate("not-a-date", now)).toBe("дата не указана");
  });
});

describe("числа", () => {
  it("formatScore10 — одна десятичная через запятую", () => {
    expect(formatScore10(6.31)).toBe("6,3");
    expect(formatScore10(10)).toBe("10,0");
    expect(formatScore10(2.95)).toBe("3,0");
  });

  it("formatPercent округляет", () => {
    expect(formatPercent(87.4)).toBe("87%");
    expect(formatPercent(0)).toBe("0%");
  });

  it("pluralRu", () => {
    const forms = ["вакансия", "вакансии", "вакансий"] as const;
    expect([1, 2, 5, 11, 12, 14, 21, 22, 25, 101, 111].map((n) => pluralRu(n, forms))).toEqual([
      "вакансия",
      "вакансии",
      "вакансий",
      "вакансий",
      "вакансий",
      "вакансий",
      "вакансия",
      "вакансии",
      "вакансий",
      "вакансия",
      "вакансий",
    ]);
  });
});

describe("formatDuration", () => {
  const start = "2026-09-30T10:00:00Z";
  it("секунды, минуты, часы", () => {
    expect(formatDuration(start, "2026-09-30T10:00:42Z")).toBe("42 с");
    expect(formatDuration(start, "2026-09-30T10:01:58Z")).toBe("1 мин 58 с");
    expect(formatDuration(start, "2026-09-30T10:03:00Z")).toBe("3 мин");
    expect(formatDuration(start, "2026-09-30T12:05:00Z")).toBe("2 ч 5 мин");
  });
  it("без конца — идёт", () => {
    expect(formatDuration(start, null)).toBe("идёт");
  });
});

describe("formatLocation", () => {
  it("город, страна и формат", () => {
    expect(formatLocation("Москва", "Россия", "hybrid")).toBe("Москва, Россия · Гибрид");
    expect(formatLocation(null, "Кипр", "office")).toBe("Кипр · Офис");
    expect(formatLocation(null, null, "remote")).toBe("Удалённо");
    expect(formatLocation("Алматы", null, "unknown")).toBe("Алматы");
    expect(formatLocation(null, null, null)).toBe("Локация не указана");
  });
});
