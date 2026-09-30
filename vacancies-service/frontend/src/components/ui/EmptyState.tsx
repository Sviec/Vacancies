import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}

/** Пустое состояние: что случилось и что сделать дальше. */
export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center rounded-card border border-dashed border-line-strong bg-surface px-6 py-12 text-center",
        className,
      )}
    >
      {Icon && (
        <span className="mb-4 flex h-11 w-11 items-center justify-center rounded-full bg-accent-soft text-accent">
          <Icon size={20} strokeWidth={1.7} aria-hidden />
        </span>
      )}
      <h2 className="text-[16px] font-semibold text-ink">{title}</h2>
      {description && (
        <p className="mt-2 max-w-md text-[14px] leading-[1.5] text-ink-muted">{description}</p>
      )}
      {action && <div className="mt-5 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  );
}
