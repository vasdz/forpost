'use client';

import { useId, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { SelectOption } from './Select';

type MultiSelectProps = { label: string; options: SelectOption[]; value: string[]; onChange: (value: string[]) => void };

export function MultiSelect({ label, options, value, onChange }: MultiSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const listId = useId();
  const toggleValue = (selected: string) => onChange(value.includes(selected) ? value.filter((item) => item !== selected) : [...value, selected]);
  return <div className="relative grid gap-1 text-xs text-[var(--color-text-muted)]">
    <span>{label}</span>
    <button type="button" aria-expanded={isOpen} aria-controls={listId} onClick={() => setIsOpen((open) => !open)} className="control-surface flex h-10 items-center justify-between rounded-[4px] px-3.5 text-left text-sm text-[var(--color-text)]">
      <span>{label} — выбрано: {value.length}</span><ChevronDown size={16} aria-hidden="true" />
    </button>
    {isOpen && <div id={listId} role="group" aria-label={label} className="surface absolute top-full z-20 mt-2 w-full p-2">
      {options.map((option) => <label key={option.value} className="flex cursor-pointer items-center gap-2 rounded-[6px] px-2.5 py-2 text-sm text-[var(--color-text)] hover:bg-[var(--color-hover)]"><input type="checkbox" checked={value.includes(option.value)} onChange={() => toggleValue(option.value)} />{option.label}</label>)}
    </div>}
  </div>;
}
