import { describe, expect, it } from "vitest";

import {
  DURATION,
  drawerMotion,
  EASE,
  modalMotion,
  overlayMotion,
  rise,
  STAGGER_LIMIT,
  STAGGER_STEP,
} from "@/lib/motion";

describe("лимиты раздела 8 ТЗ", () => {
  it("длительность 150–250 мс, easeOut", () => {
    expect(DURATION).toBeGreaterThanOrEqual(0.15);
    expect(DURATION).toBeLessThanOrEqual(0.25);
    expect(EASE).toBe("easeOut");
    for (const preset of [rise(0, false), drawerMotion(false), overlayMotion(false), modalMotion(false)]) {
      expect(preset.transition.duration).toBeGreaterThanOrEqual(0.15);
      expect(preset.transition.duration).toBeLessThanOrEqual(0.25);
    }
  });

  it("stagger 30 мс только на первых 8 элементах", () => {
    expect(STAGGER_STEP).toBe(0.03);
    expect(STAGGER_LIMIT).toBe(8);
    expect(rise(0, false).transition.delay).toBe(0);
    expect(rise(1, false).transition.delay).toBeCloseTo(0.03);
    expect(rise(20, false).transition.delay).toBe(rise(7, false).transition.delay);
    expect(rise(8, false).transition.delay).toBe(rise(7, false).transition.delay);
  });

  it("не больше двух анимируемых свойств, drawer — одно", () => {
    for (const preset of [rise(3, false), drawerMotion(false), overlayMotion(false), modalMotion(false)]) {
      expect(Object.keys(preset.animate).length).toBeLessThanOrEqual(2);
    }
    expect(Object.keys(drawerMotion(false).animate)).toEqual(["x"]);
  });

  it("reduced motion выключает анимации полностью", () => {
    for (const preset of [rise(5, true), drawerMotion(true), overlayMotion(true), modalMotion(true)]) {
      expect(preset.initial).toBe(false);
      expect(preset.transition.duration).toBe(0);
      expect(preset.transition.delay ?? 0).toBe(0);
      expect(preset.exit).toBeUndefined();
    }
  });
});
