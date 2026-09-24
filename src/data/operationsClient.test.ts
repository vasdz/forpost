import { describe, expect, it, vi } from 'vitest';

import {
  OperationsClientError,
  createPredictionServiceDraft,
  fetchServiceDrafts,
  fetchTopology,
  recordIncidentDecision,
  recordPredictionDecision,
  startDemoSession,
} from './operationsClient';

const INCIDENT_ID = 'a'.repeat(64);

describe('operationsClient', () => {
  it('создаёт demo-сессию и возвращает CSRF только из строгого ответа', async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json({
      active: true,
      profile: 'central-dispatcher',
      csrfToken: 'c'.repeat(43),
      provenance: 'simulated',
    }, { status: 201 }));

    const session = await startDemoSession('central-dispatcher', fetcher);

    expect(session.csrfToken).toHaveLength(43);
    expect(fetcher).toHaveBeenCalledWith('/api/demo-session', expect.objectContaining({
      method: 'POST',
      credentials: 'same-origin',
    }));
  });

  it('не теряет безопасную ошибку сервера при записи решения', async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json(
      { error: 'Причина решения слишком короткая' },
      { status: 422 },
    ));

    await expect(recordIncidentDecision(INCIDENT_ID, {
      status: 'in_review',
      reason: 'коротко',
    }, 'c'.repeat(43), 'decision-command-1', fetcher)).rejects.toMatchObject({
      message: 'Причина решения слишком короткая',
      status: 422,
    });
  });

  it('сохраняет решение по прогнозу только из строгого recorded-ответа', async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json({
      status: 'recorded', prediction_id: 'prediction-1', audit_record_id: 17,
    }, { status: 201 }));

    const result = await recordPredictionDecision('prediction-1', {
      decision: 'confirmed', reason: 'Проверка объекта назначена диспетчером',
    }, 'c'.repeat(43), fetcher);

    expect(result).toEqual({ status: 'recorded', predictionId: 'prediction-1', auditRecordId: 17 });
    expect(fetcher).toHaveBeenCalledWith('/api/predictions/prediction-1/decisions', expect.objectContaining({
      method: 'POST', credentials: 'same-origin',
      headers: expect.objectContaining({ 'X-Forpost-CSRF': 'c'.repeat(43) }),
    }));
  });

  it('отклоняет повреждённое подтверждение решения по прогнозу', async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json({
      status: 'recorded', prediction_id: 'another-prediction', audit_record_id: -1,
    }, { status: 201 }));

    await expect(recordPredictionDecision('prediction-1', {
      decision: 'rejected', reason: 'Данные объекта не подтверждают риск',
    }, 'c'.repeat(43), fetcher)).rejects.toBeInstanceOf(OperationsClientError);
  });

  it('создаёт черновик из прогноза через отдельный защищённый контракт', async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json({
      draftId: 'draft-1', incidentId: INCIDENT_ID, targetId: 'channel-1',
      category: 'prediction_follow_up', priority: 'high',
      recommendedAction: 'Проверить канал связи', dueAt: '2026-09-25T09:00:00Z',
      authorId: 'dispatcher-1', createdAt: '2026-09-24T10:00:00Z', provenance: 'simulated',
    }, { status: 201 }));

    const draft = await createPredictionServiceDraft(
      'prediction-1', 'c'.repeat(43), fetcher,
    );

    expect(draft.draftId).toBe('draft-1');
    expect(fetcher).toHaveBeenCalledWith(
      '/api/predictions/prediction-1/service-request-drafts',
      expect.objectContaining({
        method: 'POST', body: JSON.stringify({}),
        headers: expect.objectContaining({ 'X-Forpost-CSRF': 'c'.repeat(43) }),
      }),
    );
  });

  it('отклоняет черновик без явного simulated provenance', async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json([{
      draftId: 'draft-1',
      incidentId: INCIDENT_ID,
      targetId: 'channel-1',
      category: 'sensor_check',
      priority: 'high',
      recommendedAction: 'Проверить канал связи',
      dueAt: '2026-09-19T12:00:00Z',
      authorId: 'dispatcher-1',
      createdAt: '2026-09-18T12:00:00Z',
    }]));

    await expect(fetchServiceDrafts(fetcher)).rejects.toBeInstanceOf(OperationsClientError);
  });

  it('принимает только схемную GeoJSON-топологию с синтетическими координатами', async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json({
      type: 'FeatureCollection',
      features: [{
        type: 'Feature',
        id: 'object-1',
        geometry: { type: 'MultiLineString', coordinates: [[[0, 0], [0.4, 0]]] },
        properties: {
          objectId: 'object-1',
          parentId: null,
          objectKind: 'controlHouse',
          dispatcherName: 'Комплекс 1',
          geometrySource: 'synthetic',
          provenance: 'derived',
          coordinateProvenance: 'simulated',
        },
      }],
      metadata: {
        title: 'Схема объектов',
        geometrySource: 'synthetic',
        coordinateProvenance: 'simulated',
      },
    }));

    const topology = await fetchTopology(fetcher);

    expect(topology.features[0].properties.geometrySource).toBe('synthetic');
  });
});
