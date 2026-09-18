import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LiveIndicator } from './LiveIndicator';
vi.mock('echarts-for-react', () => ({ default: () => null }));
afterEach(cleanup);

describe('LiveIndicator', () => {
  it('показывает текущий показатель числом и компактную динамику вместо gauge', () => {
    render(<LiveIndicator value={55} label="Температура" points={[42, 47, 51, 55]} />);

    expect(screen.getByText('55%')).toBeInTheDocument();
    expect(screen.getByLabelText('Температура')).toBeInTheDocument();
    expect(screen.getByRole('figure', { name: 'Динамика: Температура' })).toBeInTheDocument();
  });
});
