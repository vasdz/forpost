'use client';

import { useEffect, type CSSProperties, type ReactNode } from 'react';
import { Header } from './Header';
import { Sidebar } from './Sidebar';
import { TimelinePlayback } from './TimelinePlayback';
import { LocalSituationProvider } from '@/data/LocalSituationProvider';
import { useThemeStore } from '@/stores/themeStore';

export function AppShell({ children }: { children: ReactNode }) {
  const theme = useThemeStore((state) => state.theme);
  const sidebarCollapsed = useThemeStore((state) => state.sidebarCollapsed);
  useEffect(() => {
    document.documentElement.classList.toggle('theme-dark', theme === 'dark');
    document.documentElement.classList.toggle('theme-light', theme === 'light');
  }, [theme]);
  return <LocalSituationProvider><div style={{ '--active-sidebar-width': sidebarCollapsed ? '64px' : '240px' } as CSSProperties} className="app-shell app-canvas flex min-h-screen"><Sidebar /><div className="min-w-0 flex-1 pb-[var(--timeline-height)] pt-[var(--header-height)]"><Header /><main id="main-content" className="mx-auto min-h-[calc(100vh-var(--header-height)-var(--timeline-height))] w-full max-w-[1680px] p-4 md:p-6 xl:p-8">{children}</main><TimelinePlayback /></div></div></LocalSituationProvider>;
}
