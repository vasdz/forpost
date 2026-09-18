import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, expect, it } from 'vitest';

import App from './App';

describe('legacy client', () => {
  it('does not render a dashboard that could present generated results as real', () => {
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
      true;
    const container = document.createElement('div');
    const root = createRoot(container);

    act(() => {
      root.render(<App />);
    });

    expect(container.textContent).toContain('Legacy-клиент выведен из эксплуатации');
    expect(container.textContent).toContain(
      'Интеграция с реальными данными и обученной моделью пока недоступна.',
    );

    act(() => {
      root.unmount();
    });
  });
});
