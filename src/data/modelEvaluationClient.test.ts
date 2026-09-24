import { describe, expect, it, vi } from 'vitest';
import { fetchModelEvaluation } from './modelEvaluationClient';

const validReport = {
  format_version: 2,
  task: 'sensor_failure',
  version: 'v12',
  status: 'published',
  evidence_tier: 'proxy',
  label_strategy: 'cadence_adjusted_silence_horizon_proxy_v2',
  task_semantics: 'risk_of_unexpected_telemetry_silence_within_horizon',
  feature_schema_version: '6',
  config_sha256: 'a'.repeat(64),
  library_versions: {
    numpy: '2.3.3', pandas: '2.3.3', 'scikit-learn': '1.7.2',
    skops: '0.13.0', catboost: '1.2.8', lightgbm: '4.6.0',
  },
  rolling_folds: [
    { index: 1, train_rows: 80, calibration_rows: 20, validation_rows: 14, threshold: 0.6,
      metrics: { precision: 0.78, recall: 0.68, f1: 0.73, pr_auc: 0.8, roc_auc: 0.81, brier_score: 0.15, expected_calibration_error: 0.07, alert_rate: 0.17 } },
    { index: 2, train_rows: 100, calibration_rows: 20, validation_rows: 13, threshold: 0.6,
      metrics: { precision: 0.8, recall: 0.7, f1: 0.75, pr_auc: 0.81, roc_auc: 0.82, brier_score: 0.14, expected_calibration_error: 0.06, alert_rate: 0.16 } },
    { index: 3, train_rows: 120, calibration_rows: 20, validation_rows: 13, threshold: 0.6,
      metrics: { precision: 0.82, recall: 0.72, f1: 0.77, pr_auc: 0.82, roc_auc: 0.83, brier_score: 0.13, expected_calibration_error: 0.05, alert_rate: 0.15 } },
  ],
  operating_profiles: {
    high_precision: { threshold: 0.72, precision: 0.88, recall: 0.55, alert_rate: 0.1 },
    balanced: { threshold: 0.6, precision: 0.8, recall: 0.7, alert_rate: 0.16 },
    high_recall: { threshold: 0.42, precision: 0.72, recall: 0.86, alert_rate: 0.25 },
  },
  validation_confidence_intervals: Object.fromEntries(
    ['precision', 'recall', 'f1', 'pr_auc', 'roc_auc', 'brier_score', 'expected_calibration_error', 'alert_rate']
      .map((key) => [key, { lower: 0.6, upper: 0.9, level: 0.95, method: 'student_t_across_rolling_folds' }]),
  ),
  horizon_hours: 48,
  created_at: '2026-09-21T12:00:00+03:00',
  reason_code: null,
  quality_thresholds: {
    minimum_precision: 0.71,
    minimum_recall: 0.51,
    maximum_alert_rate: 0.2,
    maximum_expected_calibration_error: 0.1,
    maximum_brier_score: 0.2,
    minimum_baseline_pr_auc_delta: 0.03,
  },
  split_sizes: { fit: 120, calibration: 40, validation: 40, test: 40 },
  baseline_validation_pr_auc: 0.4,
  validation_metrics: {
    precision: 0.8,
    recall: 0.7,
    f1: 0.75,
    pr_auc: 0.81,
    roc_auc: 0.82,
    brier_score: 0.14,
    expected_calibration_error: 0.06,
    alert_rate: 0.16,
  },
  test_metrics: {
    precision: 0.79,
    recall: 0.69,
    f1: 0.73,
    pr_auc: 0.8,
    roc_auc: 0.81,
    brier_score: 0.15,
    expected_calibration_error: 0.07,
    alert_rate: 0.17,
  },
  threshold: 0.6,
  champion_name: 'extra_trees_isotonic',
};

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

describe('fetchModelEvaluation', () => {
  it('отличает отсутствие пользовательской сессии 401 от недоступности 503', async () => {
    expect(await fetchModelEvaluation(async () => jsonResponse({}, 401))).toEqual({ status: 'unauthenticated' });
    expect(await fetchModelEvaluation(async () => jsonResponse({}, 503))).toEqual({ status: 'unavailable' });
  });
  it.each([0, -1, 8761, 1.5, '24', true, null, undefined])('отклоняет опубликованный горизонт %s', async (horizon) => {
    const fetcher = vi.fn(async () => jsonResponse({ ...validReport, horizon_hours: horizon }));
    expect(await fetchModelEvaluation(fetcher)).toEqual({ status: 'unavailable' });
  });

  it.each([null, 1, 48, 8760])('принимает nullable горизонт rejected-отчёта %s', async (horizon) => {
    const fetcher = vi.fn(async () => jsonResponse({ ...validReport, status: 'rejected',
      reason_code: 'configuration_invalid', test_metrics: null, horizon_hours: horizon }));
    expect(await fetchModelEvaluation(fetcher)).toMatchObject({
      status: 'ready', evaluation: { horizonHours: horizon, testMetrics: null },
    });
  });
  it('разбирает полный строго заданный контракт отчёта', async () => {
    const fetcher = vi.fn(async () => jsonResponse(validReport));

    await expect(fetchModelEvaluation(fetcher as typeof fetch)).resolves.toEqual({
      status: 'ready',
      evaluation: {
        formatVersion: 2,
        task: 'sensor_failure',
        version: 'v12',
        status: 'published',
        evidenceTier: 'proxy',
        labelStrategy: 'cadence_adjusted_silence_horizon_proxy_v2',
        taskSemantics: 'risk_of_unexpected_telemetry_silence_within_horizon',
        featureSchemaVersion: '6',
        configSha256: 'a'.repeat(64),
        libraryVersions: expect.objectContaining({ numpy: '2.3.3', lightgbm: '4.6.0' }),
        rollingFolds: expect.arrayContaining([expect.objectContaining({ index: 1, validationRows: 14 })]),
        operatingProfiles: expect.objectContaining({
          highPrecision: { threshold: 0.72, precision: 0.88, recall: 0.55, alertRate: 0.1 },
          balanced: { threshold: 0.6, precision: 0.8, recall: 0.7, alertRate: 0.16 },
        }),
        validationConfidenceIntervals: expect.objectContaining({
          precision: { lower: 0.6, upper: 0.9, level: 0.95, method: 'student_t_across_rolling_folds' },
        }),
        horizonHours: 48,
        createdAt: '2026-09-21T12:00:00+03:00',
        reasonCode: null,
        qualityThresholds: {
          minimumPrecision: 0.71,
          minimumRecall: 0.51,
          maximumAlertRate: 0.2,
          maximumExpectedCalibrationError: 0.1,
          maximumBrierScore: 0.2,
          minimumBaselinePrAucDelta: 0.03,
        },
        splitSizes: { fit: 120, calibration: 40, validation: 40, test: 40 },
        baselineValidationPrAuc: 0.4,
        validationMetrics: expect.objectContaining({ precision: 0.8, prAuc: 0.81 }),
        testMetrics: expect.objectContaining({ precision: 0.79, prAuc: 0.8 }),
        threshold: 0.6,
        championName: 'extra_trees_isotonic',
      },
    });
  });

  it('отклоняет отчёт с лишним ключом или нечисловой метрикой', async () => {
    const extraKey = vi.fn(async () => jsonResponse({ ...validReport, unexpected: true }));
    const invalidMetric = vi.fn(async () => jsonResponse({
      ...validReport,
      validation_metrics: { ...validReport.validation_metrics, precision: '0.8' },
    }));

    await expect(fetchModelEvaluation(extraKey as typeof fetch)).resolves.toEqual({ status: 'unavailable' });
    await expect(fetchModelEvaluation(invalidMetric as typeof fetch)).resolves.toEqual({ status: 'unavailable' });
  });

  it.each([
    { operating_profiles: { ...validReport.operating_profiles, balanced: { ...validReport.operating_profiles.balanced, precision: '0.8' } } },
    { rolling_folds: [{ ...validReport.rolling_folds[0], index: 0 }] },
    { validation_confidence_intervals: { ...validReport.validation_confidence_intervals, precision: { lower: 0.9, upper: 0.6, level: 0.95, method: 'student_t_across_rolling_folds' } } },
    { library_versions: { ...validReport.library_versions, unknown: '1.0.0' } },
  ])('отклоняет повреждённые validation-доказательства %#', async (invalidEvidence) => {
    const fetcher = vi.fn(async () => jsonResponse({ ...validReport, ...invalidEvidence }));
    await expect(fetchModelEvaluation(fetcher as typeof fetch)).resolves.toEqual({ status: 'unavailable' });
  });

  it.each([
    '2026-09-21',
    '2026-09-21T12:00:00',
    '21.09.2026, 12:00:00+03:00',
    '2026-09-21 12:00:00+03:00',
  ])('отклоняет неполный или не-RFC3339 created_at: %s', async (createdAt) => {
    const fetcher = vi.fn(async () => jsonResponse({ ...validReport, created_at: createdAt }));

    await expect(fetchModelEvaluation(fetcher as typeof fetch)).resolves.toEqual({ status: 'unavailable' });
  });

  it.each([
    '2026-02-31T12:00:00Z',
    '2026-04-31T12:00:00Z',
    '2026-13-01T12:00:00Z',
    '2026-09-21T24:00:00Z',
    '2026-09-21T23:60:00Z',
    '2026-09-21T23:59:60Z',
    '2026-09-21T12:00:00+24:00',
    '2026-09-21T12:00:00+03:60',
  ])('отклоняет календарно невозможный created_at: %s', async (createdAt) => {
    const fetcher = vi.fn(async () => jsonResponse({ ...validReport, created_at: createdAt }));

    await expect(fetchModelEvaluation(fetcher as typeof fetch)).resolves.toEqual({ status: 'unavailable' });
  });

  it('принимает високосную дату с дробными секундами', async () => {
    const fetcher = vi.fn(async () => jsonResponse({
      ...validReport,
      created_at: '2024-02-29T23:59:59.123456+03:00',
    }));

    await expect(fetchModelEvaluation(fetcher as typeof fetch)).resolves.toMatchObject({
      status: 'ready', evaluation: { createdAt: '2024-02-29T23:59:59.123456+03:00' },
    });
  });

  it('отклоняет report с нарушенным инвариантом опубликованного доказательства', async () => {
    const fetcher = vi.fn(async () => jsonResponse({
      ...validReport,
      reason_code: 'release_unavailable',
    }));

    await expect(fetchModelEvaluation(fetcher as typeof fetch)).resolves.toEqual({ status: 'unavailable' });
  });

  it('отделяет недоступный отчёт 503 от опубликованного доказательства', async () => {
    const fetcher = vi.fn(async () => jsonResponse({
      status: 'unavailable', reason_code: 'evaluation_unavailable',
    }, 503));

    await expect(fetchModelEvaluation(fetcher as typeof fetch)).resolves.toEqual({ status: 'unavailable' });
  });

  it('принимает отклонённый отчёт без победителя и тестовой выборки', async () => {
    const fetcher = vi.fn(async () => jsonResponse({
      ...validReport,
      status: 'rejected',
      reason_code: 'validation_rejected',
      validation_metrics: null,
      test_metrics: null,
      threshold: null,
      champion_name: null,
    }));

    await expect(fetchModelEvaluation(fetcher as typeof fetch)).resolves.toMatchObject({
      status: 'ready',
      evaluation: {
        status: 'rejected', reasonCode: 'validation_rejected', validationMetrics: null,
        testMetrics: null, threshold: null, championName: null,
      },
    });
  });
});
