import { BriefcaseBusiness, Sparkles } from "lucide-react";
import { useEffect } from "react";
import type { ReactNode } from "react";
import { Link, NavLink, Outlet, ScrollRestoration } from "react-router";

import { useHealth } from "@/api/health";
import { ThemeToggle } from "@/components/ThemeToggle";
import { describeError } from "@/components/ui/ErrorState";
import { cn } from "@/lib/cn";

const NAV_ITEMS = [
  { to: "/vacancies", label: "Вакансии" },
  // Без `end`: на `/resumes/:id` (редактор) пункт тоже активен.
  { to: "/resumes", label: "Резюме" },
  { to: "/sources", label: "Источники" },
] as const;

/** Точка состояния API: один запрос `/health` при загрузке, без опроса. */
function HealthIndicator() {
  const { data, error, isPending } = useHealth();
  const ok = !error && data?.status === "ok";
  const title = isPending
    ? "Проверяем API…"
    : error
      ? `API недоступен: ${describeError(error)}`
      : `API ${data?.status === "ok" ? "работает" : "в деградации"} · версия ${data?.version ?? "—"}`;
  return (
    <span
      role="status"
      title={title}
      aria-label={title}
      className="flex h-8 items-center gap-2 rounded-lg px-2 text-[13px] text-ink-muted"
    >
      <span
        aria-hidden
        className={cn(
          "h-2 w-2 rounded-full",
          isPending ? "bg-line-strong" : ok ? "bg-positive" : "bg-danger",
        )}
      />
      <span className="hidden lg:inline">{isPending ? "API…" : ok ? "API" : "API недоступен"}</span>
    </span>
  );
}

export function AppShell() {
  return (
    <div className="min-h-[100dvh] bg-canvas font-sans text-ink">
      <header className="sticky top-0 z-30 border-b border-line bg-canvas/95 backdrop-blur-md">
        <div className="mx-auto flex h-[72px] max-w-[1480px] items-center justify-between gap-4 px-5 lg:px-10">
          <Link to="/vacancies" className="flex items-center gap-3 rounded-lg">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent text-on-accent shadow-card">
              <BriefcaseBusiness size={18} strokeWidth={1.7} aria-hidden />
            </span>
            <span className="hidden sm:block">
              <span className="block text-[14px] font-semibold tracking-[-0.01em] text-ink">Вакансии</span>
              <span className="block text-[11px] text-ink-subtle">карьерное пространство</span>
            </span>
          </Link>

          <nav aria-label="Основная навигация" className="flex items-center gap-1">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "relative rounded-lg px-3 py-2 text-[13px]",
                    isActive
                      ? "font-medium text-ink"
                      : "text-ink-muted hover:bg-surface-muted hover:text-ink",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    {item.label}
                    {isActive && (
                      <span aria-hidden className="absolute right-3 bottom-0 left-3 h-0.5 rounded-full bg-accent" />
                    )}
                  </>
                )}
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-1">
            <HealthIndicator />
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1480px] px-5 py-8 lg:px-10 lg:py-10">
        <Outlet />
      </main>
      <ScrollRestoration />
    </div>
  );
}

interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}

/**
 * Шапка страницы. TODO: заголовок 30/34px — зафиксированное исключение для
 * display-заголовка страницы; заголовки секций — 15–24px (раздел 8 ТЗ).
 */
export function PageHeader({ eyebrow, title, description, actions }: PageHeaderProps) {
  useEffect(() => {
    document.title = `${title} — Вакансии`;
  }, [title]);

  return (
    <div className="mb-8 flex flex-col justify-between gap-5 md:flex-row md:items-end">
      <div>
        {eyebrow && (
          <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold tracking-[0.16em] text-accent-muted uppercase">
            <Sparkles size={13} aria-hidden /> {eyebrow}
          </div>
        )}
        <h1 className="text-[30px] font-semibold tracking-[-0.045em] text-ink md:text-[34px]">{title}</h1>
        {description && <p className="mt-2 max-w-2xl text-[14px] leading-[1.5] text-ink-muted">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
