import { cn } from "@/lib/cn";

export interface Option<T extends string> {
  value: T;
  label: string;
}

const CHIP = "rounded-md border px-2.5 py-1.5 text-[12px] disabled:cursor-not-allowed disabled:opacity-60";
const CHIP_ON = "border-accent-border bg-accent-soft font-medium text-accent";
const CHIP_OFF = "border-line bg-surface text-ink-muted hover:border-accent-border hover:text-ink";

interface ToggleGroupProps<T extends string> {
  label: string;
  options: readonly Option<T>[];
  value: readonly T[];
  onChange: (next: T[]) => void;
  disabled?: boolean;
  className?: string;
}

/** Множественный выбор чипами; пустой выбор — «любое значение». */
export function ToggleGroup<T extends string>({ label, options, value, onChange, disabled, className }: ToggleGroupProps<T>) {
  const toggle = (option: T) => {
    const next = value.includes(option) ? value.filter((item) => item !== option) : [...value, option];
    // Порядок как в options: URL и ключ запроса не зависят от порядка кликов.
    onChange(options.map((item) => item.value).filter((item) => next.includes(item)));
  };
  return (
    <div role="group" aria-label={label} className={cn("flex flex-wrap gap-1.5", className)}>
      {options.map((option) => {
        const active = value.includes(option.value);
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={active}
            disabled={disabled}
            onClick={() => toggle(option.value)}
            className={cn(CHIP, active ? CHIP_ON : CHIP_OFF)}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

interface SegmentedControlProps<T extends string> {
  label: string;
  options: readonly Option<T>[];
  value: T;
  onChange: (next: T) => void;
  disabled?: boolean;
  className?: string;
}

/** Выбор одного из 2–4 вариантов («любая / есть / нет»). */
export function SegmentedControl<T extends string>({
  label,
  options,
  value,
  onChange,
  disabled,
  className,
}: SegmentedControlProps<T>) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={cn("inline-flex flex-wrap gap-0.5 rounded-lg border border-line bg-surface-muted p-0.5", className)}
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={disabled}
            onClick={() => onChange(option.value)}
            className={cn(
              "rounded-md px-2.5 py-1 text-[12px] disabled:cursor-not-allowed disabled:opacity-60",
              active ? "bg-surface font-medium text-ink shadow-card" : "text-ink-muted hover:text-ink",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
