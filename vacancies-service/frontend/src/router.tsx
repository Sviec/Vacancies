import { createBrowserRouter, Navigate } from "react-router";

import { AppShell } from "@/components/layout/AppShell";
import { ResumeEditorPage } from "@/features/editor/ResumeEditorPage";
import { ResumesPage } from "@/features/resumes/ResumesPage";
import { SourcesPage } from "@/features/sources/SourcesPage";
import { VacanciesPage } from "@/features/vacancies/VacanciesPage";
import { NotFound } from "@/pages/NotFound";
import { RouteError } from "@/pages/RouteError";

// Клиентские пути не должны начинаться с /api и /health: их забирает прокси Vite.
export const router = createBrowserRouter([
  {
    element: <AppShell />,
    errorElement: <RouteError />,
    children: [
      {
        // Ошибка экрана рендерится внутри оболочки, шапка и навигация остаются.
        errorElement: <RouteError />,
        children: [
          { index: true, element: <Navigate to="/vacancies" replace /> },
          { path: "vacancies", element: <VacanciesPage /> },
          { path: "resumes", element: <ResumesPage /> },
          { path: "resumes/:resumeId", element: <ResumeEditorPage /> },
          { path: "sources", element: <SourcesPage /> },
          { path: "*", element: <NotFound /> },
        ],
      },
    ],
  },
]);
