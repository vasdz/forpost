import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ForecastFactPanel } from './ForecastFactPanel';

const client = vi.hoisted(() => ({ fetchForecastFact: vi.fn() }));
vi.mock('@/data/forecastFactClient', () => client);

const evidence = {
  formatVersion: 1 as const, task: 'sensor_failure' as const, version: 'v12', evidenceTier: 'proxy' as const,
  sourceSplit: 'final_test' as const, createdAt: '2026-09-21T10:05:00Z', evaluationReportSha256: 'a'.repeat(64), threshold: 0.5,
  metrics: { precision: 0.5, recall: 0.5, f1: 0.5, prAuc: 5 / 6 },
  rows: [
    { id: 'ff_0000000000000001', predictionAt: '2026-08-01T00:00:00Z', deadline: '2026-08-02T00:00:00Z', probability: 0.9, observedOutcome: true, confusion: 'TP' as const, sensorType: 'smoke' as const, leadTimeHours: 24 },
    { id: 'ff_0000000000000002', predictionAt: '2026-08-02T00:00:00Z', deadline: '2026-08-03T00:00:00Z', probability: 0.8, observedOutcome: false, confusion: 'FP' as const, sensorType: 'smoke' as const, leadTimeHours: 24 },
    { id: 'ff_0000000000000003', predictionAt: '2026-08-03T00:00:00Z', deadline: '2026-08-04T00:00:00Z', probability: 0.4, observedOutcome: true, confusion: 'FN' as const, sensorType: 'temperature' as const, leadTimeHours: 24 },
    { id: 'ff_0000000000000004', predictionAt: '2026-08-04T00:00:00Z', deadline: '2026-08-05T00:00:00Z', probability: 0.1, observedOutcome: false, confusion: 'TN' as const, sensorType: 'temperature' as const, leadTimeHours: 24 },
  ],
  calibrationCurve: [{ meanProbability: 0.25, observedRate: 0.5, count: 2 }, { meanProbability: 0.85, observedRate: 0.5, count: 2 }],
  liftCurve: [{ topFraction: 0.25, precision: 1, lift: 2 }, { topFraction: 1, precision: 0.5, lift: 1 }],
};

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe('ForecastFactPanel', () => {
  it('явно объясняет недоступность при отклонённом релизе без вымышленных строк', async () => {
    client.fetchForecastFact.mockResolvedValue({ status: 'unavailable' });
    render(<ForecastFactPanel />);
    expect(await screen.findByRole('heading', { name: 'Прогноз против факта недоступен' })).toBeInTheDocument();
    expect(screen.queryByRole('table', { name: 'Пары прогноз и факт' })).not.toBeInTheDocument();
  });

  it('показывает метрики, TP/FP/FN/TN, графики и фильтры опубликованного evidence', async () => {
    client.fetchForecastFact.mockResolvedValue({ status: 'ready', evidence });
    render(<ForecastFactPanel />);

    const table = await screen.findByRole('table', { name: 'Пары прогноз и факт' });
    expect(within(table).getByText('TP')).toBeInTheDocument();
    expect(within(table).getByText('FP')).toBeInTheDocument();
    expect(within(table).getByText('FN')).toBeInTheDocument();
    expect(within(table).getByText('TN')).toBeInTheDocument();
    expect(screen.getByText('PR-AUC')).toBeInTheDocument();
    expect(screen.getByRole('figure', { name: 'Калибровка вероятностей' })).toBeInTheDocument();
    expect(screen.getByRole('figure', { name: 'Lift и top-K' })).toBeInTheDocument();

    fireEvent.change(screen.getByRole('combobox', { name: 'Тип датчика' }), { target: { value: 'smoke' } });
    expect(within(table).queryByText('temperature')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Начало периода'), { target: { value: '2026-08-02' } });
    expect(within(table).queryByText('ff_0000000000000001')).not.toBeInTheDocument();
  });
});

