import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AppShell } from './AppShell';

vi.mock('./Header', () => ({ Header: () => <header>Шапка</header> }));
vi.mock('./Sidebar', () => ({ Sidebar: () => <nav>Навигация</nav> }));
vi.mock('./TimelinePlayback', () => ({ TimelinePlayback: () => <footer>Шкала</footer> }));
vi.mock('@/data/LocalSituationProvider', () => ({
  LocalSituationProvider: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock('@/stores/themeStore', () => ({
  useThemeStore: (selector: (state: { theme: 'dark'; sidebarCollapsed: false }) => unknown) => selector({ theme: 'dark', sidebarCollapsed: false }),
}));

describe('AppShell', () => {
  it('переводит клавиатурный фокус к основному содержимому', () => {
    render(<AppShell><h1>Обзор</h1></AppShell>);

    const main = screen.getByRole('main');
    const skipLink = screen.getByRole('link', { name: 'К основному содержимому' });
    expect(skipLink).toHaveAttribute('href', '#main-content');
    expect(main).toHaveAttribute('id', 'main-content');
    expect(main).toHaveAttribute('tabindex', '-1');

    fireEvent.click(skipLink);
    expect(main).toHaveFocus();
  });
});
