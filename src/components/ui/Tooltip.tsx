'use client';

import { useId, useState, type ReactNode } from 'react';

export function Tooltip({ content, children }: { content: string; children: ReactNode }) {
  const [visible, setVisible] = useState(false);
  const id = useId();
  return <span className="relative inline-flex" onMouseEnter={() => setVisible(true)} onMouseLeave={() => setVisible(false)} onFocus={() => setVisible(true)} onBlur={() => setVisible(false)} aria-describedby={visible ? id : undefined}>{children}{visible && <span id={id} role="tooltip" className="glass-surface absolute bottom-full left-1/2 z-30 mb-2 w-max max-w-64 -translate-x-1/2 px-3 py-2 text-xs leading-5 text-[var(--color-text)]">{content}</span>}</span>;
}
