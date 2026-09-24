import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ModelQualityPanel } from './ModelQualityPanel';

const modelEvaluation = vi.hoisted(() => ({ fetchModelEvaluation: vi.fn() }));
vi.mock('@/data/modelEvaluationClient', () => modelEvaluation);

const publishedReport = {
  formatVersion: 2 as const,
  task: 'sensor_failure' as const,
  version: 'v12',
  status: 'published' as const,
  evidenceTier: 'proxy' as const,
  labelStrategy: 'cadence_adjusted_silence_horizon_proxy_v2' as const,
  taskSemantics: 'risk_of_unexpected_telemetry_silence_within_horizon' as const,
  featureSchemaVersion: '6' as const,
  configSha256: 'a'.repeat(64),
  libraryVersions: { numpy: '2.3.3', pandas: '2.3.3', 'scikit-learn': '1.7.2', skops: '0.13.0', catboost: '1.2.8', lightgbm: '4.6.0' },
  rollingFolds: [1, 2, 3].map((index) => ({
    index, trainRows: 80 + index * 20, calibrationRows: 20, validationRows: index === 1 ? 14 : 13,
    threshold: 0.6,
    metrics: { precision: 0.8, recall: 0.7, f1: 0.75, prAuc: 0.81, rocAuc: 0.82, brierScore: 0.14, expectedCalibrationError: 0.06, alertRate: 0.16 },
  })),
  operatingProfiles: {
    highPrecision: { threshold: 0.72, precision: 0.88, recall: 0.55, alertRate: 0.1 },
    balanced: { threshold: 0.6, precision: 0.8, recall: 0.7, alertRate: 0.16 },
    highRecall: { threshold: 0.42, precision: 0.72, recall: 0.86, alertRate: 0.25 },
  },
  validationConfidenceIntervals: Object.fromEntries(
    ['precision', 'recall', 'f1', 'prAuc', 'rocAuc', 'brierScore', 'expectedCalibrationError', 'alertRate']
      .map((key) => [key, { lower: 0.6, upper: 0.9, level: 0.95 as const, method: 'student_t_across_rolling_folds' as const }]),
  ) as never,
  horizonHours: 48,
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
    expect(screen.getByText('Горизонт оценки')).toBeInTheDocument();
    expect(screen.getByText('48 ч')).toBeInTheDocument();
    expect(screen.getByText('120')).toBeInTheDocument();
    expect(screen.getByText(/отчёт об оценке не является прогнозом/i)).toBeInTheDocument();
    expect(screen.getByRole('figure', { name: 'Сравнение качества модели' })).toBeInTheDocument();
    const profileSelect = screen.getByRole('combobox', { name: 'Операционный профиль' });
    expect(profileSelect).toHaveValue('balanced');
    expect(screen.getByText(/16,0\s*%/)).toBeInTheDocument();
    fireEvent.change(profileSelect, { target: { value: 'highRecall' } });
    expect(screen.getByText(/25,0\s*%/)).toBeInTheDocument();
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
