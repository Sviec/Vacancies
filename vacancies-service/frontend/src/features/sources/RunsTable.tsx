import { History } from "lucide-react";
import type { ReactNode } from "react";

import type { ParseRunRead, RunStatus, SourceListItem } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Select } from "@/components/ui/fields";
import { Skeleton } from "@/components/ui/Skeleton";
import { SegmentedControl } from "@/components/ui/ToggleGroup";
import { RunStatusBadge } from "@/features/sources/RunStatusBadge";
import { formatDuration, formatRelativeDate } from "@/lib/format";

const ABSOLUTE = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

type StatusFilter = RunStatus | "all";

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "Все" },
  { value: "success", label: "Успешно" },
  { value: "failed", label: "Ошибка" },
  { value: "running", label: "Выполняется" },
];

interface RunsTableProps {
  runs: ParseRunRead[] | undefined;
  sources: SourceListItem[];
  isPending: boolean;
  isError: boolean;
  error: unknown;
  onRetry: () => void;
  retrying?: boolean;
  sourceId: string | null;
  status: RunStatus | null;
  onSourceChange: (id: string | null) => void;
  onStatusChange: (status: RunStatus | null) => void;
  onClearFilters: () => void;
  now: Date;
}

function slugById(sources: SourceListItem[], id: string): string {
  return sources.find((item) => item.id === id)?.slug ?? id.slice(0, 8);
}

/** История запусков с фильтрами источника и статуса (состояние в URL). */
export function RunsTable({
  runs,
  sources,
  isPending,
  isError,
  error,
  onRetry,
  retrying,
  sourceId,
  status,
  onSourceChange,
  onStatusChange,
  onClearFilters,
  now,
}: RunsTableProps) {
  const filtersActive = sourceId !== null || status !== null;

  let body: ReactNode;
  if (isPending) {
    body = <RunsTableSkeleton />;
  } else if (isError) {
    body = <ErrorState error={error} onRetry={onRetry} retrying={retrying} />;
  } else if (!runs || runs.length === 0) {
    body = (
      <EmptyState
        icon={History}
        title={filtersActive ? "Запусков по фильтру нет" : "Запусков пока нет"}
        description={
          filtersActive
            ? "Сбросьте фильтр, чтобы увидеть всю историю."
            : "История появится после первого запуска парсеров."
        }
        action={
          filtersActive ? (
            <Button variant="secondary" size="sm" onClick={onClearFilters}>
              Сбросить фильтр
            </Button>
          ) : undefined
        }
      />
    );
  } else {
    body = (
      <div className="overflow-x-auto rounded-card border border-line bg-surface shadow-card">
        <table className="w-full min-w-[800px] border-collapse text-left text-[13px]">
          <thead>
            <tr className="border-b border-line bg-surface-muted/60 text-ink-muted">
              <th className="px-4 py-3 font-medium">Начало</th>
              <th className="px-4 py-3 font-medium">Источник</th>
              <th className="px-4 py-3 font-medium">Длительность</th>
              <th className="px-4 py-3 font-medium">Статус</th>
              <th className="px-4 py-3 font-medium tabular-nums">Найдено / новых</th>
              <th className="px-4 py-3 font-medium">Ошибка</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id} className="border-b border-line last:border-b-0 hover:bg-surface-muted/40">
                <td
                  className="px-4 py-3 align-top text-ink-body"
                  title={ABSOLUTE.format(new Date(run.started_at))}
                >
                  {formatRelativeDate(run.started_at, now)}
                </td>
                <td className="px-4 py-3 align-top font-medium text-ink">
                  {slugById(sources, run.source_id)}
                </td>
                <td className="px-4 py-3 align-top text-ink-body">
                  {formatDuration(run.started_at, run.finished_at)}
                </td>
                <td className="px-4 py-3 align-top">
                  <RunStatusBadge status={run.status} />
                </td>
                <td className="px-4 py-3 align-top tabular-nums text-ink-body">
                  {run.items_found} / {run.items_new}
                </td>
                <td className="max-w-[280px] px-4 py-3 align-top">
                  {run.error_text ? (
                    <span className="line-clamp-2 text-danger" title={run.error_text}>
                      {run.error_text}
                    </span>
                  ) : (
                    <span className="text-ink-muted">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <section aria-labelledby="runs-table-heading" className="mt-10">
      <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <h2 id="runs-table-heading" className="text-[18px] font-semibold text-ink">
          История запусков
        </h2>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <Select
            label="Источник"
            value={sourceId ?? ""}
            onChange={(event) => onSourceChange(event.target.value || null)}
            containerClassName="min-w-[200px]"
          >
            <option value="">Все источники</option>
            {sources.map((source) => (
              <option key={source.id} value={source.id}>
                {source.slug}
              </option>
            ))}
          </Select>
          <div className="flex flex-col gap-2">
            <span className="text-[13px] font-medium text-ink-body">Статус</span>
            <SegmentedControl
              label="Статус запуска"
              options={STATUS_OPTIONS}
              value={status ?? "all"}
              onChange={(next) => onStatusChange(next === "all" ? null : next)}
            />
          </div>
        </div>
      </div>
      {body}
    </section>
  );
}

function RunsTableSkeleton() {
  return (
    <div
      aria-busy="true"
      aria-label="Загрузка истории запусков"
      className="overflow-hidden rounded-card border border-line bg-surface p-4 shadow-card"
    >
      <div className="space-y-3">
        {Array.from({ length: 5 }, (_, index) => (
          <div key={index} className="flex gap-4">
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-4 w-16" />
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-4 w-24" />
          </div>
        ))}
      </div>
    </div>
  );
}
