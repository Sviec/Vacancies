/**
 * Чекпоинт 8b: Playwright headless на http://localhost:5173.
 * Запуск: node scripts/stage8b-check.mjs
 */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

const BASE = process.env.STAGE8B_BASE || "http://localhost:5173";
const OUT = process.env.STAGE8B_OUT || path.join(os.tmpdir(), "stage8b");
const STRONG = "b5dd5923-81b3-46e0-bf37-079a7677aae5";
const WEAK = "71bf429e-b3f0-4e80-93df-230560584ac4";

fs.mkdirSync(OUT, { recursive: true });

const consoleErrors = [];
const failures = [];

function ok(name, cond, detail = "") {
  if (cond) {
    console.log(`PASS  ${name}${detail ? ` — ${detail}` : ""}`);
  } else {
    console.log(`FAIL  ${name}${detail ? ` — ${detail}` : ""}`);
    failures.push(name);
  }
}

async function shot(page, name) {
  const file = path.join(OUT, `${name}.png`);
  await page.screenshot({ path: file, fullPage: false });
  console.log(`SHOT  ${file}`);
  return file;
}

async function waitFeed(page) {
  await page.waitForSelector(
    '[aria-label="Вакансии"], [aria-label="Загружаем вакансии"], [role="alert"], h2',
    { timeout: 15000 },
  );
  await page
    .waitForFunction(() => !document.querySelector('[aria-label="Загружаем вакансии"]'), null, {
      timeout: 20000,
    })
    .catch(() => {});
}

async function firstTitles(page, n = 5) {
  return page.locator('[aria-label="Вакансии"] h3').evaluateAll(
    (nodes, limit) => nodes.slice(0, limit).map((el) => el.textContent?.trim() ?? ""),
    n,
  );
}

async function openWithResume(page, resumeId, extra = "") {
  const url = `${BASE}/vacancies?resume=${resumeId}${extra}`;
  await page.goto(url, { waitUntil: "networkidle", timeout: 30000 });
  await waitFeed(page);
}

async function applyTheme(page, theme) {
  await page.evaluate((t) => {
    localStorage.setItem("vacancies-theme", t);
    document.documentElement.classList.toggle("dark", t === "dark");
  }, theme);
}

async function delayFeedOnce(page, ms) {
  let armed = true;
  const handler = async (route) => {
    if (armed && route.request().method() === "GET") {
      armed = false;
      await new Promise((r) => setTimeout(r, ms));
    }
    await route.continue();
  };
  await page.route("**/api/v1/vacancies?*", handler);
  return async () => {
    armed = false;
    await page.unroute("**/api/v1/vacancies?*", handler).catch(() => {});
  };
}

async function fulfillFeed(page, body, status = 200) {
  const handler = async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status,
      contentType: "application/json",
      body: typeof body === "string" ? body : JSON.stringify(body),
    });
  };
  await page.route("**/api/v1/vacancies?*", handler);
  return async () => {
    await page.unroute("**/api/v1/vacancies?*", handler).catch(() => {});
  };
}

async function waitDialogGone(page) {
  await page
    .waitForFunction(() => !document.querySelector('[role="dialog"]'), null, { timeout: 5000 })
    .catch(() => {});
}

const browser = await chromium.launch({ headless: true });

async function withPage(theme, run) {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 900 },
    colorScheme: theme === "dark" ? "dark" : "light",
  });
  await context.addInitScript((t) => {
    localStorage.setItem("vacancies-theme", t);
  }, theme);
  const page = await context.newPage();
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      consoleErrors.push(msg.text());
    }
  });
  page.on("pageerror", (err) => {
    consoleErrors.push(String(err));
  });
  try {
    await run(page);
  } finally {
    await context.close();
  }
}

try {
  await withPage("light", async (page) => {
    await openWithResume(page, STRONG);
    const strongTitles = await firstTitles(page);
    ok("strong feed nonempty", strongTitles.length > 0, strongTitles[0] ?? "");
    await shot(page, "feed-strong-light");

    let sawSkeleton = false;
    const skeletonPromise = page
      .waitForSelector('[aria-label="Загружаем вакансии"]', { timeout: 8000 })
      .then(() => {
        sawSkeleton = true;
      })
      .catch(() => {});
    await page.selectOption('select[aria-label="Резюме для подбора"]', WEAK);
    await skeletonPromise;
    await waitFeed(page);
    const weakTitles = await firstTitles(page);
    ok("weak feed nonempty", weakTitles.length > 0, weakTitles[0] ?? "");
    ok(
      "strong→weak order changes",
      JSON.stringify(strongTitles) !== JSON.stringify(weakTitles),
      `strong[0]=${strongTitles[0]} weak[0]=${weakTitles[0]}`,
    );
    ok("skeleton on resume change", sawSkeleton);
    await shot(page, "feed-weak-light");

    await page.goto(
      `${BASE}/vacancies?resume=${STRONG}&work_format=remote&has_salary=true&salary_currency=USD`,
      { waitUntil: "networkidle", timeout: 30000 },
    );
    await waitFeed(page);
    const filteredCount = await page.locator('[aria-label="Вакансии"] h3').count();
    ok("remote+salary+USD nonempty", filteredCount > 0, `count=${filteredCount}`);

    await openWithResume(page, STRONG);
    await page.locator('[aria-label="Вакансии"] h3 a').first().click();
    await page.waitForSelector('[role="dialog"]', { timeout: 10000 });
    ok("drawer opens", await page.locator('[role="dialog"]').isVisible());
    await shot(page, "drawer-light");
    await page.keyboard.press("Escape");
    await waitDialogGone(page);
    ok("drawer closes on Esc", (await page.locator('[role="dialog"]').count()) === 0);

    await page.setViewportSize({ width: 700, height: 900 });
    await openWithResume(page, STRONG);
    await page.getByRole("button", { name: /Фильтры/ }).click();
    await page.waitForSelector('[role="dialog"]', { timeout: 5000 });
    ok("filters modal at 700px", await page.getByRole("heading", { name: "Фильтры" }).isVisible());
    await shot(page, "filters-modal-700-light");
    await page.keyboard.press("Escape");
    await waitDialogGone(page);

    await page.setViewportSize({ width: 1280, height: 900 });
    const clearDelay = await delayFeedOnce(page, 2500);
    const nav = page.goto(`${BASE}/vacancies?resume=${STRONG}&sort=date`, {
      waitUntil: "domcontentloaded",
      timeout: 30000,
    });
    await page.waitForSelector('[aria-label="Загружаем вакансии"]', { timeout: 10000 });
    await shot(page, "skeleton-light");
    await clearDelay();
    await nav.catch(() => {});
    await waitFeed(page);

    const clearEmpty = await fulfillFeed(page, {
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    });
    await page.goto(`${BASE}/vacancies?resume=${STRONG}&q=zzzzempty`, {
      waitUntil: "networkidle",
      timeout: 30000,
    });
    await page.waitForSelector("text=Ничего не нашлось", { timeout: 10000 });
    ok("empty state", await page.getByText("Ничего не нашлось").isVisible());
    await shot(page, "empty-light");
    await clearEmpty();

    const clearError = await fulfillFeed(
      page,
      {
        error: { code: "INTERNAL_ERROR", message: "Сбой для чекпоинта 8b", details: {} },
      },
      500,
    );
    await page.goto(`${BASE}/vacancies?resume=${STRONG}&q=zzzerror`, {
      waitUntil: "networkidle",
      timeout: 30000,
    });
    await page.waitForSelector('[role="alert"]', { timeout: 10000 });
    ok("error state", await page.getByRole("alert").isVisible());
    await shot(page, "error-light");
    await clearError();
  });

  await withPage("dark", async (page) => {
    await openWithResume(page, STRONG);
    await applyTheme(page, "dark");
    await shot(page, "feed-strong-dark");

    await page.selectOption('select[aria-label="Резюме для подбора"]', WEAK);
    await waitFeed(page);
    await shot(page, "feed-weak-dark");

    await page.locator('[aria-label="Вакансии"] h3 a').first().click();
    await page.waitForSelector('[role="dialog"]', { timeout: 10000 });
    await shot(page, "drawer-dark");
    await page.keyboard.press("Escape");
    await waitDialogGone(page);

    await page.setViewportSize({ width: 700, height: 900 });
    await openWithResume(page, STRONG);
    await page.getByRole("button", { name: /Фильтры/ }).click();
    await page.waitForSelector('[role="dialog"]', { timeout: 5000 });
    await shot(page, "filters-modal-700-dark");
    await page.keyboard.press("Escape");
    await waitDialogGone(page);

    await page.setViewportSize({ width: 1280, height: 900 });
    const clearDelay = await delayFeedOnce(page, 2500);
    const nav = page.goto(`${BASE}/vacancies?resume=${STRONG}&sort=salary`, {
      waitUntil: "domcontentloaded",
      timeout: 30000,
    });
    await page.waitForSelector('[aria-label="Загружаем вакансии"]', { timeout: 10000 });
    await shot(page, "skeleton-dark");
    await clearDelay();
    await nav.catch(() => {});
    await waitFeed(page);

    const clearEmpty = await fulfillFeed(page, {
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    });
    await page.goto(`${BASE}/vacancies?resume=${STRONG}&q=zzzzempty`, {
      waitUntil: "networkidle",
      timeout: 30000,
    });
    await page.waitForSelector("text=Ничего не нашлось", { timeout: 10000 });
    await shot(page, "empty-dark");
    await clearEmpty();

    const clearError = await fulfillFeed(
      page,
      {
        error: { code: "INTERNAL_ERROR", message: "Сбой для чекпоинта 8b", details: {} },
      },
      500,
    );
    await page.goto(`${BASE}/vacancies?resume=${STRONG}&q=zzzerror`, {
      waitUntil: "networkidle",
      timeout: 30000,
    });
    await page.waitForSelector('[role="alert"]', { timeout: 10000 });
    await shot(page, "error-dark");
    await clearError();
  });

  const realErrors = consoleErrors.filter(
    (text) =>
      !text.includes("Download the React DevTools") &&
      !/favicon/i.test(text) &&
      !text.includes("Failed to load resource: the server responded with a status of 500"),
  );
  ok("no browser console errors", realErrors.length === 0, realErrors.slice(0, 5).join(" | "));
} catch (error) {
  console.error("FATAL", error);
  failures.push(`fatal: ${error}`);
} finally {
  await browser.close();
}

console.log(`\nOUT=${OUT}`);
console.log(failures.length ? `FAILED: ${failures.join("; ")}` : "ALL CHECKS PASSED");
process.exit(failures.length ? 1 : 0);
