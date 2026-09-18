import { cn } from '@/lib/utils';

export function Skeleton({ className }: { className?: string }) {
  return <div aria-busy="true" aria-label="Загрузка" className={cn('rounded-[4px] bg-[var(--color-skeleton)]', className)} />;
}
