'use client';

import type { LucideIcon } from 'lucide-react';
import { Activity, Building2, ClipboardList, FileStack, Flame, LayoutDashboard, Menu, Settings, ShieldAlert, Wrench } from 'lucide-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Button } from '@/components/ui/Button';
import { Tooltip } from '@/components/ui/Tooltip';
import { cn } from '@/lib/utils';
import { useThemeStore } from '@/stores/themeStore';

type NavigationItem = { href: string; label: string; icon: LucideIcon };
const navigation: NavigationItem[] = [
  { href: '/', label: 'Обзор', icon: LayoutDashboard }, { href: '/sensor-failure', label: 'Отказ датчика', icon: Activity }, { href: '/fire-risk', label: 'Пожарный риск', icon: Flame }, { href: '/unauthorized-access', label: 'Несанкционированный доступ', icon: ShieldAlert }, { href: '/infrastructure-wear', label: 'Износ инфраструктуры', icon: Building2 }, { href: '/registries', label: 'Реестры', icon: FileStack }, { href: '/journals', label: 'Журналы', icon: ClipboardList }, { href: '/applications', label: 'Заявки', icon: Wrench }, { href: '/design-system', label: 'Настройки', icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const { sidebarCollapsed, toggleSidebar } = useThemeStore();
  return <aside className={cn('surface-subtle sticky top-0 z-40 flex h-screen shrink-0 flex-col rounded-none border-y-0 border-l-0 transition-[width] duration-200 ease-out', 'w-[var(--active-sidebar-width)]')}>
    <div className="flex h-[var(--header-height)] items-center justify-between border-b border-[var(--color-border)] px-4"><span className={cn('font-heading text-[15px] font-bold tracking-[0.18em]', sidebarCollapsed ? 'sr-only' : 'max-md:sr-only')}>ФОРПОСТ</span><Button variant="ghost" size="sm" onClick={toggleSidebar} aria-label={sidebarCollapsed ? 'Развернуть боковое меню' : 'Свернуть боковое меню'}><Menu size={17} aria-hidden="true" /></Button></div>
    <nav aria-label="Основная навигация" className="flex-1 space-y-1.5 p-3 pt-5">{navigation.map((item) => {
      const active = item.href === '/' ? pathname === '/' : pathname === item.href.split('?')[0];
      const Icon = item.icon;
      const link = <Link href={item.href} aria-label={item.label} aria-current={active ? 'page' : undefined} className={cn('flex h-10 items-center gap-3 rounded-[4px] border-l-2 px-3 text-[13px] transition-colors', active ? 'border-l-[var(--color-data)] bg-[var(--color-panel-2)] text-[var(--color-text)]' : 'border-l-transparent text-[var(--color-text-muted)] hover:bg-[var(--color-panel-2)] hover:text-[var(--color-text)]')}><Icon size={17} strokeWidth={1.7} aria-hidden="true" /><span className={cn(sidebarCollapsed ? 'sr-only' : 'max-md:sr-only')}>{item.label}</span></Link>;
      return sidebarCollapsed ? <Tooltip key={item.href} content={item.label}>{link}</Tooltip> : <div key={item.href}>{link}</div>;
    })}</nav>
    <div className="border-t border-[var(--color-border)] p-4 text-[10px] uppercase tracking-[0.1em] text-[var(--color-text-dim)]"><Building2 size={15} strokeWidth={1.7} aria-hidden="true" className="mb-2" /><span className={cn(sidebarCollapsed ? 'sr-only' : 'max-md:sr-only')}>АО «Москоллектор»<br />Ситуационный центр</span></div>
  </aside>;
}
