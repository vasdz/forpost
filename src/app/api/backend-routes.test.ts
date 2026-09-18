// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from 'vitest';

const backend = vi.hoisted(() => ({ proxyForpostApi: vi.fn() }));
vi.mock('@/server/forpostApi', () => backend);

import { GET as getAvailability } from './availability/route';
import { GET as getPredictions } from './predictions/route';
import { POST as postDecision } from './predictions/[predictionId]/decisions/route';

describe('same-origin backend routes', () => {
  beforeEach(() => {
    backend.proxyForpostApi.mockReset();
    backend.proxyForpostApi.mockResolvedValue(
      new Response('{"status":"ok"}', {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });

  it('проксирует чтение прогнозов и доступности только на фиксированные пути', async () => {
    await getPredictions();
    await getAvailability();

    expect(backend.proxyForpostApi).toHaveBeenNthCalledWith(1, '/api/predictions');
    expect(backend.proxyForpostApi).toHaveBeenNthCalledWith(2, '/api/availability');
  });

  it('не принимает решение без доверенной пользовательской сессии', async () => {
    const request = new Request('http://127.0.0.1/api/predictions/id/decisions', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ decision: 'confirmed', reason: 'Проверка назначена.' }),
    });

    const response = await postDecision(request, {
      params: Promise.resolve({ predictionId: 'prediction/001' }),
    });

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({
      error: 'Доверенная пользовательская сессия не подключена',
    });
    expect(backend.proxyForpostApi).not.toHaveBeenCalled();
  });

  it('отклоняет не-JSON решение до обращения к FastAPI', async () => {
    const request = new Request('http://127.0.0.1/api/predictions/id/decisions', {
      method: 'POST',
      headers: { 'content-type': 'text/plain' },
      body: 'confirmed',
    });

    const response = await postDecision(request, {
      params: Promise.resolve({ predictionId: 'prediction-001' }),
    });

    expect(response.status).toBe(415);
    expect(backend.proxyForpostApi).not.toHaveBeenCalled();
  });
});
