import { describe, expect, it, vi } from 'vitest';
import { fetchModelEvaluation } from './modelEvaluationClient';

const validReport = {
  format_version: 1,
  task: 'sensor_failure',
  version: 'v12',
  status: 'published',
  evidence_tier: 'proxy',
  label_strategy: 'silence_horizon_proxy',
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
  it('разбирает полный строго заданный контракт отчёта', async () => {
    const fetcher = vi.fn(async () => jsonResponse(validReport));

    await expect(fetchModelEvaluation(fetcher as typeof fetch)).resolves.toEqual({
      status: 'ready',
      evaluation: {
        formatVersion: 1,
        task: 'sensor_failure',
        version: 'v12',
        status: 'published',
        evidenceTier: 'proxy',
        labelStrategy: 'silence_horizon_proxy',
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
