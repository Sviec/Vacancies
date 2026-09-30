import { Bookmark, BookmarkCheck, CircleDollarSign, MapPin } from "lucide-react";
import { Link } from "react-router";

import type { VacancyListItem } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Chip } from "@/components/ui/Chip";
import { IconButton } from "@/components/ui/IconButton";
import { MatchMeter } from "@/features/vacancies/MatchMeter";
import { sourceIcon } from "@/features/vacancies/source-meta";
import type { SourceTypes } from "@/features/vacancies/source-meta";
import type { VacancyActions } from "@/features/vacancies/use-vacancy-actions";
import { cardSkills, orderedSources } from "@/features/vacancies/vacancy-view";
import { formatLocation, formatRelativeDate, formatSalary } from "@/lib/format";

interface VacancyCardProps {
  vacancy: VacancyListItem;
  /** Ссылка на ту же ленту с `?vacancy=<id>` — открывает drawer. */
  href: string;
  now: Date;
  sourceTypes: SourceTypes;
  showHidden: boolean;
  actions: VacancyActions;
}

/**
 * Карточка ленты (VacancyCard макета через токены). Вся карточка кликабельна:
 * ссылка заголовка растянута псевдоэлементом, кнопки лежат над ней.
 */
export function VacancyCard({ vacancy, href, now, sourceTypes, showHidden, actions }: VacancyCardProps) {
  const userActions = vacancy.user_actions ?? [];
  const saved = userActions.includes("saved");
  const hidden = userActions.includes("hidden");
  const busy = actions.pendingId === vacancy.id;
  const { shown, rest } = cardSkills(vacancy.skills, vacancy.match_details?.skills.matched);
  const sources = orderedSources(vacancy.source, vacancy.sources);

  return (
    <article className="lift relative rounded-card border border-line bg-surface p-5 shadow-card">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2 text-[13px] text-ink-muted">
            {sources.map((slug) => {
              const Icon = sourceIcon(sourceTypes[slug]);
              return (
                <span key={slug} className="inline-flex items-center gap-1 font-medium">
                  <Icon size={12} strokeWidth={1.8} aria-hidden />
                  {slug}
                </span>
              );
            })}
            <span aria-hidden className="h-1 w-1 rounded-full bg-line-strong" />
            <span>{formatRelativeDate(vacancy.published_at, now)}</span>
          </div>
          <h3 className="text-[16px] font-semibold tracking-[-0.02em] text-ink">
            <Link
              to={href}
              preventScrollReset
              className="rounded-sm after:absolute after:inset-0 after:rounded-card after:content-['']"
            >
              {vacancy.title}
            </Link>
          </h3>
          <p className="mt-1 text-[13px] text-ink-body">{vacancy.company ?? "Компания не указана"}</p>
        </div>
        <div className="relative z-10 flex shrink-0 items-center gap-2">
          {vacancy.match_score != null && <MatchMeter score={vacancy.match_score} />}
          <IconButton
            label={saved ? "Убрать из сохранённых" : "Сохранить вакансию"}
            aria-pressed={saved}
            disabled={busy}
            onClick={(event) => {
              event.stopPropagation();
              actions.toggleSaved(vacancy.id, userActions);
            }}
          >
            {saved ? (
              <BookmarkCheck size={17} className="text-accent" aria-hidden />
            ) : (
              <Bookmark size={17} aria-hidden />
            )}
          </IconButton>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-[13px] text-ink-muted">
        <span className="inline-flex items-center gap-2">
          <MapPin size={13} aria-hidden />
          {formatLocation(vacancy.city, vacancy.country, vacancy.work_format)}
        </span>
        <span className="inline-flex items-center gap-2">
          <CircleDollarSign size={13} aria-hidden />
          {formatSalary({
            min: vacancy.salary_min,
            max: vacancy.salary_max,
            currency: vacancy.salary_currency,
            period: vacancy.salary_period,
          })}
        </span>
      </div>

      {shown.length > 0 && (
        <ul aria-label="Навыки" className="mt-4 flex flex-wrap gap-2">
          {shown.map((skill) => (
            <li key={skill.name}>
              <Chip tone={skill.matched ? "positive" : "neutral"}>{skill.name}</Chip>
            </li>
          ))}
          {rest > 0 && (
            <li>
              <Chip tone="muted">+{rest}</Chip>
            </li>
          )}
        </ul>
      )}

      {(vacancy.parse_quality === "partial" || saved || userActions.includes("applied") || (showHidden && hidden)) && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          {vacancy.parse_quality === "partial" && (
            <Badge tone="warn" title="Часть полей не удалось разобрать из источника">
              неполные данные
            </Badge>
          )}
          {saved && <Badge tone="accent">Сохранено</Badge>}
          {userActions.includes("applied") && <Badge tone="positive">Отклик</Badge>}
          {showHidden && hidden && (
            <>
              <Badge tone="muted">Скрыто</Badge>
              <button
                type="button"
                disabled={busy}
                onClick={() => actions.unhide(vacancy.id)}
                className="relative z-10 rounded-md px-2 py-1 text-[13px] font-medium text-accent hover:text-accent-hover disabled:opacity-60"
              >
                Вернуть
              </button>
            </>
          )}
        </div>
      )}
    </article>
  );
}
