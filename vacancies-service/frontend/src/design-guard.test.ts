/**
 * Защита раздела 8 ТЗ на уровне исходников: цвета только через токены
 * index.css, без масштабирования, вращений и спиннеров.
 */

import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const SRC = fileURLToPath(new URL(".", import.meta.url));

const FORBIDDEN: { pattern: RegExp; reason: string }[] = [
  { pattern: /\[#[0-9a-fA-F]{3,8}\]/, reason: "hex-цвет в классе — нужен токен" },
  { pattern: /\b(bg|text|border)-(white|black)\b/, reason: "white/black — нужен токен темы" },
  { pattern: /\bscale-/, reason: "масштабирование запрещено" },
  { pattern: /\banimate-spin\b/, reason: "спиннер запрещён — нужен skeleton" },
  { pattern: /\brotate-/, reason: "вращения запрещены" },
];

function tsxFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      return tsxFiles(path);
    }
    return entry.name.endsWith(".tsx") ? [path] : [];
  });
}

describe("design guard", () => {
  const files = tsxFiles(SRC);

  it("находит компоненты", () => {
    expect(files.length).toBeGreaterThan(10);
  });

  it("в JSX нет запрещённых классов", () => {
    const violations: string[] = [];
    for (const file of files) {
      readFileSync(file, "utf8")
        .split(/\r?\n/)
        .forEach((line, index) => {
          for (const { pattern, reason } of FORBIDDEN) {
            if (pattern.test(line)) {
              violations.push(`${relative(SRC, file)}:${index + 1} — ${reason}: ${line.trim()}`);
            }
          }
        });
    }
    expect(violations).toEqual([]);
  });
});
