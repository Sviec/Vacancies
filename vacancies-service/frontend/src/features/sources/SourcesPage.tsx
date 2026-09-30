import { useMemo } from "react";
import { useSearchParams } from "react-router";

import { useRuns, useSources } from "@/api/sources";
import type { RunStatus } from "@/api/types";
import { PageHeader } from "@/components/layout/AppShell";
import { Skeleton } from "@/components/ui/Skeleton";
import { RunsTable } from "@/features/sources/RunsTable";
import { SourcesTable } from "@/features/sources/SourcesTable";
import {
  parseSourcesParams,
  serializeSourcesParams,
  type SourcesUrlState,
} from "@/features/sources/sources-url";

function SummaryTile({
  label,
  value,
  pending,
}: {
  label: string;
  value: number;
  pending: boolean;
}) {
  return (
    <div className="rounded-card border border-line bg-surface px-4 py-4 shadow-card">
      <p className="text-[13px] text-ink-muted">{label}</p>
      {pending ? (
        <Skeleton className="mt-2 h-8 w-12" />
      ) : (
        <p className="mt-2 text-[24px] font-semibold tracking-tight text-ink tabular-nums">{value}</p>
      )}
    </div>
  );
}

/** Технический экран источников и истории запусков парсеров. */
export function SourcesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const urlState = useMemo(() => parseSourcesParams(searchParams), [searchParams]);
  const now = useMemo(() => new Date(), []);

  const sourcesQuery = useSources();
  const runsQuery = useRuns({
    source_id: urlState.sourceId ?? undefined,
    status: urlState.status ?? undefined,
    limit: 50,
  });

  const items = useMemo(
    () => sourcesQuery.data?.items ?? [],
    [sourcesQuery.data?.items],
  );
  const summary = useMemo(() => {
    const total = items.length;
    const success = items.filter((item) => item.last_run_status === "success").length;
    const failed = items.filter((item) => item.last_run_status === "failed").length;
    return { total, success, failed };
  }, [items]);

  const setUrl = (next: SourcesUrlState) => {
    setSearchParams(serializeSourcesParams(next), { replace: true });
  };

  const patchUrl = (patch: Partial<SourcesUrlState>) => {
    setUrl({ ...urlState, ...patch });
  };

  return (
    <div>
      <PageHeader
        eyebrow="Технический экран"
        title="Источники"
        description="Парсеры вакансий, статус последнего запуска и история. Config наружу не отдаётся — только канал или URL."
      />

      <div className="mb-8 grid gap-4 sm:grid-cols-3">
        <SummaryTile
          label="Всего источников"
          value={summary.total}
          pending={sourcesQuery.isPending}
        />
        <SummaryTile
          label="Успешных последних"
          value={summary.success}
          pending={sourcesQuery.isPending}
        />
        <SummaryTile
          label="С ошибкой"
          value={summary.failed}
          pending={sourcesQuery.isPending}
        />
      </div>

      <SourcesTable
        items={sourcesQuery.data?.items}
        isPending={sourcesQuery.isPending}
        isError={sourcesQuery.isError}
        error={sourcesQuery.error}
        onRetry={() => void sourcesQuery.refetch()}
        retrying={sourcesQuery.isFetching}
        selectedId={urlState.sourceId}
        onSelect={(id) =>
          patchUrl({ sourceId: urlState.sourceId === id ? null : id })
        }
        now={now}
      />

      <RunsTable
        runs={runsQuery.data?.items}
        sources={items}
        isPending={runsQuery.isPending}
        isError={runsQuery.isError}
        error={runsQuery.error}
        onRetry={() => void runsQuery.refetch()}
        retrying={runsQuery.isFetching}
        sourceId={urlState.sourceId}
        status={urlState.status}
        onSourceChange={(id) => patchUrl({ sourceId: id })}
        onStatusChange={(status: RunStatus | null) => patchUrl({ status })}
        onClearFilters={() => setUrl({ sourceId: null, status: null })}
        now={now}
      />
    </div>
  );
}
