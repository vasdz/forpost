import { describe, expect, it, vi } from 'vitest';

import {
  OperationsClientError,
  fetchServiceDrafts,
  fetchTopology,
  recordIncidentDecision,
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
