'use client';

import type { ReactNode } from 'react';

import { useLocalSituation } from '@/data/LocalSituationProvider';

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow: string; title: string; description: string; actions?: ReactNode }) {
  const state = useLocalSituation();
  const freshness = state.status === 'ready'
    ? 'Локальный обезличенный снимок загружен'
    : state.status === 'loading'
      ? 'Локальный обезличенный снимок загружается'
      : 'Локальный обезличенный снимок недоступен';

  return <header className="mb-8 flex flex-wrap items-end justify-between gap-6"><div className="min-w-0"><p className="eyebrow mb-2">{eyebrow}</p><h1 className="max-w-4xl font-heading text-[clamp(28px,3vw,32px)] font-semibold leading-[1.15] tracking-[-0.025em]">{title}</h1><p className="mt-3 max-w-3xl text-sm leading-6 text-[var(--color-text-muted)]">{description}</p><p className="mt-2 inline-flex items-center gap-2 text-[11px] text-[var(--color-text-dim)] before:h-1.5 before:w-1.5 before:rounded-full before:bg-[var(--color-warning)]">{freshness}</p></div>{actions && <div className="min-w-0">{actions}</div>}</header>;
}
