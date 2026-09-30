import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export type BadgeTone = "neutral" | "accent" | "positive" | "warn" | "danger" | "muted";

const TONES: Record<BadgeTone, string> = {
  neutral: "border-line bg-surface text-ink-body",
  accent: "border-accent-border bg-accent-soft text-accent",
  positive: "border-transparent bg-positive-soft text-positive",
  warn: "border-transparent bg-warn-soft text-warn",
  danger: "border-transparent bg-danger-soft text-danger",
  muted: "border-transparent bg-surface-muted text-ink-muted",
};

interface BadgeProps {
  tone?: BadgeTone;
  icon?: ReactNode;
  className?: string;
  title?: string;
  children: ReactNode;
}

/** Небольшая статусная метка: «основное», «Сохранено», статус запуска. */
export function Badge({ tone = "neutral", icon, className, title, children }: BadgeProps) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap",
        TONES[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}
