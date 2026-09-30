import { Copy, FileText, MoreHorizontal, Pencil, Star, Trash2 } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router";

import type { ResumeListItem } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { buttonClasses } from "@/components/ui/Button";
import { IconButton } from "@/components/ui/IconButton";
import {
  SCORE_TONE_SOFT,
  SCORE_TONE_TEXT,
  scoreTone,
  scoreToneLabel,
} from "@/features/resumes/score-tone";
import { cn } from "@/lib/cn";
import { formatRelativeDate, formatScore10 } from "@/lib/format";
import { RESUME_ORIGIN_LABELS } from "@/lib/labels";

interface ResumeCardProps {
  resume: ResumeListItem;
  now: Date;
  busy?: boolean;
  onDuplicate: () => void;
  onMakePrimary: () => void;
  onDelete: () => void;
}

/** Карточка списка резюме (ResumeCard макета через токены). */
export function ResumeCard({
  resume,
  now,
  busy = false,
  onDuplicate,
  onMakePrimary,
  onDelete,
}: ResumeCardProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const tone = scoreTone(resume.score);
  const href = `/resumes/${resume.id}`;

  useEffect(() => {
    if (!menuOpen) {
      return;
    }
    const onPointer = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  return (
    <article className="lift relative rounded-card border border-line bg-surface p-5 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent-soft text-accent">
          <FileText size={19} strokeWidth={1.7} aria-hidden />
        </div>
        <div ref={menuRef} className="relative z-10">
          <IconButton
            label={`Действия для «${resume.title}»`}
            aria-expanded={menuOpen}
            aria-controls={menuId}
            disabled={busy}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <MoreHorizontal size={18} aria-hidden />
          </IconButton>
          {menuOpen && (
            <div
              id={menuId}
              role="menu"
              className="absolute top-10 right-0 z-10 w-48 rounded-lg border border-line bg-surface p-1 shadow-pop"
            >
              <Link
                role="menuitem"
                to={href}
                className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-[13px] text-ink-body hover:bg-surface-muted"
                onClick={() => setMenuOpen(false)}
              >
                <Pencil size={14} aria-hidden /> Редактировать
              </Link>
              <button
                type="button"
                role="menuitem"
                className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-[13px] text-ink-body hover:bg-surface-muted"
                onClick={() => {
                  setMenuOpen(false);
                  onDuplicate();
                }}
              >
                <Copy size={14} aria-hidden /> Дублировать
              </button>
              {!resume.is_primary && (
                <button
                  type="button"
                  role="menuitem"
                  className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-[13px] text-ink-body hover:bg-surface-muted"
                  onClick={() => {
                    setMenuOpen(false);
                    onMakePrimary();
                  }}
                >
                  <Star size={14} aria-hidden /> Сделать основным
                </button>
              )}
              <button
                type="button"
                role="menuitem"
                className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-[13px] text-danger hover:bg-danger-soft"
                onClick={() => {
                  setMenuOpen(false);
                  onDelete();
                }}
              >
                <Trash2 size={14} aria-hidden /> Удалить
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="mt-5 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="text-[17px] font-semibold tracking-[-0.025em] text-ink">
            <Link
              to={href}
              className="rounded-sm after:absolute after:inset-0 after:rounded-card after:content-['']"
            >
              {resume.title}
            </Link>
          </h2>
          <p className="mt-1 text-[13px] text-ink-muted">
            {resume.target_position ?? "Целевая позиция не указана"}
          </p>
        </div>
        <div className="relative z-10 flex shrink-0 flex-col items-end gap-1">
          <span
            className={cn(
              "rounded-md px-2 py-1 text-[16px] font-semibold tabular-nums",
              SCORE_TONE_SOFT[tone],
            )}
          >
            {resume.score == null ? "—" : formatScore10(resume.score)}
          </span>
          <span className={cn("text-[13px]", SCORE_TONE_TEXT[tone])}>{scoreToneLabel(tone)}</span>
        </div>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-line pt-4">
        {resume.is_primary && (
          <Badge tone="accent" icon={<Star size={11} fill="currentColor" aria-hidden />}>
            основное
          </Badge>
        )}
        {resume.origin !== "manual" && (
          <Badge tone="muted">{RESUME_ORIGIN_LABELS[resume.origin]}</Badge>
        )}
        <span className="text-[13px] text-ink-muted">
          обновлено {formatRelativeDate(resume.updated_at, now)}
        </span>
        <Link
          to={href}
          className={cn(buttonClasses("primary", "sm"), "relative z-10 ml-auto")}
        >
          Редактировать <Pencil size={13} aria-hidden />
        </Link>
      </div>
    </article>
  );
}
