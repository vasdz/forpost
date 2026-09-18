import { describe, expect, it, vi } from 'vitest';

import { fetchLocalSituation } from './localSituationClient';

const observedSnapshot = {
  sourceAvailability: {
    events: true,
    channels: true,
    objects: true,
    access_events: false,
    maintenance_history: false,
    ml_predictions: false,
    work_permits: false,
  },
  dataQuality: {
    builtAt: '2026-09-18T10:00:00Z',
    latestObservedAt: '2026-08-01T23:59:58',
    eventCount: 1,
    skippedTimestampCount: 0,
    technicalAnomalyCount: 0,
    unmappedChannelCount: 1,
    objectLinkAvailable: false,
    freshness: 'historical',
  },
  channels: [{
    channelId: 'channel-1',
    engineeringSystemType: 'system',
    sensorType: 'sensor',
    engineeringSystemTag: 'tag',
    sensorName: 'name',
    objectId: null,
  }],
  objects: [{
    objectId: 'object-1',
    hierarchyLevel: '1',
    parentId: null,
    objectKind: 'kind',
    dispatcherName: 'name',
  }],
  events: [{
    canonicalId: 'a'.repeat(64),
    eventId: 'event-1',
    channelId: 'channel-1',
    recordedAt: '2026-08-01T23:59:58',
    isAlarm: true,
    sensorValue: 'value',
    qualityCode: 'valid',
    analysisEligible: true,
    provenance: 'observed',
  }],
};

describe('fetchLocalSituation', () => {
  it('читает только относительный локальный маршрут без кеша и валидирует provenance', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(observedSnapshot), { status: 200 }));

    await expect(fetchLocalSituation(fetcher)).resolves.toEqual({ status: 'ready', snapshot: observedSnapshot });

    expect(fetcher).toHaveBeenCalledWith('/api/local-situation', {
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    });
  });

  it('не подставляет резервные данные при ответе 503', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      code: 'LOCAL_SITUATION_UNAVAILABLE',
      message: 'Локальный снимок данных недоступен.',
    }), { status: 503 }));

    await expect(fetchLocalSituation(fetcher)).resolves.toEqual({
      status: 'unavailable',
      message: 'Локальный снимок данных недоступен.',
    });
  });

  it('считает недоступным ответ с неподтверждённой схемой даже при 200', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ events: [] }), { status: 200 }));

    await expect(fetchLocalSituation(fetcher)).resolves.toEqual({
      status: 'unavailable',
      message: 'Локальный снимок данных недоступен.',
    });
  });

  it('не раскрывает ошибку сети в интерфейсе', async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error('network details'));

    await expect(fetchLocalSituation(fetcher)).resolves.toEqual({
      status: 'unavailable',
      message: 'Локальный снимок данных недоступен.',
    });
  });
});
