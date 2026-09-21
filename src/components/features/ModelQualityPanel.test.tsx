import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ModelQualityPanel } from './ModelQualityPanel';

const modelEvaluation = vi.hoisted(() => ({ fetchModelEvaluation: vi.fn() }));
vi.mock('@/data/modelEvaluationClient', () => modelEvaluation);

const publishedReport = {
  formatVersion: 1 as const,
  task: 'sensor_failure' as const,
  version: 'v12',
  status: 'published' as const,
  evidenceTier: 'proxy' as const,
  labelStrategy: 'silence_horizon_proxy' as const,
  createdAt: '2026-09-21T12:00:00+03:00',
  reasonCode: null,
  qualityThresholds: {
    minimumPrecision: 0.71, minimumRecall: 0.51, maximumAlertRate: 0.2,
    maximumExpectedCalibrationError: 0.1, maximumBrierScore: 0.2, minimumBaselinePrAucDelta: 0.03,
  },
  splitSizes: { fit: 120, calibration: 40, validation: 40, test: 40 },
  baselineValidationPrAuc: 0.4,
  validationMetrics: {
    precision: 0.8, recall: 0.7, f1: 0.75, prAuc: 0.81, rocAuc: 0.82,
    brierScore: 0.14, expectedCalibrationError: 0.06, alertRate: 0.16,
  },
  testMetrics: {
    precision: 0.79, recall: 0.69, f1: 0.73, prAuc: 0.8, rocAuc: 0.81,
    brierScore: 0.15, expectedCalibrationError: 0.07, alertRate: 0.17,
  },
  threshold: 0.6,
  championName: 'extra_trees_isotonic' as const,
};

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe('ModelQualityPanel', () => {
  it('объявляет загрузку и не показывает метрики, пока отчёт не получен', () => {
    modelEvaluation.fetchModelEvaluation.mockImplementation(() => new Promise(() => undefined));

    render(<ModelQualityPanel />);

    expect(screen.getByRole('status')).toHaveTextContent('Загрузка отчёта об оценке модели…');
    expect(screen.queryByRole('table', { name: 'Метрики качества модели' })).not.toBeInTheDocument();
  });

  it('показывает в отдельных столбцах метрики валидации и теста, пороги и размеры выборок', async () => {
    modelEvaluation.fetchModelEvaluation.mockResolvedValue({ status: 'ready', evaluation: publishedReport });

    render(<ModelQualityPanel />);

    const table = await screen.findByRole('table', { name: 'Метрики качества модели' });
    expect(within(table).getByRole('columnheader', { name: 'Валидация' })).toBeInTheDocument();
    expect(within(table).getByRole('columnheader', { name: 'Тест' })).toBeInTheDocument();
    expect(within(table).getAllByText('0,800')).toHaveLength(2);
    expect(within(table).getByText('0,790')).toBeInTheDocument();
    expect(screen.getByText('Минимальная точность')).toBeInTheDocument();
    expect(screen.getByText('Обучение')).toBeInTheDocument();
    expect(screen.getByText('120')).toBeInTheDocument();
    expect(screen.getByText(/отчёт об оценке не является прогнозом/i)).toBeInTheDocument();
  });

  it('обозначает отклонённый отчёт как заблокированный релиз без прогноза и победителя', async () => {
    modelEvaluation.fetchModelEvaluation.mockResolvedValue({
      status: 'ready',
      evaluation: {
        ...publishedReport,
        status: 'rejected',
        reasonCode: 'validation_rejected',
        validationMetrics: null,
        testMetrics: null,
        threshold: null,
        championName: null,
      },
    });

    render(<ModelQualityPanel />);

    expect(await screen.findByText('Релиз заблокирован')).toBeInTheDocument();
    expect(screen.getAllByText(/не подтверждает доступность прогноза/i)).toHaveLength(2);
    expect(screen.getByText('Валидация отклонена')).toBeInTheDocument();
    expect(screen.getAllByText('—')).toHaveLength(16);
    expect(screen.queryByText(/активных прогнозов нет/i)).not.toBeInTheDocument();
  });

  it('сообщает о недоступности отчёта без сохранения устаревших метрик', async () => {
    modelEvaluation.fetchModelEvaluation.mockResolvedValue({ status: 'unavailable' });

    render(<ModelQualityPanel />);

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Отчёт об оценке недоступен' })).toBeInTheDocument());
    expect(screen.getByText(/не загружен или не прошёл проверку контракта/i)).toBeInTheDocument();
    expect(screen.queryByRole('table', { name: 'Метрики качества модели' })).not.toBeInTheDocument();
  });
});
