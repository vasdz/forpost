'use client';

import { useEffect, useId, useRef, type ReactNode } from 'react';
import { X } from 'lucide-react';
import { Button } from './Button';

const focusableSelector = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function getFocusableElements(container: HTMLElement | null) {
  return Array.from(container?.querySelectorAll<HTMLElement>(focusableSelector) ?? []).filter((element) => element.getAttribute('aria-hidden') !== 'true');
}

export function Modal({ isOpen, onClose, title, children }: { isOpen: boolean; onClose: () => void; title: string; children: ReactNode }) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useEffect(() => {
    if (!isOpen) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const blocked: Array<{ element: HTMLElement; inert: string | null; hidden: string | null }> = [];
    let branch: HTMLElement | null = dialogRef.current?.parentElement ?? null;
    while (branch && branch !== document.body) {
      for (const sibling of Array.from(branch.parentElement?.children ?? [])) {
        if (sibling === branch || !(sibling instanceof HTMLElement)) continue;
        blocked.push({ element: sibling, inert: sibling.getAttribute('inert'), hidden: sibling.getAttribute('aria-hidden') });
        sibling.setAttribute('inert', ''); sibling.setAttribute('aria-hidden', 'true');
      }
      branch = branch.parentElement;
    }
    getFocusableElements(dialogRef.current)[0]?.focus();
    return () => {
      blocked.forEach(({ element, inert, hidden }) => {
        if (inert === null) element.removeAttribute('inert'); else element.setAttribute('inert', inert);
        if (hidden === null) element.removeAttribute('aria-hidden'); else element.setAttribute('aria-hidden', hidden);
      });
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, [isOpen]);
  if (!isOpen) return null;
  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); onClose(); return; }
    if (event.key !== 'Tab') return;
    const focusable = getFocusableElements(dialogRef.current);
    if (!focusable.length) return;
    const first = focusable[0]; const last = focusable.at(-1)!;
    if (!focusable.includes(document.activeElement as HTMLElement)) { event.preventDefault(); (event.shiftKey ? last : first).focus(); return; }
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  };
  return <div className="fixed inset-0 z-50 grid place-items-center bg-[#05070d]/80 p-4 backdrop-blur-sm" onMouseDown={onClose}><div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1} onKeyDown={onKeyDown} onMouseDown={(event) => event.stopPropagation()} className="glass-surface max-h-[calc(100vh-32px)] w-full max-w-3xl overflow-y-auto p-6 md:p-8"><header className="mb-6 flex items-start justify-between gap-4"><h2 id={titleId} className="font-heading text-xl font-semibold tracking-[-0.02em]">{title}</h2><Button variant="ghost" size="sm" onClick={onClose} aria-label="Закрыть окно"><X size={17} aria-hidden="true" /></Button></header>{children}</div></div>;
}
