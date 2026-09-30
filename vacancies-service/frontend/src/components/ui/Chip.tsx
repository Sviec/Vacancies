import { X } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export type ChipTone = "neutral" | "positive" | "muted" | "danger";

const TONES: Record<ChipTone, string> = {
  neutral: "border-line bg-surface-muted text-ink-body",
  positive: "border-transparent bg-positive-soft text-positive",
  muted: "border-line-strong border-dashed bg-transparent text-ink-muted",
  danger: "border-transparent bg-danger-soft text-danger",
};

interface ChipProps {
  tone?: ChipTone;
  children: ReactNode;
  className?: string;
  /** Кнопка удаления справа; подпись — для скринридера. */
  onRemove?: () => void;
  removeLabel?: string;
}

/** Навык или значение: «python», «+3». */
export function Chip({ tone = "neutral", children, className, onRemove, removeLabel }: ChipProps) {
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center gap-1 rounded-md border px-2 py-1 text-[12px] leading-none",
        TONES[tone],
        className,
      )}
    >
      <span className="truncate">{children}</span>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={removeLabel ?? "Удалить"}
          title={removeLabel ?? "Удалить"}
          className="-mr-0.5 rounded p-0.5 text-current opacity-70 hover:opacity-100"
        >
          <X size={12} strokeWidth={2} />
        </button>
      )}
    </span>
  );
}
