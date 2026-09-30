import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/**
 * tailwind-merge должен знать токены темы из index.css: иначе `shadow-card`
 * он примет за цвет тени, а `rounded-card` не сможет перекрыть `rounded-lg`.
 */
const twMerge = extendTailwindMerge({
  extend: {
    theme: {
      color: [
        "canvas",
        "surface",
        "surface-muted",
        "surface-inset",
        "line",
        "line-strong",
        "line-cool",
        "ink",
        "ink-body",
        "ink-muted",
        "ink-subtle",
        "accent",
        "accent-soft",
        "accent-hover",
        "accent-border",
        "accent-muted",
        "on-accent",
        "positive",
        "positive-soft",
        "warn",
        "warn-soft",
        "danger",
        "danger-soft",
        "overlay",
      ],
      shadow: ["card", "pop", "modal", "drawer"],
      radius: ["card"],
    },
  },
});

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
