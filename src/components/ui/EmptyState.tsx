import type { ReactNode } from 'react';

export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <section className="surface grid min-h-56 place-items-center p-8 text-center"><div><div aria-hidden="true" className="mx-auto mb-5 h-px w-12 bg-[var(--color-border)]" /><h2 className="font-heading text-lg font-semibold tracking-[-0.02em]">{title}</h2><p className="mt-2 max-w-md text-sm leading-6 text-[var(--color-text-muted)]">{description}</p>{action && <div className="mt-5">{action}</div>}</div></section>;
}
