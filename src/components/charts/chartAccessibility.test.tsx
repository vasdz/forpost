import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DonutChart } from './DonutChart';
import { HeatMap } from './HeatMap';
import { TimeSeriesChart } from './TimeSeriesChart';
vi.mock('echarts-for-react', () => ({ default: () => null }));
afterEach(cleanup);

describe('Табличные альтернативы графиков', () => {
  it('передаёт количество и долю каждого сегмента', () => {
    render(<DonutChart label="Статусы" items={[{ name: 'Штатно', value: 3, color: '#10B981' }, { name: 'Критично', value: 1, color: '#D9342B' }]} />);
    const table = screen.getByRole('table', { name: 'Статусы', hidden: true });
    expect(within(table).getByText('75%')).toBeInTheDocument();
    expect(within(table).getByText('Критично')).toBeInTheDocument();
  });
  it('сохраняет координаты и значение ячейки матрицы', () => {
    render(<HeatMap label="События" days={['Пн']} hours={['04']} data={[[0, 0, 7]]} />);
    const table = screen.getByRole('table', { name: 'События', hidden: true });
    expect(within(table).getByText('Пн')).toBeInTheDocument();
    expect(within(table).getByText('7')).toBeInTheDocument();
  });
  it('не читает произвольные свойства массива для некорректных координат', () => {
    render(<HeatMap label="События" days={['Пн']} hours={['04']} data={[[99, -1, 7]]} />);
    const table = screen.getByRole('table', { name: 'События', hidden: true });
    expect(within(table).getAllByText('—')).toHaveLength(2);
  });
  it('передаёт единицы и границы доверительного интервала', () => {
    render(<TimeSeriesChart now="2026-09-14T18:00:00Z" unit="°C" history={[]} forecast={[{ at: '2026-09-15T18:00:00Z', value: 30, lower: 25, upper: 35 }]} />);
    const table = screen.getByRole('table', { name: 'График истории и прогноза', hidden: true });
    expect(within(table).getByText('30 °C')).toBeInTheDocument();
    expect(within(table).getByText('25–35 °C')).toBeInTheDocument();
  });
});
