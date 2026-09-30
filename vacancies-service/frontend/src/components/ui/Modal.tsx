import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { useId, useRef } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";

import { IconButton } from "@/components/ui/IconButton";
import { useDialogA11y } from "@/components/ui/use-dialog-a11y";
import { cn } from "@/lib/cn";
import { modalMotion, overlayMotion, useReducedMotionSafe } from "@/lib/motion";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  className?: string;
}

/**
 * Модальное окно: портал, Esc и клик по подложке закрывают, фокус заперт внутри.
 * Подложка и панель — непосредственные motion-дети AnimatePresence: только так
 * exit-анимация успевает проиграть до размонтирования.
 */
export function Modal({ open, onClose, title, description, children, footer, className }: ModalProps) {
  const reduced = useReducedMotionSafe();
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  useDialogA11y(panelRef, onClose, open);

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          key="modal-overlay"
          {...overlayMotion(reduced)}
          className="fixed inset-0 z-50 bg-overlay"
          onClick={onClose}
          aria-hidden
        />
      )}
      {open && (
        <motion.div
          key="modal-panel"
          {...modalMotion(reduced)}
          className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center p-4"
        >
          <div
            ref={panelRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            aria-describedby={description ? descriptionId : undefined}
            tabIndex={-1}
            className={cn(
              "pointer-events-auto relative flex max-h-[calc(100dvh-2rem)] w-full max-w-[520px] flex-col rounded-2xl border border-line bg-canvas shadow-modal",
              className,
            )}
          >
            <div className="flex items-start justify-between gap-4 px-6 pt-5">
              <div>
                <h2 id={titleId} className="text-[17px] font-semibold text-ink">
                  {title}
                </h2>
                {description && (
                  <p id={descriptionId} className="mt-1 text-[13px] leading-[1.5] text-ink-muted">
                    {description}
                  </p>
                )}
              </div>
              <IconButton label="Закрыть" onClick={onClose} className="-mt-1 -mr-2">
                <X size={18} aria-hidden />
              </IconButton>
            </div>
            {children && <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">{children}</div>}
            {footer && (
              <div className="flex flex-wrap justify-end gap-2 border-t border-line px-6 py-4">{footer}</div>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
