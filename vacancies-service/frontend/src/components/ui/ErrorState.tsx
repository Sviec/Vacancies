import { AlertTriangle, RotateCw } from "lucide-react";

import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";

/** Понятный текст ошибки по коду из конверта API. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case "NETWORK_ERROR":
        return "Сервис недоступен. Проверьте, что запущен docker compose";
      case "NOT_FOUND":
        return "Не найдено: запись могла быть удалена";
      case "VALIDATION_ERROR":
        return "Некорректные параметры запроса";
      default:
        return error.message;
    }
  }
  return error instanceof Error ? error.message : "Неизвестная ошибка";
}

interface ErrorStateProps {
  error: unknown;
  onRetry?: () => void;
  /** Повторный запрос уже идёт — кнопка заблокирована. */
  retrying?: boolean;
  compact?: boolean;
  title?: string;
  className?: string;
}

export function ErrorState({
  error,
  onRetry,
  retrying = false,
  compact = false,
  title = "Не удалось загрузить данные",
  className,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      className={cn(
        "rounded-card border border-line bg-surface",
        compact ? "p-4" : "flex flex-col items-center px-6 py-12 text-center",
        className,
      )}
    >
      {!compact && (
        <span className="mb-4 flex h-11 w-11 items-center justify-center rounded-full bg-danger-soft text-danger">
          <AlertTriangle size={20} strokeWidth={1.7} aria-hidden />
        </span>
      )}
      <h2 className={cn("font-semibold text-ink", compact ? "text-[14px]" : "text-[16px]")}>
        {title}
      </h2>
      <p className="mt-1.5 text-[13px] leading-[1.5] text-danger">{describeError(error)}</p>
      {onRetry && (
        <Button
          variant="secondary"
          size="sm"
          onClick={onRetry}
          disabled={retrying}
          className={compact ? "mt-3" : "mt-5"}
        >
          <RotateCw size={14} strokeWidth={1.8} aria-hidden />
          {retrying ? "Повторяем…" : "Повторить"}
        </Button>
      )}
    </div>
  );
}
