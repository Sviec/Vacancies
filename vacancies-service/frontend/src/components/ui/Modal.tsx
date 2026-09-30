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

function ModalLayer({ onClose, title, description, children, footer, className }: Omit<ModalProps, "open">) {
  const reduced = useReducedMotionSafe();
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  useDialogA11y(panelRef, onClose);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <motion.div {...overlayMotion(reduced)} className="absolute inset-0 bg-overlay" onClick={onClose} aria-hidden />
      <motion.div
        {...modalMotion(reduced)}
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        className={cn(
          "relative flex max-h-[calc(100dvh-2rem)] w-full max-w-[520px] flex-col rounded-2xl border border-line bg-canvas shadow-modal",
          className,
        )}
      >
        <div className="flex items-start justify-between gap-4 px-6 pt-5">
          <div>
            <h2 id={titleId} className="text-[17px] font-semibold text-ink">
              {title}
            </h2>
            {description && (
              <p id={descriptionId} className="mt-1 text-[13px] leading-6 text-ink-muted">
                {description}
              </p>
            )}
          </div>
          <IconButton label="Закрыть" onClick={onClose} className="-mr-2 -mt-1">
            <X size={18} aria-hidden />
          </IconButton>
        </div>
        {children && <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">{children}</div>}
        {footer && (
          <div className="flex flex-wrap justify-end gap-2 border-t border-line px-6 py-4">{footer}</div>
        )}
      </motion.div>
    </div>
  );
}

/** Модальное окно: портал, Esc и клик по подложке закрывают, фокус заперт внутри. */
export function Modal({ open, ...props }: ModalProps) {
  return createPortal(
    <AnimatePresence>{open && <ModalLayer key="modal" {...props} />}</AnimatePresence>,
    document.body,
  );
}
