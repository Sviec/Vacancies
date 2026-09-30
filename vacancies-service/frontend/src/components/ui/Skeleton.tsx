import { cn } from "@/lib/cn";

interface SkeletonProps {
  className?: string;
  rounded?: "sm" | "md" | "lg" | "full" | "card";
}

const ROUNDED: Record<NonNullable<SkeletonProps["rounded"]>, string> = {
  sm: "rounded-sm",
  md: "rounded-md",
  lg: "rounded-lg",
  full: "rounded-full",
  card: "rounded-card",
};

/**
 * Плейсхолдер загрузки (shimmer из index.css). Контейнер группы skeleton'ов
 * должен нести `aria-busy="true"` и подпись.
 */
export function Skeleton({ className, rounded = "md" }: SkeletonProps) {
  return <div aria-hidden className={cn("skeleton", ROUNDED[rounded], className)} />;
}
