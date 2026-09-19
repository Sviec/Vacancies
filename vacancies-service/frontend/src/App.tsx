import { useQuery } from "@tanstack/react-query";
import { BriefcaseBusiness, RotateCw } from "lucide-react";

import { ThemeToggle } from "@/components/ThemeToggle";
import { ApiError, apiFetch } from "@/lib/api";
import type { CheckResult, HealthResponse } from "@/lib/api";

const CHECK_LABELS: Record<string, string> = {
  database: "PostgreSQL",
  redis: "Redis",
};

const NEXT_SCREENS = [
  "Вакансии — лента карточек с процентом соответствия и фильтрами",
  "Мои резюме — список резюме с оценкой и действиями",
  "Редактор резюме — форма по секциям и живая оценка",
  "Источники — таблица парсеров и история запусков",
];

function CheckRow({ name, check }: { name: string; check: CheckResult }) {
  const ok = check.status === "ok";
  return (
    <div className="flex items-center justify-between border-t border-line py-3 first:border-t-0">
      <div className="flex items-center gap-2.5">
        <span
          aria-hidden
          className={`h-2 w-2 rounded-full ${ok ? "bg-positive" : "bg-danger"}`}
        />
        <span className="text-[14px] text-ink">{CHECK_LABELS[name] ?? name}</span>
      </div>
      <span className="text-[13px] text-ink-muted">
        {ok
          ? `${check.latency_ms ?? 0} мс`
          : `ошибка: ${check.error ?? "неизвестная"}`}
      </span>
    </div>
  );
}

function HealthSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Загрузка состояния сервиса">
      <div className="skeleton h-5 w-44 rounded-md" />
      <div className="skeleton h-4 w-full rounded-md" />
      <div className="skeleton h-4 w-3/5 rounded-md" />
    </div>
  );
}

export default function App() {
  const { data, error, isPending, isFetching, refetch } = useQuery({
    queryKey: ["health"],
    // TODO: допущение — /health отдаёт 503 при деградации, поэтому apiFetch
    // бросает ApiError и карточка уходит в состояние ошибки, не показывая,
    // какая именно зависимость упала. Разделить на этапе 8, если понадобится.
    queryFn: () => apiFetch<HealthResponse>("/health"),
  });

  // react-query сохраняет данные последнего успешного запроса, поэтому после
  // неудачного refetch правдивы сразу и `data`, и `error`. Состояния раздела 8
  // взаимоисключающие: при ошибке показываем только её.
  const health = error ? null : data;

  return (
    <div className="min-h-screen bg-canvas font-sans text-ink">
      <header className="sticky top-0 z-30 border-b border-line bg-canvas/95 backdrop-blur-md">
        <div className="mx-auto flex h-[72px] max-w-[1480px] items-center justify-between px-5 lg:px-10">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent text-on-accent shadow-sm">
              <BriefcaseBusiness size={18} strokeWidth={1.7} />
            </span>
            <span>
              <span className="block text-[14px] font-semibold tracking-[-0.01em] text-ink">
                Вакансии
              </span>
              <span className="block text-[11px] text-ink-subtle">
                карьерное пространство
              </span>
            </span>
          </div>
          <ThemeToggle />
        </div>
      </header>

      <main className="mx-auto max-w-[1480px] px-5 py-8 lg:px-10 lg:py-10">
        <div className="mb-8">
          <h1 className="text-[30px] font-semibold tracking-[-0.045em] text-ink md:text-[34px]">
            Сервис запущен
          </h1>
          <p className="mt-2 max-w-2xl text-[14px] leading-6 text-ink-muted">
            Этап 1: каркас бэкенда, Docker и базовый фронтенд. Карточка ниже
            обращается к <code className="text-ink">/health</code> через прокси
            Vite — это сквозная проверка связки фронтенда и API.
          </p>
        </div>

        <section className="rise lift max-w-xl rounded-2xl border border-line bg-surface p-6 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-[15px] font-semibold text-ink">Состояние сервиса</h2>
            {health && (
              <span
                className={`rounded-full px-2.5 py-1 text-[12px] font-medium ${
                  health.status === "ok"
                    ? "bg-positive-soft text-positive"
                    : "bg-warn-soft text-warn"
                }`}
              >
                {health.status === "ok" ? "Всё работает" : "Деградация"}
              </span>
            )}
          </div>

          {isPending && <HealthSkeleton />}

          {error && (
            <div>
              <p className="text-[14px] leading-6 text-ink">
                Не удалось получить состояние сервиса.
              </p>
              <p className="mt-1 text-[13px] leading-6 text-danger">
                {error instanceof ApiError
                  ? `${error.code}: ${error.message}`
                  : error.message}
              </p>
              <button
                type="button"
                onClick={() => void refetch()}
                disabled={isFetching}
                className="mt-4 inline-flex items-center gap-2 rounded-lg bg-accent px-3.5 py-2 text-[13px] font-medium text-on-accent hover:opacity-90 disabled:opacity-60"
              >
                <RotateCw size={15} strokeWidth={1.8} />
                Повторить
              </button>
            </div>
          )}

          {health && (
            <div>
              <p className="mb-2 text-[13px] text-ink-muted">
                Версия {health.version}
              </p>
              {Object.entries(health.checks).map(([name, check]) => (
                <CheckRow key={name} name={name} check={check} />
              ))}
            </div>
          )}
        </section>

        <section className="mt-6 max-w-xl rounded-2xl border border-line bg-surface-muted p-6">
          <h2 className="text-[14px] font-semibold text-ink">Что появится дальше</h2>
          <p className="mt-1 text-[13px] leading-6 text-ink-muted">
            Полноценные экраны приходят на этапе 8 и работают на сид-данных:
          </p>
          <ul className="mt-3 space-y-2">
            {NEXT_SCREENS.map((item) => (
              <li key={item} className="flex gap-2 text-[13px] leading-6 text-ink-muted">
                <span aria-hidden className="mt-2 h-1 w-1 shrink-0 rounded-full bg-ink-subtle" />
                {item}
              </li>
            ))}
          </ul>
        </section>
      </main>
    </div>
  );
}
