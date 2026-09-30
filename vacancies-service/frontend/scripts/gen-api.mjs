// Генерация типов API из OpenAPI работающего бэкенда.
// Кроссплатформенная замена `${OPENAPI_URL:-...}`, которой нет в PowerShell.
import { spawnSync } from "node:child_process";

const url = process.env.OPENAPI_URL ?? "http://localhost:8000/openapi.json";
const result = spawnSync(
  "npx",
  ["openapi-typescript", url, "-o", "src/api/schema.gen.ts"],
  { stdio: "inherit", shell: process.platform === "win32" },
);
process.exit(result.status ?? 1);
