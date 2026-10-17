import type { ReactNode } from "react";
import { Link } from "react-router";

import { cn } from "@/lib/cn";

interface SectionProps {
  id: string;
  number: string;
  title: string;
  hint?: string;
  /** Секция берётся из профиля и в редакторе резюме не правится. */
  locked?: boolean;
  children: ReactNode;
  className?: string;
}

/** Секция формы редактора (Section макета через токены). */
export function Section({ id, number, title, hint, locked = false, children, className }: SectionProps) {
  return (
    <section
      id={id}
      className={cn("scroll-mt-24 rounded-card border border-line bg-surface p-5 md:p-6", className)}
    >
      <div className="mb-5 flex items-start gap-3">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-[13px] font-semibold text-accent">
          {number}
        </span>
        <div>
          <h2 className="text-[15px] font-semibold text-ink">{title}</h2>
          {hint && <p className="mt-1 text-[13px] leading-5 text-ink-muted">{hint}</p>}
        </div>
      </div>
      {locked && (
        <p className="mb-4 text-[13px] leading-5 text-ink-muted">
          Общие данные профиля.{" "}
          <Link to="/resumes" className="font-medium text-accent hover:text-accent-hover">
            Изменить в профиле
          </Link>
        </p>
      )}
      <fieldset disabled={locked} className="m-0 min-w-0 border-0 p-0">
        {children}
      </fieldset>
    </section>
  );
}
