import type { ReactNode } from 'react';

interface CardProps {
  title?: string;
  subtitle?: string;
  children: ReactNode;
  className?: string;
}

export function Card({ title, subtitle, children, className = '' }: CardProps) {
  return (
    <section className={`rounded-2xl border border-slate-800 bg-slate-900/80 p-5 shadow-[0_0_0_1px_rgba(15,23,42,0.7)] ${className}`}>
      {(title || subtitle) && (
        <header className="mb-4 flex items-start justify-between gap-3">
          <div>
            {title && <h2 className="text-sm font-medium uppercase tracking-[0.12em] text-slate-300">{title}</h2>}
            {subtitle && <p className="mt-1 text-xs text-slate-400">{subtitle}</p>}
          </div>
        </header>
      )}
      {children}
    </section>
  );
}
