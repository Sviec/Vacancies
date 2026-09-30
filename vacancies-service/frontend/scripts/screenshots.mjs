/**
 * Скриншоты демо-фронтенда для visual-reviewer (подэтап 8d).
 *
 * Запуск из frontend/: `npm run shots`
 * Требует: http://localhost:5173 и API на :8000 (docker compose).
 * Chromium: при отсутствии — `npx playwright install chromium`.
 *
 * Кадры:
 *   - frontend/.screenshots/ (gitignored)
 *   - %TEMP%/stage8d/ — ключевые кадры для visual-reviewer
 */

import { chromium } from "playwright";
import { copyFileSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const BASE = process.env.SHOTS_BASE ?? "http://localhost:5173";
const API = process.env.SHOTS_API ?? "http://localhost:8000";
const OUT = join(ROOT, ".screenshots");
const TEMP_OUT = join(process.env.TEMP || tmpdir(), "stage8d");

mkdirSync(OUT, { recursive: true });
mkdirSync(TEMP_OUT, { recursive: true });

const KEY_SHOTS = new Set([
  "sources-1440-light",
  "sources-1440-dark",
  "sources-768-light",
  "sources-768-dark",
  "sources-runs-1440-light",
  "sources-skeleton-1440-light",
  "sources-empty-1440-light",
  "sources-error-1440-light",
  "vacancies-1440-light",
  "resumes-1440-light",
  "editor-1440-light",
]);

const report = { shots: [], errors: [], copied: [] };

async function api(path) {
  const res = await fetch(`${API}${path}`, {
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`API ${path} → ${res.status}`);
  }
  return res.json();
}

async function setTheme(page, theme) {
  await page.evaluate((t) => {
    document.documentElement.classList.toggle("dark", t === "dark");
    localStorage.setItem("vacancies-theme", t);
  }, theme);
  await page.waitForTimeout(120);
}

async function shot(page, name) {
  const file = join(OUT, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  report.shots.push(file);
  if (KEY_SHOTS.has(name)) {
    const dest = join(TEMP_OUT, `${name}.png`);
    copyFileSync(file, dest);
    report.copied.push(dest);
  }
  console.log(`shot ${name}`);
}

async function withContext(browser, width, fn) {
  const context = await browser.newContext({
    viewport: { width, height: 900 },
    colorScheme: "light",
    reducedMotion: "reduce",
  });
  const page = await context.newPage();
  page.on("pageerror", (err) => report.errors.push(String(err)));
  page.on("console", (msg) => {
    if (msg.type() !== "error") {
      return;
    }
    const text = msg.text();
    // Ожидаемо при съёмке error-state через page.route(500).
    if (text.includes("status of 500")) {
      return;
    }
    report.errors.push(text);
  });
  try {
    await fn(page);
  } finally {
    await context.close();
  }
}

const ERROR_BODY = JSON.stringify({
  error: { code: "INTERNAL_ERROR", message: "Сбой для скриншота", details: {} },
});

async function main() {
  const resumes = await api("/api/v1/resumes");
  const sources = await api("/api/v1/sources");
  const runs = await api("/api/v1/sources/runs?limit=50");

  const strong = resumes.items.find((r) => r.score != null && r.score >= 8);
  const weak = resumes.items.find((r) => r.score != null && r.score < 4);
  if (!strong || !weak) {
    throw new Error("В сиде нет strong/weak резюме");
  }
  if (sources.items.length !== 4) {
    console.warn(`ожидали 4 источника, получили ${sources.items.length}`);
  }
  if (runs.items.length !== 11) {
    console.warn(`ожидали 11 запусков, получили ${runs.items.length}`);
  }

  console.log(
    `seed: sources=${sources.items.length}, runs=${runs.items.length}, strong=${strong.score}, weak=${weak.score}`,
  );

  let browser;
  try {
    browser = await chromium.launch({ headless: true });
  } catch (err) {
    console.error("Chromium не найден. Установите: npx playwright install chromium");
    throw err;
  }

  // —— Источники: light/dark × 1440/768 ——
  for (const width of [1440, 768]) {
    for (const theme of ["light", "dark"]) {
      await withContext(browser, width, async (page) => {
        await page.goto(`${BASE}/sources`, { waitUntil: "networkidle" });
        await page.getByRole("heading", { level: 1, name: "Источники" }).waitFor();
        await setTheme(page, theme);
        await shot(page, `sources-${width}-${theme}`);
      });
    }
  }

  // История (с прокруткой к секции) — light 1440
  await withContext(browser, 1440, async (page) => {
    await page.goto(`${BASE}/sources`, { waitUntil: "networkidle" });
    await page.getByRole("heading", { name: "История запусков" }).scrollIntoViewIfNeeded();
    await setTheme(page, "light");
    await shot(page, "sources-runs-1440-light");
  });

  // Skeleton источников (задержка ответа)
  await withContext(browser, 1440, async (page) => {
    let release;
    const gate = new Promise((r) => {
      release = r;
    });
    await page.route("**/api/v1/sources", async (route) => {
      if (route.request().method() !== "GET") {
        return route.continue();
      }
      await gate;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [] }),
      });
    });
    await page.route("**/api/v1/sources/runs**", async (route) => {
      if (route.request().method() !== "GET") {
        return route.continue();
      }
      await gate;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [] }),
      });
    });
    const nav = page.goto(`${BASE}/sources`);
    await page.waitForSelector('[aria-busy="true"]', { timeout: 8000 });
    await setTheme(page, "light");
    await shot(page, "sources-skeleton-1440-light");
    release();
    await nav.catch(() => {});
  });

  // Empty
  await withContext(browser, 1440, async (page) => {
    await page.route("**/api/v1/sources", (route) => {
      if (route.request().method() !== "GET") {
        return route.continue();
      }
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [] }),
      });
    });
    await page.route("**/api/v1/sources/runs**", (route) => {
      if (route.request().method() !== "GET") {
        return route.continue();
      }
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [] }),
      });
    });
    await page.goto(`${BASE}/sources`, { waitUntil: "networkidle" });
    await page.getByText("Источников нет").waitFor();
    await setTheme(page, "light");
    await shot(page, "sources-empty-1440-light");
  });

  // Error
  await withContext(browser, 1440, async (page) => {
    await page.route("**/api/v1/sources", (route) => {
      if (route.request().method() !== "GET") {
        return route.continue();
      }
      return route.fulfill({
        status: 500,
        contentType: "application/json",
        body: ERROR_BODY,
      });
    });
    await page.goto(`${BASE}/sources`, { waitUntil: "networkidle" });
    await page.getByRole("alert").waitFor({ timeout: 10000 });
    await setTheme(page, "light");
    await shot(page, "sources-error-1440-light");
  });

  // Лента / резюме / редактор — по одному кадру 1440 light
  await withContext(browser, 1440, async (page) => {
    await page.goto(`${BASE}/vacancies?resume=${strong.id}&sort=match`, {
      waitUntil: "networkidle",
    });
    await page.getByRole("heading", { name: "Вакансии" }).waitFor();
    await setTheme(page, "light");
    await shot(page, "vacancies-1440-light");
  });

  await withContext(browser, 1440, async (page) => {
    await page.goto(`${BASE}/resumes`, { waitUntil: "networkidle" });
    await page.getByRole("heading", { name: "Мои резюме" }).waitFor();
    await setTheme(page, "light");
    await shot(page, "resumes-1440-light");
  });

  await withContext(browser, 1440, async (page) => {
    await page.goto(`${BASE}/resumes/${strong.id}`, { waitUntil: "networkidle" });
    await page.waitForSelector("text=Оценка", { timeout: 10000 }).catch(() => {});
    await setTheme(page, "light");
    await shot(page, "editor-1440-light");
  });

  // Доп. кадры по матрице плана (лента weak, drawer, фильтры, сохранённые) — в .screenshots
  await withContext(browser, 1440, async (page) => {
    await page.goto(`${BASE}/vacancies?resume=${weak.id}&sort=match`, {
      waitUntil: "networkidle",
    });
    await setTheme(page, "light");
    await shot(page, "vacancies-weak-1440-light");
  });

  // Drawer через URL
  const vacancies = await api(`/api/v1/vacancies?resume_id=${strong.id}&page_size=1`);
  const sampleVacancy = vacancies.items[0];

  await withContext(browser, 1440, async (page) => {
    const id = sampleVacancy?.id;
    const url = id
      ? `${BASE}/vacancies?resume=${strong.id}&sort=match&vacancy=${id}`
      : `${BASE}/vacancies?resume=${strong.id}&sort=match`;
    await page.goto(url, { waitUntil: "networkidle" });
    await setTheme(page, "light");
    await shot(page, "vacancies-drawer-1440-light");
  });

  await withContext(browser, 700, async (page) => {
    await page.goto(`${BASE}/vacancies`, { waitUntil: "networkidle" });
    const filtersBtn = page.getByRole("button", { name: /Фильтры/ });
    if (await filtersBtn.isVisible().catch(() => false)) {
      await filtersBtn.click();
      await page.waitForTimeout(300);
    }
    await setTheme(page, "light");
    await shot(page, "vacancies-filters-modal-700-light");
  });

  await withContext(browser, 1440, async (page) => {
    await page.goto(`${BASE}/vacancies?saved=true`, { waitUntil: "networkidle" });
    await setTheme(page, "light");
    await shot(page, "vacancies-saved-1440-light");
  });

  await withContext(browser, 1440, async (page) => {
    await page.goto(`${BASE}/resumes/${weak.id}`, { waitUntil: "networkidle" });
    await setTheme(page, "light");
    await shot(page, "editor-weak-1440-light");
  });

  // Тёмные дополнительные для источников уже сняты выше; тёмная лента/резюме
  await withContext(browser, 1440, async (page) => {
    await page.goto(`${BASE}/vacancies?resume=${strong.id}`, { waitUntil: "networkidle" });
    await setTheme(page, "dark");
    await shot(page, "vacancies-1440-dark");
  });

  await withContext(browser, 1440, async (page) => {
    await page.goto(`${BASE}/resumes`, { waitUntil: "networkidle" });
    await setTheme(page, "dark");
    await shot(page, "resumes-1440-dark");
  });

  await browser.close();

  const summaryPath = join(OUT, "report.json");
  writeFileSync(
    summaryPath,
    JSON.stringify(
      {
        base: BASE,
        sources: sources.items.length,
        runs: runs.items.length,
        locations: sources.items.map((s) => ({ slug: s.slug, location: s.location })),
        shots: report.shots,
        copied: report.copied,
        errors: report.errors,
      },
      null,
      2,
    ),
  );

  console.log(`\nГотово: ${report.shots.length} кадров в ${OUT}`);
  console.log(`Ключевые копии: ${TEMP_OUT} (${report.copied.length})`);
  if (report.errors.length) {
    console.warn("Ошибки консоли:", report.errors.slice(0, 10));
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
