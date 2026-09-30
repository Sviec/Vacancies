/**
 * Защита раздела 8 ТЗ на уровне исходников: цвета только через токены
 * index.css, без масштабирования, вращений и спиннеров.
 */

import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const SRC = fileURLToPath(new URL(".", import.meta.url));

/** Статический `-rotate-90` у кольца MatchMeter — дуга начинается сверху. */
const ALLOWED_ROTATE = new Set(["features/vacancies/MatchMeter.tsx"]);

const FORBIDDEN: { pattern: RegExp; reason: string; allowlist?: Set<string> }[] = [
  { pattern: /#[0-9a-fA-F]{3,8}\b/, reason: "hex-цвет в кавычках/коде — нужен токен" },
  { pattern: /\b(bg|text|border)-(white|black)\b/, reason: "white/black — нужен токен темы" },
  { pattern: /\banimate-bounce\b/, reason: "bounce запрещён" },
  { pattern: /\banimate-pulse\b/, reason: "pulse запрещён" },
  { pattern: /\banimate-spin\b/, reason: "спиннер запрещён — нужен skeleton" },
  { pattern: /\bscale-/, reason: "масштабирование (Tailwind) запрещено" },
  { pattern: /\bscale\s*:/, reason: "Framer scale запрещён" },
  { pattern: /\bwhileHover\b[\s\S]{0,80}\bscale\b/, reason: "whileHover со scale запрещён" },
  { pattern: /\bwhileTap\b[\s\S]{0,80}\bscale\b/, reason: "whileTap со scale запрещён" },
  { pattern: /\brotate\s*:/, reason: "Framer rotate запрещён" },
  {
    pattern: /\b-?rotate-/,
    reason: "вращения Tailwind запрещены",
    allowlist: ALLOWED_ROTATE,
  },
];

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      return sourceFiles(path);
    }
    if (!entry.name.endsWith(".ts") && !entry.name.endsWith(".tsx")) {
      return [];
    }
    if (entry.name.endsWith(".test.ts") || entry.name.endsWith(".test.tsx")) {
      return [];
    }
    if (entry.name === "schema.gen.ts") {
      return [];
    }
    return [path];
  });
}

describe("design guard", () => {
  const files = sourceFiles(SRC);

  it("находит исходники", () => {
    expect(files.length).toBeGreaterThan(10);
  });

  it("паттерны ловят типичные нарушения", () => {
    expect(/#[0-9a-fA-F]{3,8}\b/.test('color: "#FAFAF9"')).toBe(true);
    expect(/\banimate-bounce\b/.test("animate-bounce")).toBe(true);
    expect(/\banimate-pulse\b/.test("animate-pulse")).toBe(true);
    expect(/\banimate-spin\b/.test("animate-spin")).toBe(true);
    expect(/\bscale-/.test("scale-105")).toBe(true);
    expect(/\bscale\s*:/.test("scale: 1.05")).toBe(true);
    expect(/\bwhileHover\b[\s\S]{0,80}\bscale\b/.test("whileHover={{ scale: 1.02 }}")).toBe(true);
    expect(/\bwhileTap\b[\s\S]{0,80}\bscale\b/.test("whileTap={{ scale: 0.98 }}")).toBe(true);
    expect(/\brotate\s*:/.test("rotate: 90")).toBe(true);
    expect(/\b-?rotate-/.test("-rotate-90")).toBe(true);
    expect(/\b-?rotate-/.test("rotate-45")).toBe(true);
  });

  it("в исходниках нет запрещённых паттернов", () => {
    const violations: string[] = [];
    for (const file of files) {
      const rel = relative(SRC, file).replaceAll("\\", "/");
      readFileSync(file, "utf8")
        .split(/\r?\n/)
        .forEach((line, index) => {
          for (const { pattern, reason, allowlist } of FORBIDDEN) {
            if (allowlist?.has(rel)) {
              continue;
            }
            if (pattern.test(line)) {
              violations.push(`${rel}:${index + 1} — ${reason}: ${line.trim()}`);
            }
          }
        });
    }
    expect(violations).toEqual([]);
  });
});
