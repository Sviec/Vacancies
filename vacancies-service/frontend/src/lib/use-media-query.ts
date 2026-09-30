import { useSyncExternalStore } from "react";

/** Совпадение media-query с подпиской на изменения. */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const media = window.matchMedia(query);
      media.addEventListener("change", onChange);
      return () => media.removeEventListener("change", onChange);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}

/** Ширина меньше 768px: фильтры уходят в модальное окно (раздел 8 ТЗ). */
export function useIsBelowMd(): boolean {
  return useMediaQuery("(max-width: 767.98px)");
}
