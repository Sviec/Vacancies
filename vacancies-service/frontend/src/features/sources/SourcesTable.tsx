import { Database } from "lucide-react";
import { useState } from "react";
import type { ReactNode } from "react";

import { ApiError } from "@/api/client";
import { useRunSource } from "@/api/sources";
import type { SourceListItem } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { RunStatusBadge } from "@/features/sources/RunStatusBadge";
import { runErrorMessage } from "@/features/sources/run-error";
import { sourceIcon } from "@/features/vacancies/source-meta";
import { cn } from "@/lib/cn";
import { FEATURES } from "@/lib/features";
import { formatRelativeDate } from "@/lib/format";
import { SOURCE_TYPE_LABELS } from "@/lib/labels";

const ABSOLUTE = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

interface SourcesTableProps {
  items: SourceListItem[] | undefined;
  isPending: boolean;
  isError: boolean;
  error: unknown;
  onRetry: () => void;
  retrying?: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
  now: Date;
}

function LocationCell({ source }: { source: SourceListItem }) {
  const value = source.location ?? null;
  if (!value) {
    return <span className="text-ink-muted">—</span>;
  }
  if (source.source_type === "html") {
    return (
      <a
        href={value}
        target="_blank"
        rel="noopener noreferrer"
        className="text-accent underline-offset-2 hover:underline"
        onClick={(event) => event.stopPropagation()}
      >
        {value}
      </a>
    );
  }
  return <span className="font-mono text-[13px]">{value}</span>;
}

function countsLabel(found: number | null | undefined, neu: number | null | undefined): string {
  if (found == null && neu == null) {
    return "—";
  }
  return `${found ?? "—"} / ${neu ?? "—"}`;
}

/** Таблица источников: slug, тип, канал/адрес, статус, счётчики, запуск. */
export function SourcesTable({
  items,
  isPending,
  isError,
  error,
  onRetry,
  retrying,
  selectedId,
  onSelect,
  now,
}: SourcesTableProps) {
  const [expandedError, setExpandedError] = useState<string | null>(null);
  const [rowState, setRowState] = useState<Record<string, { error?: string; queued?: boolean }>>(
    {},
  );
  const runMutation = useRunSource();

  const startRun = (sourceId: string) => {
    setRowState((current) => ({ ...current, [sourceId]: {} }));
    runMutation.mutate(sourceId, {
      onSuccess: () => {
        setRowState((current) => ({ ...current, [sourceId]: { queued: true } }));
      },
      onError: (error: unknown) => {
        const code = error instanceof ApiError ? error.code : "";
        setRowState((current) => ({ ...current, [sourceId]: { error: runErrorMessage(code) } }));
      },
    });
  };

  let body: ReactNode;
  if (isPending) {
    body = <SourcesTableSkeleton />;
  } else if (isError) {
    body = <ErrorState error={error} onRetry={onRetry} retrying={retrying} />;
  } else if (!items || items.length === 0) {
    body = (
      <EmptyState
        icon={Database}
        title="Источников нет"
        description="Наполните базу сидом: docker compose exec api python -m scripts.seed"
      />
    );
  } else {
    body = (
      <div className="overflow-x-auto rounded-card border border-line bg-surface shadow-card">
        <table className="w-full min-w-[880px] border-collapse text-left text-[13px]">
          <thead>
            <tr className="border-b border-line bg-surface-muted/60 text-ink-muted">
              <th className="px-4 py-3 font-medium">Slug</th>
              <th className="px-4 py-3 font-medium">Тип</th>
              <th className="px-4 py-3 font-medium">Канал / адрес</th>
              <th className="px-4 py-3 font-medium">Статус</th>
              <th className="px-4 py-3 font-medium">Последний запуск</th>
              <th className="px-4 py-3 font-medium tabular-nums">Найдено / новых</th>
              <th className="px-4 py-3 font-medium">Включён</th>
              <th className="px-4 py-3 font-medium">
                <span className="sr-only">Действия</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((source) => {
              const Icon = sourceIcon(source.source_type);
              const selected = selectedId === source.id;
              const showError =
                source.last_run_status === "failed" && Boolean(source.last_error);
              const expanded = expandedError === source.id;
              const pending = runMutation.isPending && runMutation.variables === source.id;
              const row = rowState[source.id];
              return (
                <tr
                  key={source.id}
                  aria-selected={selected}
                  onClick={() => onSelect(source.id)}
                  className={cn(
                    "cursor-pointer border-b border-line last:border-b-0",
                    selected ? "bg-accent-soft/50" : "hover:bg-surface-muted/40",
                  )}
                >
                  <td className="px-4 py-3 align-top">
                    <div className="font-medium text-ink">{source.slug}</div>
                    {showError && (
                      <button
                        type="button"
                        className={cn(
                          "mt-1 max-w-[240px] text-left text-[13px] leading-5 text-danger",
                          expanded ? "whitespace-pre-wrap" : "truncate",
                        )}
                        title={expanded ? "Свернуть" : "Показать ошибку полностью"}
                        onClick={(event) => {
                          event.stopPropagation();
                          setExpandedError(expanded ? null : source.id);
                        }}
                      >
                        {source.last_error}
                      </button>
                    )}
                  </td>
                  <td className="px-4 py-3 align-top">
                    <span className="inline-flex items-center gap-2 text-ink-body">
                      <Icon size={14} strokeWidth={1.7} aria-hidden className="text-accent" />
                      {SOURCE_TYPE_LABELS[source.source_type]}
                    </span>
                  </td>
                  <td className="px-4 py-3 align-top text-ink-body">
                    <LocationCell source={source} />
                  </td>
                  <td className="px-4 py-3 align-top">
                    <RunStatusBadge status={source.last_run_status} />
                  </td>
                  <td
                    className="px-4 py-3 align-top text-ink-body"
                    title={
                      source.last_run_at
                        ? ABSOLUTE.format(new Date(source.last_run_at))
                        : undefined
                    }
                  >
                    {formatRelativeDate(source.last_run_at, now)}
                  </td>
                  <td className="px-4 py-3 align-top tabular-nums text-ink-body">
                    {countsLabel(source.last_run_items_found, source.last_run_items_new)}
                  </td>
                  <td className="px-4 py-3 align-top text-ink-body">
                    {source.is_enabled ? "да" : "нет"}
                  </td>
                  <td className="px-4 py-3 align-top">
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={!FEATURES.runSource || pending}
                      onClick={(event) => {
                        event.stopPropagation();
                        startRun(source.id);
                      }}
                    >
                      Запустить
                    </Button>
                    {row?.queued ? (
                      <p className="mt-1 text-[13px] text-ink-muted">Поставлено в очередь</p>
                    ) : null}
                    {row?.error ? (
                      <p className="mt-1 max-w-[220px] text-[13px] leading-5 text-danger">
                        {row.error}
                      </p>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <section aria-labelledby="sources-table-heading">
      <h2 id="sources-table-heading" className="mb-4 text-[18px] font-semibold text-ink">
        Список источников
      </h2>
      {body}
    </section>
  );
}

function SourcesTableSkeleton() {
  return (
    <div
      aria-busy="true"
      aria-label="Загрузка источников"
      className="overflow-hidden rounded-card border border-line bg-surface p-4 shadow-card"
    >
      <div className="space-y-3">
        {Array.from({ length: 4 }, (_, index) => (
          <div key={index} className="flex gap-4">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-4 w-48" />
            <Skeleton className="h-4 w-16" />
            <Skeleton className="h-4 w-24" />
          </div>
        ))}
      </div>
    </div>
  );
}
