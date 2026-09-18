import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const localSituation = vi.hoisted(() => {
  class LocalSituationUnavailableError extends Error {}

  return {
    LocalSituationUnavailableError,
    getLocalSituationSnapshot: vi.fn(),
  };
});

vi.mock('@/data/localSituation', () => localSituation);

import { GET } from './route';

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
  channels: [],
  objects: [],
  events: [],
};

function request(host: string): Request {
  return new Request('http://127.0.0.1/api/local-situation', { headers: { host } });
}

describe('GET /api/local-situation', () => {
  beforeEach(() => {
    vi.stubEnv('FORPOST_LOCAL_SNAPSHOT', '1');
    localSituation.getLocalSituationSnapshot.mockReset();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('не использует управляемый клиентом Host как подтверждение локального доступа', async () => {
    localSituation.getLocalSituationSnapshot.mockResolvedValue(observedSnapshot);

    const response = await GET(request('example.invalid'));

    expect(response.status).toBe(200);
    expect(response.headers.get('cache-control')).toContain('no-store');
    expect(response.headers.get('x-content-type-options')).toBe('nosniff');
    expect(localSituation.getLocalSituationSnapshot).toHaveBeenCalledOnce();
  });

  it('не выдаёт снимок при запуске вне штатного локального launcher', async () => {
    vi.stubEnv('FORPOST_LOCAL_SNAPSHOT', '0');

    const response = await GET(request('localhost:3000'));

    expect(response.status).toBe(404);
    expect(localSituation.getLocalSituationSnapshot).not.toHaveBeenCalled();
  });

  it('выдаёт локальный ответ без кеширования и с защитными заголовками', async () => {
    localSituation.getLocalSituationSnapshot.mockResolvedValue(observedSnapshot);

    const response = await GET(request('localhost:3000'));

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual(observedSnapshot);
    expect(response.headers.get('cache-control')).toContain('no-store');
    expect(response.headers.get('x-robots-tag')).toBe('noindex, nofollow');
    expect(response.headers.get('x-content-type-options')).toBe('nosniff');
    expect(response.headers.get('x-frame-options')).toBe('DENY');
    expect(response.headers.get('referrer-policy')).toBe('no-referrer');
    expect(response.headers.get('content-security-policy')).toContain("default-src 'none'");
  });

  it('не раскрывает причину недоступности локального файла', async () => {
    localSituation.getLocalSituationSnapshot.mockRejectedValue(
      new localSituation.LocalSituationUnavailableError('internal local path'),
    );

    const response = await GET(request('127.0.0.1'));

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({
      code: 'LOCAL_SITUATION_UNAVAILABLE',
      message: 'Локальный снимок данных недоступен.',
    });
  });
});
