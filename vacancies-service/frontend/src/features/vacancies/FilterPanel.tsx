import type { ReactNode } from "react";

import { useFiltersMeta } from "@/api/vacancies";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { Checkbox, NumberField, Select } from "@/components/ui/fields";
import { Skeleton } from "@/components/ui/Skeleton";
import { SegmentedControl, ToggleGroup } from "@/components/ui/ToggleGroup";
import type { Option } from "@/components/ui/ToggleGroup";
import {
  countActiveFilters,
  EMPLOYMENT_TYPES,
  EXPERIENCE_LEVELS,
  hasNarrowingFilters,
  WORK_FORMATS,
} from "@/features/vacancies/feed-state";
import type { FeedFilters, PublishedPreset } from "@/features/vacancies/feed-state";
import { useDebouncedCommit } from "@/features/vacancies/use-debounced-commit";
import { EMPLOYMENT_TYPE_LABELS, EXPERIENCE_LEVEL_LABELS, WORK_FORMAT_LABELS } from "@/lib/labels";

export type FilterChange = (patch: Partial<FeedFilters>, options?: { replace?: boolean }) => void;

const SALARY_DEBOUNCE_MS = 400;

function options<T extends string>(values: readonly T[], labels: Record<T, string>): Option<T>[] {
  return values.filter((value) => value !== "unknown").map((value) => ({ value, label: labels[value] }));
}

const LEVEL_OPTIONS = options(EXPERIENCE_LEVELS, EXPERIENCE_LEVEL_LABELS);
const EMPLOYMENT_OPTIONS = options(EMPLOYMENT_TYPES, EMPLOYMENT_TYPE_LABELS);
const FORMAT_OPTIONS = options(WORK_FORMATS, WORK_FORMAT_LABELS);

type PublishedOption = PublishedPreset | "all";
const PUBLISHED_OPTIONS: Option<PublishedOption>[] = [
  { value: "all", label: "Всё время" },
  { value: "3d", label: "3 дня" },
  { value: "7d", label: "Неделя" },
  { value: "30d", label: "Месяц" },
];

type TriState = "any" | "yes" | "no";
const toTri = (value: boolean | null): TriState => (value === null ? "any" : value ? "yes" : "no");
const fromTri = (value: TriState): boolean | null => (value === "any" ? null : value === "yes");

const HAS_SALARY_OPTIONS: Option<TriState>[] = [
  { value: "any", label: "Любая" },
  { value: "yes", label: "Указана" },
  { value: "no", label: "Не указана" },
];
const RELOCATION_OPTIONS: Option<TriState>[] = [
  { value: "any", label: "Неважно" },
  { value: "yes", label: "Есть" },
  { value: "no", label: "Нет" },
];

const parseSalary = (text: string): number | null => {
  const digits = text.replace(/\s/g, "");
  return /^\d+$/.test(digits) && Number.isSafeInteger(Number(digits)) ? Number(digits) : null;
};
const normalizeSalary = (text: string): string => {
  const value = parseSalary(text);
  return value === null ? "" : String(value);
};

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="min-w-0">
      <legend className="mb-2 text-[11px] font-semibold tracking-[0.09em] text-ink-muted uppercase">{title}</legend>
      {children}
    </fieldset>
  );
}

function SalaryField({ value, onChange }: { value: number | null; onChange: FilterChange }) {
  const [text, setText] = useDebouncedCommit(
    value === null ? "" : String(value),
    (next) => onChange({ salary_min: parseSalary(next) }, { replace: true }),
    normalizeSalary,
    SALARY_DEBOUNCE_MS,
  );
  const invalid = text.trim() !== "" && parseSalary(text) === null;
  return (
    <NumberField
      label="Зарплата от"
      placeholder="например, 200000"
      value={text}
      onChange={(event) => setText(event.target.value)}
      error={invalid ? "Только целое число" : null}
      hint="Учитываются месячные вилки"
    />
  );
}

interface FilterPanelProps {
  filters: FeedFilters;
  onChange: FilterChange;
  onReset: () => void;
}

/** Все фильтры п. 5.5 ТЗ, кроме навыков. Колонка слева или модалка ниже 768px. */
export function FilterPanel({ filters, onChange, onReset }: FilterPanelProps) {
  const meta = useFiltersMeta();
  const active = countActiveFilters(filters);

  return (
    <div className="flex flex-col gap-6">
      <Group title="Уровень">
        <ToggleGroup
          label="Уровень"
          options={LEVEL_OPTIONS}
          value={filters.experience_level}
          onChange={(experience_level) => onChange({ experience_level })}
        />
      </Group>
      <Group title="Формат работы">
        <ToggleGroup
          label="Формат работы"
          options={FORMAT_OPTIONS}
          value={filters.work_format}
          onChange={(work_format) => onChange({ work_format })}
        />
      </Group>
      <Group title="Занятость">
        <ToggleGroup
          label="Занятость"
          options={EMPLOYMENT_OPTIONS}
          value={filters.employment_type}
          onChange={(employment_type) => onChange({ employment_type })}
        />
      </Group>

      <Group title="Локация и зарплата">
        {meta.isPending ? (
          <div aria-busy="true" aria-label="Загружаем значения фильтров" className="flex flex-col gap-3">
            <Skeleton className="h-9 w-full" rounded="lg" />
            <Skeleton className="h-9 w-full" rounded="lg" />
            <Skeleton className="h-9 w-full" rounded="lg" />
          </div>
        ) : meta.isError ? (
          <ErrorState
            compact
            title="Не удалось загрузить страны, города и валюты"
            error={meta.error}
            onRetry={() => void meta.refetch()}
            retrying={meta.isFetching}
          />
        ) : (
          <div className="flex flex-col gap-3">
            <Select
              label="Страна"
              value={filters.country ?? ""}
              onChange={(event) => onChange({ country: event.target.value || null })}
            >
              <option value="">Любая</option>
              {meta.data.countries.map((country) => (
                <option key={country} value={country}>
                  {country}
                </option>
              ))}
            </Select>
            <Select
              label="Город"
              value={filters.city ?? ""}
              onChange={(event) => onChange({ city: event.target.value || null })}
            >
              <option value="">Любой</option>
              {meta.data.cities.map((city) => (
                <option key={city} value={city}>
                  {city}
                </option>
              ))}
            </Select>
            <Select
              label="Валюта"
              value={filters.salary_currency ?? ""}
              onChange={(event) => onChange({ salary_currency: event.target.value || null })}
            >
              <option value="">Любая</option>
              {meta.data.currencies.map((currency) => (
                <option key={currency} value={currency}>
                  {currency}
                </option>
              ))}
            </Select>
          </div>
        )}
        <div className="mt-3">
          <SalaryField value={filters.salary_min} onChange={onChange} />
        </div>
      </Group>

      <Group title="Зарплата в вакансии">
        <SegmentedControl
          label="Зарплата в вакансии"
          options={HAS_SALARY_OPTIONS}
          value={toTri(filters.has_salary)}
          onChange={(value) => onChange({ has_salary: fromTri(value) })}
        />
      </Group>
      <Group title="Релокация">
        <SegmentedControl
          label="Релокация"
          options={RELOCATION_OPTIONS}
          value={toTri(filters.relocation_support)}
          onChange={(value) => onChange({ relocation_support: fromTri(value) })}
        />
      </Group>
      <Group title="Дата публикации">
        <SegmentedControl
          label="Дата публикации"
          options={PUBLISHED_OPTIONS}
          value={filters.published ?? "all"}
          onChange={(value) => onChange({ published: value === "all" ? null : value })}
        />
      </Group>

      <Group title="Источники">
        {meta.isPending ? (
          <div className="flex gap-1.5">
            <Skeleton className="h-7 w-24" />
            <Skeleton className="h-7 w-28" />
          </div>
        ) : meta.isError ? (
          <p className="text-[12px] text-ink-muted">Список источников недоступен</p>
        ) : (
          <ToggleGroup
            label="Источники"
            options={meta.data.sources.map((slug) => ({ value: slug, label: slug }))}
            value={filters.source}
            onChange={(source) => onChange({ source })}
          />
        )}
      </Group>

      <Checkbox
        label="Показывать скрытые"
        checked={filters.show_hidden}
        onCheckedChange={(show_hidden) => onChange({ show_hidden })}
      />

      <Button variant="ghost" size="sm" onClick={onReset} disabled={!hasNarrowingFilters(filters)} className="self-start">
        Сбросить всё{active > 0 ? ` (${active})` : ""}
      </Button>
    </div>
  );
}
