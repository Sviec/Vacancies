import { useQueryClient } from "@tanstack/react-query";
import {
  Bookmark,
  BookmarkCheck,
  CircleDollarSign,
  ExternalLink,
  EyeOff,
  GraduationCap,
  Languages,
  MapPin,
  RotateCcw,
} from "lucide-react";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import { ApiError } from "@/api/client";
import type { MatchCriterionBreakdown, MatchDetails, VacancyPostingBrief } from "@/api/types";
import {
  applyUserState,
  findCachedCard,
  setVacancyAction,
  useVacancy,
} from "@/api/vacancies";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { Drawer } from "@/components/ui/Drawer";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { MatchMeter } from "@/features/vacancies/MatchMeter";
import { sourceIcon } from "@/features/vacancies/source-meta";
import type { SourceTypes } from "@/features/vacancies/source-meta";
import type { VacancyActions } from "@/features/vacancies/use-vacancy-actions";
import { experienceLabel, originalUrl, relocationLabel } from "@/features/vacancies/vacancy-view";
import {
  formatLocation,
  formatPercent,
  formatRelativeDate,
  formatSalary,
} from "@/lib/format";
import {
  EMPLOYMENT_TYPE_LABELS,
  EXPERIENCE_LEVEL_LABELS,
  SOURCE_TYPE_LABELS,
} from "@/lib/labels";
import {
  MATCH_CRITERION_TITLES,
  describeCriterion,
  formatPoints,
} from "@/lib/match-reasons";
import type { MatchCriterionKey } from "@/lib/match-reasons";

/** Id, для которых в этой вкладке уже отправили `viewed`. */
const viewedThisSession = new Set<string>();

const CRITERION_KEYS = ["level", "salary", "location", "freshness"] as const satisfies readonly Exclude<
  MatchCriterionKey,
  "skills"
>[];

interface VacancyDrawerProps {
  vacancyId: string | null;
  resumeId: string | null;
  now: Date;
  sourceTypes: SourceTypes;
  actions: VacancyActions;
  onClose: () => void;
}

/**
 * Деталь вакансии в drawer. Открыт, пока в URL есть `?vacancy=`.
 * TODO: viewed отправляется при открытии drawer, один раз на id за сессию.
 */
export function VacancyDrawer({
  vacancyId,
  resumeId,
  now,
  sourceTypes,
  actions,
  onClose,
}: VacancyDrawerProps) {
  const open = vacancyId !== null;
  const [displayId, setDisplayId] = useState(vacancyId);
  if (vacancyId !== null && vacancyId !== displayId) {
    setDisplayId(vacancyId);
  }

  const id = displayId;
  const queryClient = useQueryClient();
  const cached = id !== null ? findCachedCard(queryClient, id) : null;
  const query = useVacancy(id, resumeId, cached);
  const detail = query.data;

  useEffect(() => {
    if (id === null || viewedThisSession.has(id)) {
      return;
    }
    viewedThisSession.add(id);
    void setVacancyAction(id, "viewed", true)
      .then((state) => applyUserState(queryClient, state))
      .catch(() => {
        /* ошибка viewed не мешает просмотру */
      });
  }, [id, queryClient]);

  let body: ReactNode = null;
  let footer: ReactNode = undefined;

  if (id !== null) {
    if (query.isPending && !detail) {
      body = <DrawerSkeleton />;
    } else if (query.isError && !detail) {
      body =
        query.error instanceof ApiError && query.error.status === 404 ? (
          <div className="px-6 py-10">
            <ErrorState compact title="Вакансия не найдена" error={query.error} />
          </div>
        ) : (
          <div className="px-6 py-10">
            <ErrorState
              compact
              error={query.error}
              onRetry={() => void query.refetch()}
              retrying={query.isFetching}
            />
          </div>
        );
    } else if (!detail) {
      body = <DrawerSkeleton />;
    } else {
      const userActions = detail.user_actions ?? [];
      const saved = userActions.includes("saved");
      const hidden = userActions.includes("hidden");
      const busy = actions.pendingId === id;
      const origin = originalUrl(detail.url, detail.postings);
      const salaryText = formatSalary({
        min: detail.salary_min,
        max: detail.salary_max,
        currency: detail.salary_currency,
        period: detail.salary_period,
      });
      const salaryLabel =
        detail.salary_is_gross === true ? `${salaryText} · до вычета` : salaryText;

      body = (
        <div className="space-y-8 px-6 py-6">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h2 className="text-[20px] font-semibold tracking-[-0.03em] text-ink">{detail.title}</h2>
              <p className="mt-1 text-[14px] text-ink-body">
                {detail.company ?? "Компания не указана"}
              </p>
            </div>
            {detail.match_score != null && <MatchMeter score={detail.match_score} size="lg" />}
          </div>

          <MetaGrid
            items={[
              {
                icon: <MapPin size={14} aria-hidden />,
                label: "Локация",
                value: formatLocation(detail.city, detail.country, detail.work_format),
              },
              {
                label: "Занятость",
                value: EMPLOYMENT_TYPE_LABELS[detail.employment_type],
              },
              {
                label: "Уровень",
                value: EXPERIENCE_LEVEL_LABELS[detail.experience_level],
              },
              {
                label: "Стаж",
                value: experienceLabel(detail.experience_min_years),
              },
              {
                icon: <CircleDollarSign size={14} aria-hidden />,
                label: "Зарплата",
                value: salaryLabel,
              },
              {
                label: "Опубликована",
                value: formatRelativeDate(detail.published_at, now),
              },
              {
                label: "Релокация",
                value: relocationLabel(detail.relocation_support),
              },
              {
                icon: <Languages size={14} aria-hidden />,
                label: "Языки",
                value: detail.languages.length ? detail.languages.join(", ") : "Не указаны",
              },
              {
                icon: <GraduationCap size={14} aria-hidden />,
                label: "Образование",
                value: detail.education_required ?? "Не указано",
              },
            ]}
          />

          <MatchBreakdown
            score={detail.match_score}
            details={detail.match_details}
            hasResume={resumeId !== null}
          />

          <section>
            <h3 className="mb-3 text-[13px] font-semibold text-ink">Описание</h3>
            {query.isFetching && !detail.description_clean ? (
              <div className="space-y-2" aria-busy="true" aria-label="Загружаем описание">
                <Skeleton className="h-3.5 w-full" />
                <Skeleton className="h-3.5 w-11/12" />
                <Skeleton className="h-3.5 w-4/5" />
              </div>
            ) : (
              <p className="whitespace-pre-line text-[15px] leading-[1.5] text-ink-body">
                {detail.description_clean.trim() || "Описание не указано"}
              </p>
            )}
          </section>

          <PostingsList postings={detail.postings ?? []} now={now} sourceTypes={sourceTypes} />
        </div>
      );

      footer = (
        <>
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => actions.toggleSaved(id, userActions)}
          >
            {saved ? (
              <>
                <BookmarkCheck size={15} aria-hidden /> Убрать из сохранённых
              </>
            ) : (
              <>
                <Bookmark size={15} aria-hidden /> Сохранить
              </>
            )}
          </Button>
          {hidden ? (
            <Button variant="secondary" disabled={busy} onClick={() => actions.unhide(id)}>
              <RotateCcw size={15} aria-hidden /> Вернуть в ленту
            </Button>
          ) : (
            <Button variant="ghost" disabled={busy} onClick={() => actions.hide(id, onClose)}>
              <EyeOff size={15} aria-hidden /> Скрыть
            </Button>
          )}
          {origin && (
            <a
              href={origin}
              target="_blank"
              rel="noopener noreferrer"
              className="ml-auto inline-flex h-9 items-center gap-2 rounded-lg bg-accent px-3.5 text-[13px] font-medium text-on-accent hover:bg-accent-hover"
            >
              <ExternalLink size={15} aria-hidden /> Открыть оригинал
            </a>
          )}
        </>
      );
    }
  }

  return (
    <Drawer open={open} onClose={onClose} title="Вакансия" footer={footer}>
      {body}
    </Drawer>
  );
}

function MetaGrid({
  items,
}: {
  items: { icon?: ReactNode; label: string; value: string }[];
}) {
  return (
    <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {items.map((item) => (
        <div key={item.label} className="rounded-lg bg-surface-inset px-3 py-2.5">
          <dt className="text-[11px] font-medium tracking-[0.06em] text-ink-muted uppercase">
            {item.label}
          </dt>
          <dd className="mt-1 flex items-start gap-1.5 text-[13px] text-ink">
            {item.icon}
            <span>{item.value}</span>
          </dd>
        </div>
      ))}
    </dl>
  );
}

function MatchBreakdown({
  score,
  details,
  hasResume,
}: {
  score: number | null | undefined;
  details: MatchDetails | null | undefined;
  hasResume: boolean;
}) {
  if (!hasResume) {
    return (
      <section className="rounded-card border border-dashed border-line-strong bg-surface px-4 py-4">
        <h3 className="text-[13px] font-semibold text-ink">Почему рекомендовано</h3>
        <p className="mt-2 text-[13px] leading-[1.5] text-ink-muted">
          Выберите резюме вверху страницы, чтобы увидеть процент соответствия и разбивку.
        </p>
      </section>
    );
  }
  if (score == null || !details) {
    return null;
  }

  return (
    <section>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h3 className="text-[13px] font-semibold text-ink">Почему рекомендовано</h3>
        <span className="text-[13px] font-medium text-ink tabular-nums">{formatPercent(score)}</span>
      </div>

      {(details.skills.matched.length > 0 || details.skills.missing.length > 0) && (
        <div className="mb-4">
          <p className="mb-2 text-[12px] text-ink-muted">{describeCriterion("skills", details.skills)}</p>
          <ul className="flex flex-wrap gap-1.5">
            {details.skills.matched.map((skill) => (
              <li key={`m-${skill}`}>
                <Chip tone="positive">{skill}</Chip>
              </li>
            ))}
            {details.skills.missing.map((skill) => (
              <li key={`x-${skill}`}>
                <Chip tone="muted">{skill}</Chip>
              </li>
            ))}
          </ul>
        </div>
      )}

      <ul className="space-y-3">
        {CRITERION_KEYS.map((key) => (
          <CriterionBar key={key} criterionKey={key} breakdown={details[key]} />
        ))}
      </ul>
    </section>
  );
}

function CriterionBar({
  criterionKey,
  breakdown,
}: {
  criterionKey: Exclude<MatchCriterionKey, "skills">;
  breakdown: MatchCriterionBreakdown;
}) {
  const max = breakdown.max_points ?? 0;
  const ratio = max > 0 ? Math.min(Math.max(breakdown.points / max, 0), 1) : 0;
  return (
    <li>
      <div className="mb-1 flex items-baseline justify-between gap-3">
        <span className="text-[12px] font-medium text-ink">{MATCH_CRITERION_TITLES[criterionKey]}</span>
        <span className="text-[11px] text-ink-muted tabular-nums">
          {formatPoints(breakdown.points, max)}
        </span>
      </div>
      <div className="h-1 overflow-hidden rounded-full bg-surface-inset" aria-hidden>
        <div className="h-full rounded-full bg-accent" style={{ width: `${ratio * 100}%` }} />
      </div>
      <p className="mt-1.5 text-[12px] leading-[1.5] text-ink-muted">
        {describeCriterion(criterionKey, breakdown)}
      </p>
    </li>
  );
}

function PostingsList({
  postings,
  now,
  sourceTypes,
}: {
  postings: VacancyPostingBrief[];
  now: Date;
  sourceTypes: SourceTypes;
}) {
  if (postings.length === 0) {
    return null;
  }
  return (
    <section>
      <h3 className="mb-3 text-[13px] font-semibold text-ink">Источники</h3>
      <ul className="space-y-2">
        {postings.map((posting) => {
          const Icon = sourceIcon(posting.source_type ?? sourceTypes[posting.source]);
          return (
            <li
              key={posting.id}
              className="flex flex-wrap items-center gap-2 rounded-lg border border-line px-3 py-2.5"
            >
              <Icon size={14} aria-hidden className="text-ink-muted" />
              <span className="text-[13px] font-medium text-ink">{posting.source}</span>
              <span className="text-[12px] text-ink-muted">
                {SOURCE_TYPE_LABELS[posting.source_type]}
              </span>
              <span className="text-[12px] text-ink-muted">
                {formatRelativeDate(posting.published_at, now)}
              </span>
              {posting.parse_quality === "partial" && <Badge tone="warn">неполные данные</Badge>}
              {posting.url && (
                <a
                  href={posting.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="ml-auto inline-flex items-center gap-1 text-[12px] font-medium text-accent hover:text-accent-hover"
                >
                  Открыть <ExternalLink size={12} aria-hidden />
                </a>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function DrawerSkeleton() {
  return (
    <div className="space-y-6 px-6 py-6" aria-busy="true" aria-label="Загружаем вакансию">
      <div>
        <Skeleton className="h-6 w-3/5" />
        <Skeleton className="mt-2 h-4 w-40" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        {Array.from({ length: 6 }, (_, index) => (
          <Skeleton key={index} className="h-14 w-full" rounded="lg" />
        ))}
      </div>
      <div className="space-y-2">
        <Skeleton className="h-3.5 w-full" />
        <Skeleton className="h-3.5 w-11/12" />
        <Skeleton className="h-3.5 w-4/5" />
      </div>
    </div>
  );
}
