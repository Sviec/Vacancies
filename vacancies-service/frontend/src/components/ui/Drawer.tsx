import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { useId, useRef } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";

import { IconButton } from "@/components/ui/IconButton";
import { useDialogA11y } from "@/components/ui/use-dialog-a11y";
import { drawerMotion, overlayMotion, useReducedMotionSafe } from "@/lib/motion";

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  /** Подпись для `aria-labelledby`; видимая строка в шапке drawer. */
  title: string;
  children?: ReactNode;
  footer?: ReactNode;
}

function DrawerLayer({ onClose, title, children, footer }: Omit<DrawerProps, "open">) {
  const reduced = useReducedMotionSafe();
  const panelRef = useRef<HTMLElement>(null);
  const titleId = useId();
  useDialogA11y(panelRef, onClose);

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <motion.div {...overlayMotion(reduced)} className="absolute inset-0 bg-overlay" onClick={onClose} aria-hidden />
      <motion.aside
        {...drawerMotion(reduced)}
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="relative flex h-full w-full flex-col border-l border-line bg-canvas shadow-drawer md:max-w-[520px]"
      >
        <div className="flex items-center justify-between border-b border-line px-6 py-4">
          <span id={titleId} className="text-[12px] font-medium text-ink-muted">
            {title}
          </span>
          <IconButton label="Закрыть" onClick={onClose} className="-mr-2">
            <X size={18} aria-hidden />
          </IconButton>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
        {footer && <div className="flex flex-wrap gap-2 border-t border-line px-6 py-4">{footer}</div>}
      </motion.aside>
    </div>
  );
}

/** Боковая панель справа (520px, ниже 768px — на всю ширину). */
export function Drawer({ open, ...props }: DrawerProps) {
  return createPortal(
    <AnimatePresence>{open && <DrawerLayer key="drawer" {...props} />}</AnimatePresence>,
    document.body,
  );
}
