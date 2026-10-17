import { createBrowserRouter, Navigate } from "react-router";

import { AppShell } from "@/components/layout/AppShell";
import { ResumeEditorPage } from "@/features/editor/ResumeEditorPage";
import { AuthPage } from "@/features/auth/AuthPage";
import { RequireAuth } from "@/features/auth/RequireAuth";
import { ResumesPage } from "@/features/resumes/ResumesPage";
import { SourcesPage } from "@/features/sources/SourcesPage";
import { VacanciesPage } from "@/features/vacancies/VacanciesPage";
import { NotFound } from "@/pages/NotFound";
import { RouteError } from "@/pages/RouteError";

// Клиентские пути не должны начинаться с /api и /health: их забирает прокси Vite.
export const router = createBrowserRouter([
  { path: "login", element: <AuthPage mode="login" /> },
  { path: "register", element: <AuthPage mode="register" /> },
  {
    element: <RequireAuth />,
    errorElement: <RouteError />,
    children: [
      {
        element: <AppShell />,
        errorElement: <RouteError />,
        children: [
          {
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
    ],
  },
]);
