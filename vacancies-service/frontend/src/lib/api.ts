/**
 * Тонкий клиент HTTP-API сервиса.
 *
 * Все пути — относительные (`/health`, `/api/v1/...`): на них настроен прокси
 * Vite, поэтому запрос всегда уходит на тот же origin и CORS в браузере не
 * возникает. Модуль переиспользуют все экраны этапа 8, поэтому он не знает
 * ничего про конкретные ресурсы.
 */

/** Конверт ошибки из раздела 6 ТЗ. */
interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: Record<string, unknown>;

  constructor(
    code: string,
    message: string,
    status: number,
    details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (typeof value !== "object" || value === null || !("error" in value)) {
    return false;
  }
  const payload = (value as { error: unknown }).error;
  return (
    typeof payload === "object" &&
    payload !== null &&
    typeof (payload as { code?: unknown }).code === "string" &&
    typeof (payload as { message?: unknown }).message === "string"
  );
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    // Тело может оказаться не JSON: например, ошибку вернул прокси, а не
    // приложение. Тогда отдаём обобщённый код, не теряя HTTP-статус.
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }

    if (isErrorEnvelope(body)) {
      throw new ApiError(
        body.error.code,
        body.error.message,
        response.status,
        body.error.details ?? {},
      );
    }

    throw new ApiError(
      "UNKNOWN_ERROR",
      `Сервис ответил статусом ${response.status}`,
      response.status,
    );
  }

  return (await response.json()) as T;
}

/** Зеркало pydantic-модели `CheckResult` из app/api/health.py. */
export interface CheckResult {
  status: "ok" | "error";
  latency_ms: number | null;
  error: string | null;
}

/** Зеркало pydantic-модели `HealthResponse` из app/api/health.py. */
export interface HealthResponse {
  status: "ok" | "degraded";
  version: string;
  checks: Record<string, CheckResult>;
}
