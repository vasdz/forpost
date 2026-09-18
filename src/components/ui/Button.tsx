import type { ButtonHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
  size?: 'sm' | 'md';
};

function getVariantClass(variant: unknown): string {
  switch (variant) {
    case 'secondary':
      return 'border-[var(--color-border)] bg-[var(--color-panel-2)] hover:bg-[var(--color-hover)]';
    case 'danger':
      return 'border-[var(--color-danger)] bg-[var(--color-danger)] text-white hover:brightness-110';
    case 'ghost':
      return 'border-transparent bg-transparent hover:bg-[var(--color-hover)]';
    default:
      return 'border-[var(--color-data)] bg-[var(--color-data)] text-white hover:brightness-110';
  }
}

function getSizeClass(size: unknown): string {
  return size === 'sm' ? 'h-8 px-3 text-xs' : 'h-10 px-4 text-sm';
}

export function Button({ className, variant = 'primary', size = 'md', type = 'button', ...props }: ButtonProps) {
  return <button type={type} className={cn('control-surface inline-flex items-center justify-center gap-2 rounded-[8px] border font-medium transition-colors duration-200 ease-out disabled:cursor-not-allowed disabled:opacity-50', getVariantClass(variant), getSizeClass(size), className)} {...props} />;
}
