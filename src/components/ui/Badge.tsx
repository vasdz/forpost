import type { HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

const colorByTone = {
  critical: 'status-critical text-[var(--color-text)]',
  high: 'status-high text-[var(--color-text)]',
  medium: 'status-medium text-[var(--color-text)]',
  low: 'status-low text-[var(--color-text)]',
  neutral: 'status-neutral border-[var(--color-border)] text-[var(--color-text)]',
};

function getColorClass(tone: unknown): string {
  switch (tone) {
    case 'critical':
      return colorByTone.critical;
    case 'high':
      return colorByTone.high;
    case 'medium':
      return colorByTone.medium;
    case 'low':
      return colorByTone.low;
    default:
      return colorByTone.neutral;
  }
}

export function Badge({ className, children, tone = 'neutral', ...props }: HTMLAttributes<HTMLSpanElement> & { tone?: keyof typeof colorByTone }) {
  return <span className={cn('inline-flex items-center gap-1 rounded-[6px] border px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em]', getColorClass(tone), className)} {...props}>{children}</span>;
}
