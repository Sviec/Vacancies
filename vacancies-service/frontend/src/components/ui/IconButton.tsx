import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

interface IconButtonProps extends Omit<ComponentProps<"button">, "aria-label" | "title"> {
  /** Обязательная подпись: иконка без текста иначе недоступна для скринридера. */
  label: string;
}

export function IconButton({ label, className, type = "button", ...props }: IconButtonProps) {
  return (
    <button
      type={type}
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-lg p-2 text-ink-muted",
        "hover:bg-surface-muted hover:text-accent disabled:cursor-not-allowed disabled:opacity-60",
        className,
      )}
      {...props}
    />
  );
}
