/**
 * Тонкий клиент HTTP-API сервиса.
 *
 * Все пути — относительные (`/health`, `/api/v1/...`): на них настроен прокси
 * Vite, поэтому запрос всегда уходит на тот же origin и CORS в браузере не
 * возникает. Модуль не знает ничего про конкретные ресурсы.
 */

export const API_PREFIX = "/api/v1";

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

type QueryValue = string | number | boolean | null | undefined;

/**
 * Query-строка в формате бэкенда: массивы — повтором ключа, булевы —
 * `true`/`false`; `undefined`, `null`, `""` и пустые массивы пропускаются.
 * Возвращает строку с ведущим `?` или пустую строку.
 */
export function buildQuery(params: Record<string, QueryValue | readonly QueryValue[]>): string {
  const search = new URLSearchParams();
  for (const [key, raw] of Object.entries(params)) {
    const values = Array.isArray(raw) ? raw : [raw];
    for (const value of values) {
      if (value === undefined || value === null || value === "") {
        continue;
      }
      search.append(key, String(value));
    }
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
  } catch (error) {
    // Отмену запроса (react-query) не превращаем в сетевую ошибку.
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new ApiError("NETWORK_ERROR", "Сервис недоступен", 0);
  }

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

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/** Тело запроса в JSON для `apiFetch`. */
export function jsonBody(method: string, body: unknown): RequestInit {
  return { method, body: JSON.stringify(body) };
}
