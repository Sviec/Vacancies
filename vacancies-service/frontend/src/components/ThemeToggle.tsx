import { Monitor, Moon, Sun } from "lucide-react";

import { useTheme } from "@/lib/theme";
import type { Theme } from "@/lib/theme";

const ORDER: Theme[] = ["light", "dark", "system"];

const LABELS: Record<Theme, string> = {
  light: "Светлая тема",
  dark: "Тёмная тема",
  system: "Тема как в системе",
};

/** Кнопка циклического переключения светлая → тёмная → системная. */
export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const next = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length];

  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      title={LABELS[theme]}
      aria-label={`${LABELS[theme]}. Переключить на: ${LABELS[next].toLowerCase()}`}
      className="rounded-lg border border-line p-2 text-ink-muted hover:bg-surface-muted hover:text-ink"
    >
      {theme === "light" && <Sun size={17} strokeWidth={1.7} />}
      {theme === "dark" && <Moon size={17} strokeWidth={1.7} />}
      {theme === "system" && <Monitor size={17} strokeWidth={1.7} />}
    </button>
  );
}
