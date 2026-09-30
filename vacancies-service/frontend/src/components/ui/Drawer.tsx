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

/**
 * Боковая панель справа (520px, ниже 768px — на всю ширину). Подложка (opacity)
 * и панель (x, 220 мс) — непосредственные motion-дети AnimatePresence, поэтому
 * закрытие тоже анимируется. Содержимое на время exit держит вызывающий код.
 */
export function Drawer({ open, onClose, title, children, footer }: DrawerProps) {
  const reduced = useReducedMotionSafe();
  const panelRef = useRef<HTMLElement>(null);
  const titleId = useId();
  useDialogA11y(panelRef, onClose, open);

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          key="drawer-overlay"
          {...overlayMotion(reduced)}
          className="fixed inset-0 z-50 bg-overlay"
          onClick={onClose}
          aria-hidden
        />
      )}
      {open && (
        <motion.aside
          key="drawer-panel"
          {...drawerMotion(reduced)}
          ref={panelRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          tabIndex={-1}
          className="fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l border-line bg-canvas shadow-drawer md:max-w-[520px]"
        >
          <div className="flex items-center justify-between border-b border-line px-6 py-4">
            <span id={titleId} className="text-[13px] font-medium text-ink-muted">
              {title}
            </span>
            <IconButton label="Закрыть" onClick={onClose} className="-mr-2">
              <X size={18} aria-hidden />
            </IconButton>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
          {footer && <div className="flex flex-wrap gap-2 border-t border-line px-6 py-4">{footer}</div>}
        </motion.aside>
      )}
    </AnimatePresence>,
    document.body,
  );
}
