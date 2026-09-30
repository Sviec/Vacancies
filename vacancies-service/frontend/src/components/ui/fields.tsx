/**
 * Поля формы с подписью, подсказкой и ошибкой. Ошибка связывается с полем
 * через `aria-describedby` и помечает его `aria-invalid`.
 */

import { Check, ChevronDown } from "lucide-react";
import { useId } from "react";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/cn";

export const CONTROL_CLASSES = cn(
  "w-full rounded-lg border border-line bg-surface px-3 text-[14px] text-ink",
  "hover:border-accent-border focus-visible:border-accent-border",
  "disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-ink-muted",
  "aria-[invalid=true]:border-danger",
);

interface FieldShellProps {
  label?: ReactNode;
  hint?: ReactNode;
  error?: string | null;
  className?: string;
  children: (ids: { id: string; describedBy: string | undefined; invalid: boolean }) => ReactNode;
}

export function FieldShell({ label, hint, error, className, children }: FieldShellProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [error ? errorId : null, hint ? hintId : null].filter(Boolean).join(" ");
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {label && (
        <label htmlFor={id} className="text-[13px] font-medium text-ink-body">
          {label}
        </label>
      )}
      {children({ id, describedBy: describedBy || undefined, invalid: Boolean(error) })}
      {error && (
        <p id={errorId} className="text-[13px] leading-5 text-danger">
          {error}
        </p>
      )}
      {hint && !error && (
        <p id={hintId} className="text-[13px] leading-5 text-ink-muted">
          {hint}
        </p>
      )}
    </div>
  );
}

interface CommonFieldProps {
  label?: ReactNode;
  hint?: ReactNode;
  error?: string | null;
  containerClassName?: string;
}

type TextFieldProps = CommonFieldProps & Omit<ComponentProps<"input">, "type"> & {
  type?: "text" | "email" | "url" | "tel" | "search" | "date";
};

export function TextField({ label, hint, error, containerClassName, className, type = "text", ...props }: TextFieldProps) {
  return (
    <FieldShell label={label} hint={hint} error={error} className={containerClassName}>
      {({ id, describedBy, invalid }) => (
        <input
          id={id}
          type={type}
          aria-invalid={invalid || undefined}
          aria-describedby={describedBy}
          className={cn(CONTROL_CLASSES, "h-9", className)}
          {...props}
        />
      )}
    </FieldShell>
  );
}

type NumberFieldProps = CommonFieldProps & Omit<ComponentProps<"input">, "type" | "inputMode">;

/** Числовое поле: значение остаётся строкой, парсит вызывающий код. */
export function NumberField({ label, hint, error, containerClassName, className, ...props }: NumberFieldProps) {
  return (
    <FieldShell label={label} hint={hint} error={error} className={containerClassName}>
      {({ id, describedBy, invalid }) => (
        <input
          id={id}
          type="text"
          inputMode="numeric"
          aria-invalid={invalid || undefined}
          aria-describedby={describedBy}
          className={cn(CONTROL_CLASSES, "h-9 tabular-nums", className)}
          {...props}
        />
      )}
    </FieldShell>
  );
}

type TextAreaProps = CommonFieldProps & ComponentProps<"textarea">;

export function TextArea({ label, hint, error, containerClassName, className, rows = 4, ...props }: TextAreaProps) {
  return (
    <FieldShell label={label} hint={hint} error={error} className={containerClassName}>
      {({ id, describedBy, invalid }) => (
        <textarea
          id={id}
          rows={rows}
          aria-invalid={invalid || undefined}
          aria-describedby={describedBy}
          className={cn(CONTROL_CLASSES, "py-2 leading-[1.5]", className)}
          {...props}
        />
      )}
    </FieldShell>
  );
}

type SelectProps = CommonFieldProps & ComponentProps<"select">;

/** Нативный `<select>` в стиле полей: `appearance-none` и шеврон lucide. */
export function Select({ label, hint, error, containerClassName, className, children, ...props }: SelectProps) {
  return (
    <FieldShell label={label} hint={hint} error={error} className={containerClassName}>
      {({ id, describedBy, invalid }) => (
        <div className="relative">
          <select
            id={id}
            aria-invalid={invalid || undefined}
            aria-describedby={describedBy}
            className={cn(CONTROL_CLASSES, "h-9 cursor-pointer appearance-none pr-9", className)}
            {...props}
          >
            {children}
          </select>
          <ChevronDown
            size={16}
            aria-hidden
            className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-ink-muted"
          />
        </div>
      )}
    </FieldShell>
  );
}

interface CheckboxProps extends Omit<ComponentProps<"input">, "type" | "onChange"> {
  label: ReactNode;
  onCheckedChange: (checked: boolean) => void;
}

export function Checkbox({ label, checked, onCheckedChange, className, disabled, ...props }: CheckboxProps) {
  return (
    <label
      className={cn(
        "inline-flex cursor-pointer items-center gap-2 text-[13px] text-ink-body select-none",
        disabled && "cursor-not-allowed opacity-60",
        className,
      )}
    >
      <span className="relative inline-flex">
        <input
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(event) => onCheckedChange(event.target.checked)}
          className="peer h-4 w-4 cursor-pointer appearance-none rounded border border-line-strong bg-surface checked:border-accent checked:bg-accent"
          {...props}
        />
        <Check
          size={12}
          strokeWidth={3}
          aria-hidden
          className="pointer-events-none absolute top-0.5 left-0.5 hidden text-on-accent peer-checked:block"
        />
      </span>
      {label}
    </label>
  );
}
