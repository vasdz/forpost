import { describe, expect, it } from 'vitest';
import { buildTimeSeriesOption } from './chartOptions';

describe('buildTimeSeriesOption', () => {
  it('показывает текущий момент между измерениями без сдвига прогноза', () => {
    const option = buildTimeSeriesOption({ history: [{ at: '2026-09-14T10:00:00Z', value: 12 }], forecast: [{ at: '2026-09-15T10:00:00Z', value: 18 }], now: '2026-09-14T10:30:00Z', unit: '°C' });
    expect((option.xAxis as { data: string[] }).data).toEqual(['2026-09-14T10:00:00Z', '2026-09-14T10:30:00Z', '2026-09-15T10:00:00Z']);
    expect((option.series as Array<{ data: unknown[] }>).at(-1)?.data).toEqual([null, null, 18]);
  });
  it('строит историю, пунктирный прогноз, вертикаль сейчас и confidence band', () => {
    const option = buildTimeSeriesOption({
      history: [{ at: '2026-09-14T10:00:00.000Z', value: 12 }, { at: '2026-09-14T11:00:00.000Z', value: 14 }],
      forecast: [{ at: '2026-09-14T12:00:00.000Z', value: 18, lower: 15, upper: 21 }],
      now: '2026-09-14T11:00:00.000Z',
      unit: '°C',
    });
    const series = option.series as Array<{ name: string; lineStyle?: { type?: string }; markLine?: unknown }>;
    expect(series.map((item) => item.name)).toContain('История');
    expect(series.find((item) => item.name === 'Прогноз')?.lineStyle?.type).toBe('dashed');
    expect(series.find((item) => item.name === 'История')?.markLine).toBeDefined();
    expect(series.map((item) => item.name)).toContain('Доверительный интервал');
  });

  it('использует семантические токены новой палитры', () => {
    const option = buildTimeSeriesOption({
      history: [{ at: '2026-09-14T10:00:00.000Z', value: 12 }],
      forecast: [{ at: '2026-09-14T11:00:00.000Z', value: 18 }],
      now: '2026-09-14T10:30:00.000Z',
      unit: '°C',
    });
    const series = option.series as Array<{ name: string; lineStyle?: { color?: string } }>;
    expect(series.find((item) => item.name === 'История')?.lineStyle?.color).toBe('var(--color-data)');
    expect(series.find((item) => item.name === 'Прогноз')?.lineStyle?.color).toBe('var(--color-danger)');
  });
});
