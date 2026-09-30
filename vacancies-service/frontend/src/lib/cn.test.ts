import { describe, expect, it } from "vitest";

import { cn } from "@/lib/cn";

describe("cn и токены темы", () => {
  it("цвета текста из токенов перекрывают друг друга, размер шрифта — нет", () => {
    expect(cn("text-ink", "text-ink-muted")).toBe("text-ink-muted");
    expect(cn("text-[13px] text-ink", "text-ink-body")).toBe("text-[13px] text-ink-body");
    expect(cn("bg-surface", "bg-surface-inset")).toBe("bg-surface-inset");
  });

  it("тени и радиус темы", () => {
    expect(cn("shadow-card", "shadow-pop")).toBe("shadow-pop");
    expect(cn("rounded-lg", "rounded-card")).toBe("rounded-card");
  });

  it("условные классы", () => {
    const active = false;
    expect(cn("px-2", active && "font-medium", undefined, "px-3")).toBe("px-3");
  });
});
