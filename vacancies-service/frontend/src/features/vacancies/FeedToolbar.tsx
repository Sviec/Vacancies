import { PanelLeftClose, PanelLeftOpen, Plus, Search, SlidersHorizontal } from "lucide-react";
import { Link } from "react-router";

import type { ResumeListItem, VacancySort } from "@/api/types";
import { buttonClasses } from "@/components/ui/Button";
import { Button } from "@/components/ui/Button";
import { CONTROL_CLASSES, Select } from "@/components/ui/fields";
import { IconButton } from "@/components/ui/IconButton";
import { Skeleton } from "@/components/ui/Skeleton";
import { SegmentedControl } from "@/components/ui/ToggleGroup";
import type { FilterChange } from "@/features/vacancies/FilterPanel";
import { countActiveFilters, effectiveSort } from "@/features/vacancies/feed-state";
import type { FeedFilters } from "@/features/vacancies/feed-state";
import { useDebouncedCommit } from "@/features/vacancies/use-debounced-commit";
import { cn } from "@/lib/cn";
import { formatScore10 } from "@/lib/format";
import { VACANCY_SORT_LABELS } from "@/lib/labels";

const SEARCH_DEBOUNCE_MS = 300;
const trim = (text: string) => text.trim();

function resumeOptionLabel(resume: ResumeListItem): string {
  const score = resume.score === null ? "без оценки" : formatScore10(resume.score);
  return `${resume.title} · ${score}${resume.is_primary ? " · основное" : ""}`;
}

interface ResumeSelectProps {
  items: readonly ResumeListItem[];
  activeId: string | null;
  loading: boolean;
  failed: boolean;
  onSelect: (id: string) => void;
}

function ResumeSelect({ items, activeId, loading, failed, onSelect }: ResumeSelectProps) {
  if (loading) {
    return <Skeleton className="h-9 w-full sm:w-72" rounded="lg" />;
  }
  if (failed) {
    return <p className="text-[13px] text-danger">Резюме не загрузились — лента без процента соответствия</p>;
  }
  if (items.length === 0) {
    return (
      <Link to="/resumes" className={buttonClasses("primary", "md")}>
        <Plus size={15} aria-hidden /> Создать резюме
      </Link>
    );
  }
  return (
    <Select
      aria-label="Резюме для подбора"
      value={activeId ?? ""}
      onChange={(event) => onSelect(event.target.value)}
      containerClassName="w-full sm:w-72"
    >
      {items.map((resume) => (
        <option key={resume.id} value={resume.id}>
          {resumeOptionLabel(resume)}
        </option>
      ))}
    </Select>
  );
}

function SearchInput({ value, onChange }: { value: string; onChange: FilterChange }) {
  const [text, setText] = useDebouncedCommit(
    value,
    (next) => onChange({ q: next.trim() }, { replace: true }),
    trim,
    SEARCH_DEBOUNCE_MS,
  );
  return (
    <div className="relative min-w-0 flex-1">
      <Search size={16} aria-hidden className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-ink-subtle" />
      <input
        type="search"
        aria-label="Поиск вакансий"
        placeholder="Должность, компания или навык"
        value={text}
        onChange={(event) => setText(event.target.value)}
        className={cn(CONTROL_CLASSES, "h-9 pl-9")}
      />
    </div>
  );
}

type Tab = "all" | "saved";
const TABS = [
  { value: "all" as const, label: "Все" },
  { value: "saved" as const, label: "Сохранённые" },
];

interface FeedToolbarProps {
  filters: FeedFilters;
  onChange: FilterChange;
  resumes: {
    items: readonly ResumeListItem[];
    activeId: string | null;
    loading: boolean;
    failed: boolean;
    onSelect: (id: string) => void;
  };
  isBelowMd: boolean;
  filtersCollapsed: boolean;
  onToggleFilters: () => void;
  onOpenFiltersModal: () => void;
}

export function FeedToolbar({
  filters,
  onChange,
  resumes,
  isBelowMd,
  filtersCollapsed,
  onToggleFilters,
  onOpenFiltersModal,
}: FeedToolbarProps) {
  const sort = effectiveSort(filters, resumes.activeId);
  const sortOptions: VacancySort[] = [
    ...(resumes.activeId !== null ? (["match"] as const) : []),
    ...(filters.q.trim() ? (["relevance"] as const) : []),
    "date",
    "salary",
  ];
  const activeFilters = countActiveFilters(filters);

  return (
    <div className="mb-5 flex flex-col gap-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <ResumeSelect {...resumes} />
        <SearchInput value={filters.q} onChange={onChange} />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        {isBelowMd ? (
          <Button onClick={onOpenFiltersModal} aria-haspopup="dialog">
            <SlidersHorizontal size={15} aria-hidden />
            Фильтры{activeFilters > 0 ? ` (${activeFilters})` : ""}
          </Button>
        ) : (
          <IconButton
            label={filtersCollapsed ? "Показать фильтры" : "Свернуть фильтры"}
            aria-expanded={!filtersCollapsed}
            onClick={onToggleFilters}
            className="border border-line bg-surface"
          >
            {filtersCollapsed ? <PanelLeftOpen size={17} aria-hidden /> : <PanelLeftClose size={17} aria-hidden />}
          </IconButton>
        )}
        <SegmentedControl<Tab>
          label="Вкладки ленты"
          options={TABS}
          value={filters.saved ? "saved" : "all"}
          onChange={(tab) => onChange({ saved: tab === "saved" })}
        />
        <Select
          aria-label="Сортировка"
          value={sort}
          onChange={(event) => onChange({ sort: event.target.value as VacancySort })}
          containerClassName="ml-auto w-48"
        >
          {sortOptions.map((option) => (
            <option key={option} value={option}>
              {VACANCY_SORT_LABELS[option]}
            </option>
          ))}
        </Select>
      </div>
    </div>
  );
}
