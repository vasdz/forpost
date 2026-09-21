import { describe, expect, it, vi } from 'vitest';
import { fetchPredictionFeed, fetchPredictions } from './predictionsClient';

const validPrediction = {
  id: 'prediction-1', entity_type: 'sensor', entity_id: 'channel-1',
  prediction_type: 'sensor_failure', probability: 0.82, anomaly_score: null,
  evidence_tier: 'proxy', calibrated: true, provenance: 'derived',
  confidence: { lower: 0.75, upper: 0.9 },
  model_metrics: { precision: 0.8, recall: 0.7, f1: 0.75, pr_auc: 0.81, brier_score: 0.13 },
  quality_status: 'passed', limitations: ['Прокси-метка'], predicted_at: '2026-09-18T12:00:00Z',
  horizon_hours: 24, model_version: 'v1',
  factors: [{ factor: 'hours_since_last_event', weight: 1, description: 'Permutation importance' }],
  recommended_action: 'Проверить датчик', priority: 'high', status: 'new',
};

function response(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

describe('fetchPredictions', () => {
  it('parses the strict backend contract', async () => {
    const fetcher = vi.fn(async () => response({
      predictions: [validPrediction], available_types: ['sensor_failure'],
    }));

    const result = await fetchPredictions(fetcher as typeof fetch);

    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({ probability: 0.82, evidenceTier: 'proxy', modelVersion: 'v1' });
  });

  it('drops a probability that is not calibrated', async () => {
    const fetcher = vi.fn(async () => response({
      predictions: [{ ...validPrediction, calibrated: false }],
      available_types: ['sensor_failure'],
    }));

    await expect(fetchPredictions(fetcher as typeof fetch)).resolves.toEqual([]);
  });

  it('drops scenario output presented as a probability', async () => {
    const fetcher = vi.fn(async () => response({
      predictions: [{
        ...validPrediction,
        evidence_tier: 'scenario',
        provenance: 'simulated',
      }],
      available_types: ['sensor_failure'],
    }));

    await expect(fetchPredictions(fetcher as typeof fetch)).resolves.toEqual([]);
  });

  it('rejects enum values disguised as arrays', async () => {
    const fetcher = vi.fn(async () => response({
      predictions: [{ ...validPrediction, evidence_tier: ['proxy'] }],
      available_types: ['sensor_failure'],
    }));

    await expect(fetchPredictions(fetcher as typeof fetch)).resolves.toEqual([]);
  });

  it('accepts an honest probability without a fabricated confidence interval', async () => {
    const fetcher = vi.fn(async () => response({
      predictions: [{ ...validPrediction, confidence: null }],
      available_types: ['sensor_failure'],
    }));

    const result = await fetchPredictions(fetcher as typeof fetch);

    expect(result[0]?.confidence).toBeNull();
  });

  it('fails closed on unavailable or malformed API', async () => {
    const failed = vi.fn(async () => response({ status: 'pending' }, 503));
    const malformed = vi.fn(async () => response({ predictions: 'nope' }));

    await expect(fetchPredictions(failed as typeof fetch)).resolves.toEqual([]);
    await expect(fetchPredictions(malformed as typeof fetch)).resolves.toEqual([]);
  });

  it('distinguishes a ready model without active alerts from an unavailable model', async () => {
    const ready = vi.fn(async () => response({
      predictions: [], available_types: ['sensor_failure'],
    }));
    const unavailable = vi.fn(async () => response({ status: 'pending' }, 503));

    await expect(fetchPredictionFeed(ready as typeof fetch)).resolves.toEqual({
      status: 'ready', availableTypes: ['sensor_failure'], predictions: [],
    });
    await expect(fetchPredictionFeed(unavailable as typeof fetch)).resolves.toEqual({
      status: 'unavailable', availableTypes: [], predictions: [],
    });
  });
});
