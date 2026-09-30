/**
 * Чекпоинт 8c: сценарий + скриншоты light/dark.
 * Запуск: node scripts/stage8c-check.mjs
 */
import { chromium } from "playwright";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const BASE = process.env.STAGE8C_BASE ?? "http://localhost:5173";
const OUT = process.env.STAGE8C_OUT ?? join(process.env.TEMP || "/tmp", "stage8c");
mkdirSync(OUT, { recursive: true });

const consoleErrors = [];
const report = { scores: {}, seedBefore: null, seedAfter: null, screenshots: [], checks: [] };

function ok(name, detail = "") {
  report.checks.push({ name, ok: true, detail });
  console.log(`OK  ${name}${detail ? ` — ${detail}` : ""}`);
}
function fail(name, detail) {
  report.checks.push({ name, ok: false, detail });
  console.error(`FAIL ${name} — ${detail}`);
}

async function api(path, init = {}) {
  const res = await fetch(`http://localhost:8000${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });
  const text = await res.text();
  return { status: res.status, body: text ? JSON.parse(text) : null };
}

async function shot(page, name) {
  const file = join(OUT, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  report.screenshots.push(file);
}

async function setTheme(page, theme) {
  await page.evaluate((t) => {
    document.documentElement.classList.toggle("dark", t === "dark");
    localStorage.setItem("vacancies.theme", t);
  }, theme);
  await page.waitForTimeout(150);
}

async function withPage(browser, fn) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));
  try {
    await fn(page);
  } finally {
    await context.close();
  }
}

async function main() {
  const listBefore = await api("/api/v1/resumes");
  report.seedBefore = listBefore.body.items.map((r) => ({
    id: r.id,
    title: r.title,
    score: r.score,
    origin: r.origin,
    is_primary: r.is_primary,
  }));
  const weak = report.seedBefore.find((r) => r.score != null && r.score < 4);
  const strong = report.seedBefore.find((r) => r.score != null && r.score >= 8);
  if (!weak || !strong) throw new Error("strong/weak not found in seed");
  ok("seed loaded", `strong=${strong.score}, weak=${weak.score}, n=${report.seedBefore.length}`);

  const browser = await chromium.launch({ headless: true });

  await withPage(browser, async (page) => {
    await page.goto(`${BASE}/resumes`, { waitUntil: "networkidle" });
    await page.waitForSelector("text=Мои резюме");
    await setTheme(page, "light");
    await shot(page, "resumes-list-light");
    await setTheme(page, "dark");
    await shot(page, "resumes-list-dark");
    ok("resumes list");
  });

  await withPage(browser, async (page) => {
    let release;
    const gate = new Promise((r) => {
      release = r;
    });
    await page.route("**/api/v1/resumes", async (route) => {
      if (route.request().method() !== "GET") return route.continue();
      await gate;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [] }),
      });
    });
    const nav = page.goto(`${BASE}/resumes`);
    await page.waitForSelector('[aria-busy="true"]');
    ok("list skeleton");
    release();
    await nav;
  });

  await withPage(browser, async (page) => {
    await page.route("**/api/v1/resumes", (route) => {
      if (route.request().method() !== "GET") return route.continue();
      return route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          error: { code: "INTERNAL_ERROR", message: "boom", details: {} },
        }),
      });
    });
    await page.goto(`${BASE}/resumes`, { waitUntil: "networkidle" });
    // QueryClient ретраит 5xx один раз — ждём финальный ErrorState.
    await page.getByRole("alert").waitFor({ timeout: 8000 });
    if (await page.getByRole("alert").isVisible()) ok("list error state");
    else fail("list error state", await page.locator("body").innerText());
  });

  await withPage(browser, async (page) => {
    await page.route("**/api/v1/resumes", (route) => {
      if (route.request().method() !== "GET") return route.continue();
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [] }),
      });
    });
    await page.goto(`${BASE}/resumes`, { waitUntil: "networkidle" });
    if (await page.getByText("Создайте первое резюме").isVisible()) ok("list empty state");
    else fail("list empty state", "нет");
  });

  await withPage(browser, async (page) => {
    await page.route("**/api/v1/resumes/**", (route) => {
      if (route.request().method() !== "GET") return route.continue();
      return route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "NOT_FOUND", message: "not found", details: {} } }),
      });
    });
    await page.goto(`${BASE}/resumes/00000000-0000-4000-8000-000000000099`, {
      waitUntil: "networkidle",
    });
    if (await page.getByText("Резюме не найдено").isVisible()) ok("editor 404");
    else fail("editor 404", "нет");
  });

  await withPage(browser, async (page) => {
    await page.goto(`${BASE}/resumes/${strong.id}`, { waitUntil: "networkidle" });
    await page.waitForSelector('[data-testid="score-circle"]');
    await setTheme(page, "light");
    await shot(page, "editor-strong-light");
    await setTheme(page, "dark");
    await shot(page, "editor-strong-dark");
    ok("editor strong screenshots");

    await page.goto(`${BASE}/resumes/${weak.id}`, { waitUntil: "networkidle" });
    await page.waitForSelector('[data-testid="score-circle"]');
    await setTheme(page, "light");
    await shot(page, "editor-weak-light");
    await setTheme(page, "dark");
    await shot(page, "editor-weak-dark");
    ok("editor weak screenshots");

    await page.getByRole("button", { name: /Сгенерировать через ИИ/i }).click();
    await page.waitForSelector("text=ИИ-генерация подключается на этапе 10");
    if (await page.getByRole("button", { name: /^Сгенерировать$/ }).isDisabled()) {
      ok("AI button disabled with hint");
    } else fail("AI button", "активна");
    await setTheme(page, "light");
    await shot(page, "ai-modal-light");
    await setTheme(page, "dark");
    await shot(page, "ai-modal-dark");
    await page.getByRole("button", { name: "Закрыть" }).last().click();
  });

  // duplicate → edit → restore → save → delete
  const dup = await api(`/api/v1/resumes/${weak.id}/duplicate`, { method: "POST" });
  if (dup.status !== 200 && dup.status !== 201) throw new Error(`duplicate ${dup.status}`);
  const copyId = dup.body.id;
  const scoreBefore = dup.body.score;
  report.scores.before = scoreBefore;
  ok("duplicated weak", `id=${copyId}, score=${scoreBefore}`);

  await withPage(browser, async (page) => {
    await page.goto(`${BASE}/resumes/${copyId}`, { waitUntil: "networkidle" });
    await page.waitForSelector("#skills");

    await page.getByRole("button", { name: "Добавить навык" }).click();
    await page.locator("#skills input").last().fill("graphql");
    await page
      .locator("#skills [role='group']")
      .last()
      .getByRole("button", { name: "Уровень 4" })
      .click();

    const ach = page.locator("#experience textarea").nth(1);
    const prevAch = await ach.inputValue();
    await ach.fill(`${prevAch}\nУвеличил покрытие тестами на 25%.`);

    await page.waitForTimeout(900);
    const stored = await page.evaluate(
      (id) => localStorage.getItem(`vacancies.resumeDraft.${id}`),
      copyId,
    );
    if (stored?.includes("graphql")) ok("local draft written");
    else fail("local draft", String(stored).slice(0, 160));

    await page.reload({ waitUntil: "networkidle" });
    await page.waitForSelector("text=Восстановлены несохранённые изменения");
    await setTheme(page, "light");
    await shot(page, "draft-banner-light");
    await setTheme(page, "dark");
    await shot(page, "draft-banner-dark");
    await page.getByRole("button", { name: "Продолжить" }).click();

    const values = await page
      .locator("#skills input")
      .evaluateAll((nodes) => nodes.map((n) => n.value));
    if (values.some((v) => v.toLowerCase() === "graphql")) ok("draft restored after reload");
    else fail("draft restore", JSON.stringify(values));

    if (await page.getByText("Оценка обновится после сохранения").isVisible()) {
      ok("score pending caption");
    } else fail("score pending caption", "нет");

    await page.getByRole("button", { name: /^Сохранить$/ }).click();
    await page.waitForSelector("text=Все изменения сохранены", { timeout: 15000 });
    await page.waitForTimeout(600);
  });

  const after = await api(`/api/v1/resumes/${copyId}`);
  report.scores.after = after.body.score;
  ok("saved copy", `score ${scoreBefore} → ${after.body.score}`);

  const del = await api(`/api/v1/resumes/${copyId}`, { method: "DELETE" });
  if (del.status === 204 || del.status === 200) ok("deleted copy");
  else fail("delete copy", `status=${del.status}`);

  const list = await api("/api/v1/resumes");
  if (!list.body.items.some((r) => r.id === copyId)) ok("copy absent from list/selector");
  else fail("copy still present", copyId);

  report.seedAfter = list.body.items.map((r) => ({
    id: r.id,
    title: r.title,
    score: r.score,
    origin: r.origin,
    is_primary: r.is_primary,
  }));
  const unchanged =
    report.seedAfter.length === report.seedBefore.length &&
    report.seedAfter.every((r) => {
      const b = report.seedBefore.find((x) => x.id === r.id);
      return b && b.score === r.score && b.title === r.title;
    });
  if (unchanged) ok("seed resumes unchanged");
  else fail("seed resumes", JSON.stringify({ before: report.seedBefore, after: report.seedAfter }));

  const realErrors = consoleErrors.filter(
    (e) =>
      !/Download the React DevTools/i.test(e) &&
      !/favicon/i.test(e) &&
      // Ожидаемые ошибки из page.route для skeleton/error/404 проверок.
      !/status of 500/i.test(e) &&
      !/status of 404/i.test(e),
  );
  if (realErrors.length === 0) ok("console clean");
  else fail("console errors", realErrors.join(" | "));

  writeFileSync(
    join(OUT, "report.json"),
    JSON.stringify({ report, consoleErrors: realErrors }, null, 2),
  );
  await browser.close();

  const failed = report.checks.filter((c) => !c.ok);
  console.log(`\nDone → ${OUT}`);
  console.log(`checks: ${report.checks.length - failed.length}/${report.checks.length} ok`);
  console.log(`score before/after save: ${report.scores.before} → ${report.scores.after}`);
  if (failed.length) process.exit(1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
