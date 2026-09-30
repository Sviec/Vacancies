/**
 * Быстрая проверка экрана /sources для чекпоинта 8d.
 * node scripts/stage8d-check.mjs
 */
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";
import { join } from "node:path";

const BASE = process.env.STAGE8D_BASE ?? "http://localhost:5173";
const API = "http://localhost:8000";
const OUT = join(process.env.TEMP || "/tmp", "stage8d");

const consoleErrors = [];
const checks = [];

function ok(name, detail = "") {
  checks.push({ name, ok: true, detail });
  console.log(`OK  ${name}${detail ? ` — ${detail}` : ""}`);
}
function fail(name, detail) {
  checks.push({ name, ok: false, detail });
  console.error(`FAIL ${name} — ${detail}`);
}

async function main() {
  const sources = await (await fetch(`${API}/api/v1/sources`)).json();
  const runs = await (await fetch(`${API}/api/v1/sources/runs?limit=50`)).json();

  const expectedLoc = {
    tg_it_jobs: "@demo_it_jobs",
    tg_relocate_remote: "@demo_relocate_jobs",
    html_careerhub: "https://careers.example.com/vacancies",
    html_jobboard: "https://jobs.example.org/it",
  };

  if (sources.items.length === 4) ok("api sources count", "4");
  else fail("api sources count", String(sources.items.length));

  if (runs.items.length === 11) ok("api runs count", "11");
  else fail("api runs count", String(runs.items.length));

  for (const [slug, loc] of Object.entries(expectedLoc)) {
    const item = sources.items.find((s) => s.slug === slug);
    if (item?.location === loc) ok(`location ${slug}`, loc);
    else fail(`location ${slug}`, JSON.stringify(item?.location));
  }

  const jobboard = sources.items.find((s) => s.slug === "html_jobboard");
  if (jobboard?.last_run_status === "failed") ok("html_jobboard failed");
  else fail("html_jobboard failed", String(jobboard?.last_run_status));

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    reducedMotion: "reduce",
  });
  const page = await context.newPage();
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));

  await page.goto(`${BASE}/sources`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { level: 1, name: "Источники" }).waitFor();

  for (const slug of Object.keys(expectedLoc)) {
    if (await page.getByText(slug, { exact: true }).first().isVisible()) ok(`ui slug ${slug}`);
    else fail(`ui slug ${slug}`, "не видно");
  }

  for (const loc of Object.values(expectedLoc)) {
    if (await page.getByText(loc, { exact: true }).first().isVisible()) ok(`ui location ${loc}`);
    else fail(`ui location ${loc}`, "не видно");
  }

  const runBtn = page.getByRole("button", { name: "Запустить" }).first();
  if (await runBtn.isDisabled()) ok("run button disabled");
  else fail("run button disabled", "кнопка активна");

  const title = await runBtn.getAttribute("title");
  if (title && title.includes("этап 11")) ok("run button hint", title);
  else fail("run button hint", String(title));

  // История: 11 строк в tbody второй таблицы
  const runRows = page.locator("section").filter({ hasText: "История запусков" }).locator("tbody tr");
  const n = await runRows.count();
  if (n === 11) ok("ui runs rows", "11");
  else fail("ui runs rows", String(n));

  if (consoleErrors.length === 0) ok("console clean");
  else fail("console clean", consoleErrors.join(" | "));

  await browser.close();

  writeFileSync(join(OUT, "check-report.json"), JSON.stringify({ checks, consoleErrors }, null, 2));
  const failed = checks.filter((c) => !c.ok);
  if (failed.length) {
    console.error(`\n${failed.length} failed`);
    process.exit(1);
  }
  console.log(`\nAll ${checks.length} checks passed`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
