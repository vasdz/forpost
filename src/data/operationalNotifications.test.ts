import { describe, expect, it } from 'vitest';
import type { Prediction } from './predictionsClient';
import { buildOperationalNotifications, predictionIncidentId } from './operationalNotifications';

function prediction(overrides: Partial<Prediction>): Prediction {
  return {
    id: 'prediction-1', entityType: 'sensor', entityId: 'channel-1',
    predictionType: 'sensor_failure', probability: 0.82, anomalyScore: null,
    evidenceTier: 'proxy', calibrated: true, provenance: 'derived', confidence: null,
    modelMetrics: { precision: 0.8, recall: 0.7, f1: 0.75, prAuc: 0.81, brierScore: 0.13 },
    qualityStatus: 'passed', limitations: ['Прокси-метка'],
    predictedAt: '2026-09-24T09:00:00Z', horizonHours: 24, modelVersion: 'v7',
    factors: [{ factor: 'silence', weight: 1, description: 'Длительность тишины' }],
    recommendedAction: 'Проверить датчик', priority: 'high', status: 'new',
    ...overrides,
  };
}

describe('buildOperationalNotifications', () => {
  it('оставляет только проверяемые вероятностные прогнозы и сортирует по приоритету и времени', () => {
    const notifications = buildOperationalNotifications([
      prediction({ id: 'old-high', priority: 'high', predictedAt: '2026-09-24T08:00:00Z' }),
      prediction({ id: 'critical', priority: 'critical', predictedAt: '2026-09-24T07:00:00Z' }),
      prediction({ id: 'new-high', priority: 'high', predictedAt: '2026-09-24T10:00:00Z' }),
      prediction({ id: 'limited', qualityStatus: 'limited' }),
      prediction({ id: 'rejected', status: 'rejected' }),
      prediction({ id: 'resolved', status: 'resolved' }),
      prediction({ id: 'expired', predictedAt: '2026-09-22T09:00:00Z', horizonHours: 24 }),
      prediction({ id: 'scenario', evidenceTier: 'scenario', probability: null, calibrated: false, modelMetrics: null, provenance: 'simulated' }),
    ], Date.parse('2026-09-24T11:00:00Z'));

    expect(notifications.map(({ id }) => id)).toEqual(['critical', 'new-high', 'old-high']);
  });

  it('строит стабильный канонический incident id без раскрытия исходной строки', async () => {
    await expect(predictionIncidentId('prediction-1')).resolves.toMatch(/^[a-f0-9]{64}$/);
    await expect(predictionIncidentId('prediction-1')).resolves.toBe(await predictionIncidentId('prediction-1'));
    await expect(predictionIncidentId('prediction-2')).resolves.not.toBe(await predictionIncidentId('prediction-1'));
  });
});
