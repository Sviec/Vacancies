import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router";

import { useVacancyFeed } from "@/api/vacancies";
import { PageHeader } from "@/components/layout/AppShell";
import { FeedToolbar } from "@/features/vacancies/FeedToolbar";
import type { FilterChange } from "@/features/vacancies/FilterPanel";
import { FilterPanel } from "@/features/vacancies/FilterPanel";
import { FiltersModal } from "@/features/vacancies/FiltersModal";
import {
  clearFilters,
  feedKeyToApiParams,
  serializeFeedParams,
  toFeedKey,
  withFilters,
  withVacancy,
} from "@/features/vacancies/feed-state";
import { useSourceTypes } from "@/features/vacancies/source-meta";
import { useActiveResume } from "@/features/vacancies/use-active-resume";
import { useFeedParams } from "@/features/vacancies/use-feed-params";
import { useVacancyActions } from "@/features/vacancies/use-vacancy-actions";
import { VacancyDrawer } from "@/features/vacancies/VacancyDrawer";
import { VacancyFeed } from "@/features/vacancies/VacancyFeed";
import { pluralRu } from "@/lib/format";
import { readStorage, writeStorage } from "@/lib/storage";
import { useIsBelowMd } from "@/lib/use-media-query";

const FILTERS_COLLAPSED_KEY = "vacancies.filtersCollapsed";

/**
 * Экран «Вакансии»: лента, фильтры, drawer детали.
 * TODO: модалка фильтров — ниже 768px; от 768px — сворачиваемая колонка.
 * TODO: любая смена ключа ленты показывает skeleton, предыдущая выдача не сохраняется.
 */
export function VacanciesPage() {
  const [state, update] = useFeedParams();
  const resume = useActiveResume(state, update);
  const isBelowMd = useIsBelowMd();
  const sourceTypes = useSourceTypes();
  const actions = useVacancyActions();
  const [filtersModalOpen, setFiltersModalOpen] = useState(false);
  const [filtersCollapsed, setFiltersCollapsed] = useState(
    () => readStorage(FILTERS_COLLAPSED_KEY) === "true",
  );

  const feedKey = useMemo(
    () => toFeedKey(state.filters, resume.activeId),
    [state.filters, resume.activeId],
  );
  const listKey = useMemo(() => JSON.stringify(feedKey), [feedKey]);
  const feed = useVacancyFeed(feedKey, (key) => feedKeyToApiParams(key, new Date()), resume.resolved);

  const onChange = useCallback<FilterChange>(
    (patch, options) => {
      update((current) => withFilters(current, patch), options);
    },
    [update],
  );

  const onResetFilters = useCallback(() => {
    update((current) => clearFilters(current));
  }, [update]);

  const onPage = useCallback(
    (page: number) => {
      update((current) => withFilters(current, { page }));
      window.scrollTo(0, 0);
    },
    [update],
  );

  const cardHref = useCallback(
    (id: string) => {
      const qs = serializeFeedParams(withVacancy(state, id)).toString();
      return qs ? `/vacancies?${qs}` : "/vacancies";
    },
    [state],
  );

  const closeDrawer = useCallback(() => {
    update((current) => withVacancy(current, null), { replace: true });
  }, [update]);

  const toggleFiltersCollapsed = useCallback(() => {
    setFiltersCollapsed((prev) => {
      const next = !prev;
      writeStorage(FILTERS_COLLAPSED_KEY, String(next));
      return next;
    });
  }, []);

  const total = feed.data?.total ?? null;
  const description =
    !resume.resolved || feed.isPending
      ? "Загружаем вакансии…"
      : feed.isError
        ? "Не удалось посчитать выдачу"
        : `Найдено ${total ?? 0} ${pluralRu(total ?? 0, ["вакансия", "вакансии", "вакансий"])}`;

  return (
    <>
      <PageHeader eyebrow="Лента" title="Вакансии" description={description} />

      {resume.resolved && resume.items.length === 0 && (
        <div
          role="status"
          className="mb-5 rounded-card border border-line bg-surface-muted px-4 py-3 text-[13px] leading-[1.5] text-ink-body"
        >
          Создайте резюме, чтобы видеть процент соответствия.{" "}
          <Link to="/resumes" className="font-medium text-accent hover:text-accent-hover">
            Перейти к резюме
          </Link>
        </div>
      )}

      <div className="flex items-start gap-8">
        {!isBelowMd && !filtersCollapsed && (
          <aside className="w-[260px] shrink-0">
            <FilterPanel filters={state.filters} onChange={onChange} onReset={onResetFilters} />
          </aside>
        )}

        <div className="min-w-0 flex-1">
          <FeedToolbar
            filters={state.filters}
            onChange={onChange}
            resumes={{
              items: resume.items,
              activeId: resume.activeId,
              loading: !resume.resolved,
              failed: resume.resumes.isError,
              onSelect: resume.select,
            }}
            isBelowMd={isBelowMd}
            filtersCollapsed={filtersCollapsed}
            onToggleFilters={toggleFiltersCollapsed}
            onOpenFiltersModal={() => setFiltersModalOpen(true)}
          />
          <VacancyFeed
            query={feed}
            listKey={listKey}
            filters={state.filters}
            now={new Date()}
            sourceTypes={sourceTypes}
            actions={actions}
            cardHref={cardHref}
            onPage={onPage}
            onResetFilters={onResetFilters}
            onShowAll={() => onChange({ saved: false })}
          />
        </div>
      </div>

      <FiltersModal
        open={isBelowMd && filtersModalOpen}
        onClose={() => setFiltersModalOpen(false)}
        filters={state.filters}
        onChange={onChange}
        onReset={onResetFilters}
        total={total}
      />

      <VacancyDrawer
        vacancyId={state.vacancyId}
        resumeId={resume.activeId}
        now={new Date()}
        sourceTypes={sourceTypes}
        actions={actions}
        onClose={closeDrawer}
      />
    </>
  );
}
