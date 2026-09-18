'use client';

import type { ReactNode } from 'react';

import { useLocalSituation } from '@/data/LocalSituationProvider';
import type { LocalSituationSnapshot } from '@/data/localSituationContract';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';

export function LocalSituationGate({ children }: { children: (snapshot: LocalSituationSnapshot) => ReactNode }) {
  const state = useLocalSituation();

  if (state.status === 'loading') {
    return <section aria-live="polite" role="status" className="panel p-5"><Skeleton className="h-5 w-56" /><p className="mt-3 text-sm text-[var(--color-text-muted)]">Загрузка локального обезличенного снимка.</p></section>;
  }

  if (state.status === 'unavailable') {
    return <EmptyState title="Локальный снимок недоступен" description={state.message} />;
  }

  return <>{children(state.snapshot)}</>;
}

export function UnavailableCapability({ title, description }: { title: string; description: string }) {
  return <EmptyState title={title} description={description} />;
}
