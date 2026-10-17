import { Copy, MoreHorizontal, Pencil, Star, Trash2 } from "lucide-react";
import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router";

import type { ResumeListItem, ResumeRead } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Chip } from "@/components/ui/Chip";
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
  detail?: ResumeRead;
  photo: string | null;
  now: Date;
  busy?: boolean;
  onDuplicate: () => void;
  onMakePrimary: () => void;
  onDelete: () => void;
}

/** Превью резюме в вертикальном списке. Меню действий — портал, чтобы не просвечивало сквозь карточку. */
export function ResumeCard({
  resume,
  detail,
  photo,
  now,
  busy = false,
  onDuplicate,
  onMakePrimary,
  onDelete,
}: ResumeCardProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuBox, setMenuBox] = useState<{ top: number; right: number } | null>(null);
  const buttonRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const tone = scoreTone(resume.score);
  const href = `/resumes/${resume.id}`;
  const summary = detail?.summary?.trim();
  const experience = detail?.experience ?? [];
  const job = experience.find((item) => item.is_current) ?? experience[0];
  const allSkills = detail?.skills ?? [];
  const skills = allSkills.slice(0, 5);
  const extraSkills = Math.max(0, allSkills.length - skills.length);

  useLayoutEffect(() => {
    if (!menuOpen) {
      return;
    }
    const place = () => {
      const rect = buttonRef.current?.getBoundingClientRect();
      if (!rect) {
        return;
      }
      setMenuBox({ top: rect.bottom + 4, right: Math.max(8, window.innerWidth - rect.right) });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [menuOpen]);

  useEffect(() => {
    if (!menuOpen) {
      return;
    }
    const onPointer = (event: MouseEvent) => {
      const target = event.target as Node;
      if (buttonRef.current?.contains(target) || panelRef.current?.contains(target)) {
        return;
      }
      setMenuOpen(false);
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

  const itemClass =
    "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-[13px] text-ink-body hover:bg-surface-muted";

  return (
    <article className="lift flex gap-4 rounded-card border border-line bg-surface p-5 shadow-card">
      <span className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-full bg-accent-soft text-accent">
        {photo ? (
          <img src={photo} alt="" className="h-full w-full object-cover" />
        ) : (
          <span className="text-[15px] font-semibold">{resume.title.slice(0, 1).toUpperCase()}</span>
        )}
      </span>

      <div className="min-w-0 flex-1">
        <h2 className="text-[17px] font-semibold tracking-[-0.025em] text-ink">
          <Link to={href} className="rounded-sm">
            {resume.title}
          </Link>
        </h2>
        <p className="mt-1 text-[13px] text-ink-muted">
          {resume.target_position ?? "Целевая позиция не указана"}
        </p>
        {summary && (
          <p className="mt-3 line-clamp-2 text-[14px] leading-[1.5] text-ink-body">{summary}</p>
        )}
        {job && (
          <p className="mt-2 text-[13px] text-ink-body">
            {job.position}
            <span className="text-ink-muted"> · {job.company}</span>
            {job.is_current && <span className="text-ink-muted"> · сейчас</span>}
          </p>
        )}
        {skills.length > 0 && (
          <ul className="mt-3 flex flex-wrap gap-2">
            {skills.map((item) => (
              <li key={item.skill}>
                <Chip>{item.skill}</Chip>
              </li>
            ))}
            {extraSkills > 0 && (
              <li>
                <Chip tone="muted">+{extraSkills}</Chip>
              </li>
            )}
          </ul>
        )}
        <div className="mt-4 flex flex-wrap items-center gap-2">
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
        </div>
      </div>

      <div className="flex shrink-0 flex-col items-end gap-2">
        <div ref={buttonRef}>
          <IconButton
            label={`Действия для «${resume.title}»`}
            aria-expanded={menuOpen}
            aria-controls={menuId}
            disabled={busy}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <MoreHorizontal size={18} aria-hidden />
          </IconButton>
        </div>
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

      {menuOpen &&
        menuBox &&
        createPortal(
          <div
            ref={panelRef}
            id={menuId}
            role="menu"
            style={{ top: menuBox.top, right: menuBox.right }}
            className="fixed z-50 w-48 rounded-lg border border-line bg-surface p-1 shadow-pop"
          >
            <Link role="menuitem" to={href} className={itemClass} onClick={() => setMenuOpen(false)}>
              <Pencil size={14} aria-hidden /> Редактировать
            </Link>
            <button
              type="button"
              role="menuitem"
              className={itemClass}
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
                className={itemClass}
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
          </div>,
          document.body,
        )}
    </article>
  );
}
