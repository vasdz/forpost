import { describe, expect, it, vi } from 'vitest';
import { fetchForecastFact } from './forecastFactClient';

const validEvidence = {
  format_version: 1,
  task: 'sensor_failure',
  version: 'v12',
  evidence_tier: 'proxy',
  source_split: 'final_test',
  created_at: '2026-09-21T10:05:00Z',
  evaluation_report_sha256: 'a'.repeat(64),
  threshold: 0.5,
  metrics: { precision: 0.5, recall: 0.5, f1: 0.5, pr_auc: 5 / 6 },
  rows: [
    { id: 'ff_0000000000000001', prediction_at: '2026-08-01T00:00:00Z', deadline: '2026-08-02T00:00:00Z', probability: 0.9, observed_outcome: true, confusion: 'TP', sensor_type: 'smoke', lead_time_hours: 24 },
    { id: 'ff_0000000000000002', prediction_at: '2026-08-02T00:00:00Z', deadline: '2026-08-03T00:00:00Z', probability: 0.8, observed_outcome: false, confusion: 'FP', sensor_type: 'smoke', lead_time_hours: 24 },
    { id: 'ff_0000000000000003', prediction_at: '2026-08-03T00:00:00Z', deadline: '2026-08-04T00:00:00Z', probability: 0.4, observed_outcome: true, confusion: 'FN', sensor_type: 'temperature', lead_time_hours: 24 },
    { id: 'ff_0000000000000004', prediction_at: '2026-08-04T00:00:00Z', deadline: '2026-08-05T00:00:00Z', probability: 0.1, observed_outcome: false, confusion: 'TN', sensor_type: 'temperature', lead_time_hours: 24 },
  ],
  calibration_curve: [
    { mean_probability: 0.25, observed_rate: 0.5, count: 2 },
    { mean_probability: 0.85, observed_rate: 0.5, count: 2 },
  ],
  lift_curve: [
    { top_fraction: 0.25, precision: 1, lift: 2 },
    { top_fraction: 0.5, precision: 0.5, lift: 1 },
    { top_fraction: 1, precision: 0.5, lift: 1 },
  ],
};

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { 'content-type': 'application/json' } });
}

describe('fetchForecastFact', () => {
  it('разбирает строгий evidence-контракт и переводит имена полей', async () => {
    const fetcher = vi.fn(async () => jsonResponse(validEvidence));

    await expect(fetchForecastFact(fetcher as typeof fetch)).resolves.toMatchObject({
      status: 'ready',
      evidence: {
        version: 'v12', sourceSplit: 'final_test', threshold: 0.5,
        metrics: { precision: 0.5, recall: 0.5, f1: 0.5, prAuc: 5 / 6 },
        rows: [expect.objectContaining({ id: 'ff_0000000000000001', observedOutcome: true, sensorType: 'smoke' })],
        liftCurve: [expect.objectContaining({ topFraction: 0.25, lift: 2 })],
      },
    });
  });

  it('различает отсутствие сессии и недоступность опубликованного evidence', async () => {
    expect(await fetchForecastFact(async () => jsonResponse({}, 401))).toEqual({ status: 'unauthenticated' });
    expect(await fetchForecastFact(async () => jsonResponse({}, 503))).toEqual({ status: 'unavailable' });
  });

  it.each([
    { ...validEvidence, unexpected: true },
    { ...validEvidence, rows: [{ ...validEvidence.rows[0], id: 'raw-sensor-id' }] },
    { ...validEvidence, rows: [{ ...validEvidence.rows[0], probability: 1.2 }] },
    { ...validEvidence, lift_curve: [{ top_fraction: 1, precision: 1, lift: Number.NaN }] },
  ])('отклоняет повреждённый или расширенный контракт %#', async (payload) => {
    expect(await fetchForecastFact(async () => jsonResponse(payload))).toEqual({ status: 'unavailable' });
  });
});

