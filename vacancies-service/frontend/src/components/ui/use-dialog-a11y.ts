import { useEffect, useRef } from "react";
import type { RefObject } from "react";

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type='hidden'])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

// Открытые диалоги по порядку открытия: Esc и Tab обрабатывает только верхний
// (подтверждение поверх drawer не должно закрывать оба).
const stack: symbol[] = [];
let lockedOverflow: string | null = null;

function focusables(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (element) => !element.hasAttribute("inert") && element.getClientRects().length > 0,
  );
}

/**
 * Доступность модального слоя: фокус на первый элемент и возврат фокуса,
 * цикл Tab внутри, закрытие по Esc, блокировка прокрутки body.
 * Хук вызывается в компоненте, который смонтирован, пока диалог открыт.
 */
export function useDialogA11y(
  containerRef: RefObject<HTMLElement | null>,
  onClose: () => void,
): void {
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const id = Symbol("dialog");
    stack.push(id);
    const previouslyFocused = document.activeElement as HTMLElement | null;

    if (stack.length === 1) {
      lockedOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
    }

    const container = containerRef.current;
    if (container) {
      const [first] = focusables(container);
      (first ?? container).focus({ preventScroll: true });
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (stack[stack.length - 1] !== id || !containerRef.current) {
        return;
      }
      if (event.key === "Escape") {
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      const items = focusables(containerRef.current);
      if (items.length === 0) {
        event.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || !containerRef.current.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || !containerRef.current.contains(active))) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      const index = stack.indexOf(id);
      if (index !== -1) {
        stack.splice(index, 1);
      }
      if (stack.length === 0) {
        document.body.style.overflow = lockedOverflow ?? "";
        lockedOverflow = null;
      }
      if (previouslyFocused && document.contains(previouslyFocused)) {
        previouslyFocused.focus({ preventScroll: true });
      }
    };
  }, [containerRef]);
}
