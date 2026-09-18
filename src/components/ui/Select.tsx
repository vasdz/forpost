import type { SelectHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

export type SelectOption = { value: string; label: string };
type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & { label: string; options: SelectOption[] };

export function Select({ id, label, options, className, ...props }: SelectProps) {
  const inputId = id ?? `select-${label}`;
  return <label className="grid gap-1 text-xs text-[var(--color-text-muted)]" htmlFor={inputId}>{label}
    <select id={inputId} className={cn('control-surface h-10 rounded-[8px] px-3.5 text-sm text-[var(--color-text)]', className)} {...props}>
      {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
    </select>
  </label>;
}
