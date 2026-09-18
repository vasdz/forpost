'use client';

import { useId, useState, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

export type Tab = { id: string; label: string; content: ReactNode };

function getTab(tabs: readonly Tab[], index: number): Tab | undefined {
  if (!Number.isInteger(index) || index < 0 || index >= tabs.length) {
    return undefined;
  }
  return tabs.at(index);
}

export function Tabs({ tabs, defaultTabId, value, onValueChange }: { tabs: Tab[]; defaultTabId?: string; value?: string; onValueChange?: (id: string) => void }) {
  const [internalId, setInternalId] = useState(defaultTabId ?? tabs.at(0)?.id);
  const activeId = value ?? internalId;
  const setActiveId = (id: string) => { if (value === undefined) setInternalId(id); onValueChange?.(id); };
  const baseId = useId();
  const activeIndex = Math.max(0, tabs.findIndex((tab) => tab.id === activeId));
  const activeTab = getTab(tabs, activeIndex);
  const onKeyDown = (index: number, event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (!['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const nextIndex = event.key === 'ArrowRight' ? (index + 1) % tabs.length : event.key === 'ArrowLeft' ? (index - 1 + tabs.length) % tabs.length : event.key === 'Home' ? 0 : tabs.length - 1;
    const nextTab = getTab(tabs, nextIndex);
    if (!nextTab) return;
    setActiveId(nextTab.id);
    document.getElementById(`${baseId}-${nextTab.id}`)?.focus();
  };
  if (!activeTab) return null;
  return <div><div role="tablist" aria-label="Разделы" className="inline-flex gap-1 rounded-[4px] border border-[var(--color-border)] bg-[var(--color-panel-2)] p-1">{tabs.map((tab, index) => <button key={tab.id} id={`${baseId}-${tab.id}`} role="tab" type="button" aria-selected={tab.id === activeId} aria-controls={`${baseId}-panel-${tab.id}`} tabIndex={tab.id === activeId ? 0 : -1} onKeyDown={(event) => onKeyDown(index, event)} onClick={() => setActiveId(tab.id)} className={cn('rounded-[4px] border px-3 py-1.5 text-xs font-medium transition-colors', tab.id === activeId ? 'border-[var(--color-border)] bg-[var(--color-panel)] text-[var(--color-text)]' : 'border-transparent text-[var(--color-text-muted)] hover:text-[var(--color-text)]')}>{tab.label}</button>)}</div><div id={`${baseId}-panel-${activeTab.id}`} role="tabpanel" aria-labelledby={`${baseId}-${activeTab.id}`} className="pt-5">{activeTab.content}</div></div>;
}
