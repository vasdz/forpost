'use client';

import { BrainCircuit, ChevronRight, Moon, Sun } from 'lucide-react';
import { usePathname } from 'next/navigation';

import { Button } from '@/components/ui/Button';
import { useLocalSituation } from '@/data/LocalSituationProvider';
import { useThemeStore } from '@/stores/themeStore';

export function getPageName(pathname: string): string {
  switch (pathname) {
    case '/': return 'Обзор';
    case '/sensor-failure': return 'Отказ датчика';
    case '/fire-risk': return 'Пожарный риск';
    case '/unauthorized-access': return 'Несанкционированный доступ';
    case '/infrastructure-wear': return 'Износ инфраструктуры';
    case '/registries': return 'Реестры';
    case '/journals': return 'Журналы';
    case '/applications': return 'Заявки';
    case '/design-system': return 'Дизайн-система';
    default: return 'Раздел';
  }
}

export function Header() {
  const pathname = usePathname();
  const { theme, toggleTheme } = useThemeStore();
  const localSituation = useLocalSituation();
  const sourceLabel = localSituation.status === 'ready'
    ? 'Локальный снимок доступен'
    : localSituation.status === 'loading'
      ? 'Локальный снимок загружается'
      : 'Локальный снимок недоступен';

  return <header className="glass-surface-subtle fixed left-[var(--active-sidebar-width)] right-0 top-0 z-30 flex h-[var(--header-height)] items-center justify-between rounded-none border-x-0 border-t-0 px-5 md:px-8">
    <nav aria-label="Навигационная цепочка" className="flex items-center gap-2 text-[13px]"><span className="font-heading font-semibold tracking-[0.02em]">ФОРПОСТ</span><ChevronRight size={14} aria-hidden="true" className="text-[var(--color-text-dim)]" /><span className="text-[var(--color-text-muted)]">{getPageName(pathname)}</span></nav>
    <div className="flex items-center gap-3"><span className="hidden items-center gap-2 rounded-[6px] border border-[var(--color-border)] bg-[var(--color-panel-2)] px-3 py-1.5 text-[11px] text-[var(--color-text-muted)] md:inline-flex"><BrainCircuit size={14} className="text-[var(--color-warning)]" aria-hidden="true" />ML-модель: недоступна</span><span className="hidden text-[11px] text-[var(--color-text-dim)] lg:inline">{sourceLabel}</span><Button variant="ghost" size="sm" onClick={toggleTheme} aria-label={theme === 'dark' ? 'Включить светлую тему' : 'Включить тёмную тему'}>{theme === 'dark' ? <Sun size={17} aria-hidden="true" /> : <Moon size={17} aria-hidden="true" />}</Button></div>
  </header>;
}
