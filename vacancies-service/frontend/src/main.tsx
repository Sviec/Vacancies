import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "framer-motion";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router/dom";

import { ApiError } from "@/api/client";
import { ToasterProvider } from "@/components/ui/Toaster";
import { ThemeProvider } from "@/lib/theme";
import { router } from "@/router";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      // Одна попытка повтора и только для сетевых и серверных ошибок: 4xx
      // (не найдено, неверные параметры) повтор не исправит.
      retry: (failureCount, error) =>
        failureCount < 1 && !(error instanceof ApiError && error.status >= 400 && error.status < 500),
      refetchOnWindowFocus: false,
    },
  },
});

const container = document.getElementById("root");
if (container === null) {
  throw new Error("Не найден контейнер #root в index.html");
}

createRoot(container).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        {/* reducedMotion="user" гасит transform; opacity и длительность обнуляют пресеты motion.ts. */}
        <MotionConfig reducedMotion="user">
          <ToasterProvider>
            <RouterProvider router={router} />
          </ToasterProvider>
        </MotionConfig>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
);
