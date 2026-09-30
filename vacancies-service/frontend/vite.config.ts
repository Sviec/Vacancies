/// <reference types="vitest/config" />
import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Tailwind 4 подключается плагином Vite (CSS-first): tailwind.config.js и
// postcss.config.js не нужны, вся тема живёт в src/index.css.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    watch: {
      // Bind-mount через Docker Desktop на Windows не отдаёт inotify-события,
      // поэтому в контейнере VITE_USE_POLLING=true (см. docker-compose.yml).
      usePolling: process.env.VITE_USE_POLLING === "true",
    },
    // Принципиальное решение: фронтенд ходит только по ОТНОСИТЕЛЬНЫМ путям
    // (/api/v1/..., /health), а на бэкенд их уводит этот прокси. Поэтому в
    // браузере CORS не возникает вообще, а в Docker запрос идёт на
    // http://api:8000 по внутреннему DNS Compose. Переменной вида
    // VITE_API_BASE_URL с абсолютным хостом в проекте сознательно нет.
    // Клиентские маршруты поэтому не должны начинаться с /api и /health.
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
      },
      "/health": {
        target: process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  // Тесты только для чистых функций (решение по этапу 8): среда node, без DOM.
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
