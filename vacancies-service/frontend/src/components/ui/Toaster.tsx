import { AnimatePresence, motion } from "framer-motion";
import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";
import { useReducedMotionSafe } from "@/lib/motion";

// TODO: свой минимальный тостер вместо библиотеки: только opacity 150 мс,
// автоскрытие через 4 с, одна необязательная кнопка действия.
const HIDE_AFTER_MS = 4000;

export interface ToastInput {
  message: string;
  tone?: "neutral" | "danger";
  action?: { label: string; onClick: () => void };
}

interface Toast extends ToastInput {
  id: number;
}

const ToastContext = createContext<((toast: ToastInput) => void) | null>(null);

export function ToasterProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);
  const reduced = useReducedMotionSafe();

  const dismiss = useCallback((id: number) => {
    setToasts((items) => items.filter((item) => item.id !== id));
  }, []);

  const show = useCallback(
    (toast: ToastInput) => {
      const id = nextId.current++;
      setToasts((items) => [...items.slice(-2), { ...toast, id }]);
      window.setTimeout(() => dismiss(id), HIDE_AFTER_MS);
    },
    [dismiss],
  );

  const value = useMemo(() => show, [show]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed right-4 bottom-4 z-[60] flex w-[min(360px,calc(100vw-2rem))] flex-col gap-2">
        <AnimatePresence initial={false}>
          {toasts.map((toast) => (
            <motion.div
              key={toast.id}
              initial={reduced ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={reduced ? undefined : { opacity: 0 }}
              transition={{ duration: reduced ? 0 : 0.15, ease: "easeOut" }}
              className={cn(
                "pointer-events-auto flex items-center justify-between gap-3 rounded-lg border border-line bg-surface px-4 py-3 text-[13px] shadow-pop",
                toast.tone === "danger" ? "text-danger" : "text-ink",
              )}
            >
              <span>{toast.message}</span>
              {toast.action && (
                <button
                  type="button"
                  className="shrink-0 font-medium text-accent hover:text-accent-hover"
                  onClick={() => {
                    toast.action?.onClick();
                    dismiss(toast.id);
                  }}
                >
                  {toast.action.label}
                </button>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): (toast: ToastInput) => void {
  const show = useContext(ToastContext);
  if (show === null) {
    throw new Error("useToast должен вызываться внутри ToasterProvider");
  }
  return show;
}
