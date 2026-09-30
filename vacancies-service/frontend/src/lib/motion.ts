/**
 * Пресеты Framer Motion в лимитах раздела 8 ТЗ: 150–250 мс, easeOut, не более
 * двух анимируемых свойств, stagger 30 мс только на первых 8 элементах.
 * При `reduced` анимации отключаются полностью: `initial: false` и нулевая
 * длительность (MotionConfig reducedMotion="user" гасит только transform).
 */

import { useReducedMotion } from "framer-motion";

export const DURATION = 0.22;
export const EASE = "easeOut" as const;
export const STAGGER_STEP = 0.03;
export const STAGGER_LIMIT = 8;

const OVERLAY_DURATION = 0.18;
const MODAL_DURATION = 0.2;

type MotionTarget = { opacity?: number; x?: number | string; y?: number };

export interface MotionPreset {
  initial: false | MotionTarget;
  animate: MotionTarget;
  exit?: MotionTarget;
  transition: { duration: number; ease: typeof EASE; delay?: number };
}

/** Появление элемента списка: opacity + translateY(8px), stagger по индексу. */
export function rise(index: number, reduced: boolean): MotionPreset {
  return {
    initial: reduced ? false : { opacity: 0, y: 8 },
    animate: { opacity: 1, y: 0 },
    transition: {
      duration: reduced ? 0 : DURATION,
      ease: EASE,
      delay: reduced ? 0 : Math.min(Math.max(index, 0), STAGGER_LIMIT - 1) * STAGGER_STEP,
    },
  };
}

/** Drawer: выезд справа, одно свойство `x`. */
export function drawerMotion(reduced: boolean): MotionPreset {
  return {
    initial: reduced ? false : { x: "100%" },
    animate: { x: 0 },
    exit: reduced ? undefined : { x: "100%" },
    transition: { duration: reduced ? 0 : DURATION, ease: EASE },
  };
}

/** Подложка drawer и модалок: только opacity. */
export function overlayMotion(reduced: boolean): MotionPreset {
  return {
    initial: reduced ? false : { opacity: 0 },
    animate: { opacity: 1 },
    exit: reduced ? undefined : { opacity: 0 },
    transition: { duration: reduced ? 0 : OVERLAY_DURATION, ease: EASE },
  };
}

/** Модальное окно: opacity + translateY(8px). */
export function modalMotion(reduced: boolean): MotionPreset {
  return {
    initial: reduced ? false : { opacity: 0, y: 8 },
    animate: { opacity: 1, y: 0 },
    exit: reduced ? undefined : { opacity: 0, y: 8 },
    transition: { duration: reduced ? 0 : MODAL_DURATION, ease: EASE },
  };
}

/** `prefers-reduced-motion`; до первого замера — `false`. */
export function useReducedMotionSafe(): boolean {
  return useReducedMotion() ?? false;
}
