import type { UseQueryResult } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Bookmark, ChevronLeft, ChevronRight, Database, SearchX } from "lucide-react";

import type { VacancyListResponse } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { hasNarrowingFilters } from "@/features/vacancies/feed-state";
import type { FeedFilters } from "@/features/vacancies/feed-state";
import type { SourceTypes } from "@/features/vacancies/source-meta";
import type { VacancyActions } from "@/features/vacancies/use-vacancy-actions";
import { VacancyCard } from "@/features/vacancies/VacancyCard";
import { rise, useReducedMotionSafe } from "@/lib/motion";

const SKELETON_CARDS = 6;

/** Плейсхолдер ленты в форме настоящих карточек. */
export function FeedSkeleton() {
  return (
    <div aria-busy="true" aria-label="Загружаем вакансии" className="space-y-3">
      {Array.from({ length: SKELETON_CARDS }, (_, index) => (
        <div key={index} className="rounded-card border border-line bg-surface p-5 shadow-card">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <Skeleton className="h-3 w-40" />
              <Skeleton className="mt-3 h-5 w-3/5" />
              <Skeleton className="mt-2 h-3.5 w-32" />
            </div>
            <Skeleton rounded="full" className="h-11 w-11" />
          </div>
          <div className="mt-4 flex gap-4">
            <Skeleton className="h-3 w-36" />
            <Skeleton className="h-3 w-28" />
          </div>
          <div className="mt-4 flex gap-1.5">
            <Skeleton className="h-6 w-14" />
            <Skeleton className="h-6 w-[72px]" />
            <Skeleton className="h-6 w-12" />
            <Skeleton className="h-6 w-16" />
          </div>
        </div>
      ))}
    </div>
  );
}

interface PaginationProps {
  page: number;
  totalPages: number;
  onPage: (page: number) => void;
}

function Pagination({ page, totalPages, onPage }: PaginationProps) {
  if (totalPages <= 1) {
    return null;
  }
  return (
    <nav aria-label="Страницы ленты" className="mt-6 flex items-center justify-between gap-3">
      <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        <ChevronLeft size={14} aria-hidden /> Назад
      </Button>
      <span className="text-[12px] text-ink-muted tabular-nums">
        стр. {page} из {totalPages}
      </span>
      <Button size="sm" variant="secondary" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>
        Вперёд <ChevronRight size={14} aria-hidden />
      </Button>
    </nav>
  );
}

interface VacancyFeedProps {
  query: UseQueryResult<VacancyListResponse>;
  /** Хеш ключа запроса: новый ключ — новый контейнер, stagger проигрывается заново. */
  listKey: string;
  filters: FeedFilters;
  now: Date;
  sourceTypes: SourceTypes;
  actions: VacancyActions;
  cardHref: (id: string) => string;
  onPage: (page: number) => void;
  onResetFilters: () => void;
  onShowAll: () => void;
}

export function VacancyFeed({
  query,
  listKey,
  filters,
  now,
  sourceTypes,
  actions,
  cardHref,
  onPage,
  onResetFilters,
  onShowAll,
}: VacancyFeedProps) {
  const reduced = useReducedMotionSafe();

  if (query.isPending) {
    return <FeedSkeleton />;
  }
  if (query.isError) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />;
  }

  const { items, total, page_size: pageSize } = query.data;
  const totalPages = Math.max(Math.ceil(total / pageSize), 1);

  if (items.length === 0) {
    if (filters.page > 1 && total > 0) {
      return (
        <EmptyState
          icon={SearchX}
          title="На этой странице пусто"
          description={`Всего страниц: ${totalPages}. Вернитесь к началу выдачи.`}
          action={<Button onClick={() => onPage(1)}>На первую страницу</Button>}
        />
      );
    }
    if (hasNarrowingFilters(filters)) {
      return (
        <EmptyState
          icon={SearchX}
          title="Ничего не нашлось"
          description="Под выбранные условия вакансий нет. Ослабьте фильтры или измените поисковый запрос."
          action={<Button onClick={onResetFilters}>Сбросить фильтры</Button>}
        />
      );
    }
    if (filters.saved) {
      return (
        <EmptyState
          icon={Bookmark}
          title="Сохранённых вакансий пока нет"
          description="Сохраняйте вакансии из ленты кнопкой с закладкой — они появятся здесь."
          action={<Button onClick={onShowAll}>Перейти ко всем вакансиям</Button>}
        />
      );
    }
    return (
      <EmptyState
        icon={Database}
        title="Вакансий нет"
        description={
          <>
            Наполните базу демо-данными:{" "}
            <code className="rounded bg-surface-muted px-1.5 py-0.5 text-[13px] text-ink-body">
              docker compose exec api python -m scripts.seed
            </code>
          </>
        }
      />
    );
  }

  return (
    <>
      <ul key={listKey} aria-label="Вакансии" className="space-y-3">
        {items.map((vacancy, index) => (
          <motion.li key={vacancy.id} {...rise(index, reduced)}>
            <VacancyCard
              vacancy={vacancy}
              href={cardHref(vacancy.id)}
              now={now}
              sourceTypes={sourceTypes}
              showHidden={filters.show_hidden}
              actions={actions}
            />
          </motion.li>
        ))}
      </ul>
      <Pagination page={filters.page} totalPages={totalPages} onPage={onPage} />
    </>
  );
}
