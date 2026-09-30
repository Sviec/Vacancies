/**
 * URL-состояние экрана «Источники»: фильтры истории запусков.
 * `source` — UUID источника, `status` — RunStatus или пусто (= все).
 */

import type { RunStatus } from "@/api/types";

const RUN_STATUSES = new Set<RunStatus>(["running", "success", "failed"]);

export interface SourcesUrlState {
  sourceId: string | null;
  status: RunStatus | null;
}

export function parseSourcesParams(params: URLSearchParams): SourcesUrlState {
  const rawSource = params.get("source");
  const sourceId = rawSource && /^[0-9a-f-]{36}$/i.test(rawSource) ? rawSource : null;
  const rawStatus = params.get("status");
  const status =
    rawStatus && RUN_STATUSES.has(rawStatus as RunStatus) ? (rawStatus as RunStatus) : null;
  return { sourceId, status };
}

/** Дефолты в URL не пишутся. */
export function serializeSourcesParams(state: SourcesUrlState): URLSearchParams {
  const params = new URLSearchParams();
  if (state.sourceId) {
    params.set("source", state.sourceId);
  }
  if (state.status) {
    params.set("status", state.status);
  }
  return params;
}
