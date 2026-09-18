import { forwardRef, type InputHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...props }, ref) {
  return <input ref={ref} className={cn('control-surface h-10 w-full rounded-[8px] px-3.5 text-sm outline-none placeholder:text-[var(--color-text-dim)] hover:border-[color-mix(in_srgb,var(--color-data)_35%,var(--color-border))]', className)} {...props} />;
});
