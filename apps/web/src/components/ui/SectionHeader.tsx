import type { ReactNode } from 'react';

interface SectionHeaderProps {
  eyebrow: string;
  title: string;
  action?: ReactNode;
}

export function SectionHeader({ eyebrow, title, action }: SectionHeaderProps) {
  return (
    <div className="mb-6 flex items-center justify-between gap-4">
      <div>
        <p className="text-[10px] uppercase tracking-[0.18em] text-cyan-300">{eyebrow}</p>
        <h1 className="mt-2 text-2xl font-semibold text-slate-50">{title}</h1>
      </div>
      {action}
    </div>
  );
}
