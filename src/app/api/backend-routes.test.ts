// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from 'vitest';

const backend = vi.hoisted(() => ({ proxyForpostApi: vi.fn() }));
vi.mock('@/server/forpostApi', () => backend);

const DEMO_ASSERTION = `demo.${'x'.repeat(40)}.${'y'.repeat(40)}`;

import { GET as getAvailability } from './availability/route';
import { GET as getModelEvaluation } from './model-evaluation/route';
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

  it('проксирует чтение прогнозов, оценки с пользовательской demo-сессией и доступности только на фиксированные пути', async () => {
    await getPredictions();
    await getModelEvaluation(new Request('http://127.0.0.1/api/model-evaluation', {
      headers: { cookie: `forpost_demo_session=${DEMO_ASSERTION}; forpost_csrf=${'c'.repeat(40)}` },
    }));
    await getAvailability();

    expect(backend.proxyForpostApi).toHaveBeenNthCalledWith(1, '/api/predictions');
    expect(backend.proxyForpostApi).toHaveBeenNthCalledWith(2, '/api/model-evaluation', { credential: DEMO_ASSERTION });
    expect(backend.proxyForpostApi).toHaveBeenNthCalledWith(3, '/api/availability');
  });

  it('не подставляет центральный service token для анонимного чтения отчёта', async () => {
    const response = await getModelEvaluation(new Request('http://127.0.0.1/api/model-evaluation', {
      headers: { authorization: `Bearer ${'service-token'.repeat(4)}` },
    }));

    expect(response.status).toBe(401);
    await expect(response.json()).resolves.toEqual({ error: 'Требуется доверенная пользовательская сессия' });
    expect(backend.proxyForpostApi).not.toHaveBeenCalled();
  });

  it.each([401, 503])('передаёт scoped demo-утверждение и сохраняет статус %s backend', async (status) => {
    backend.proxyForpostApi.mockResolvedValue(Response.json({ status: 'unavailable' }, { status }));
    const response = await getModelEvaluation(new Request('http://127.0.0.1/api/model-evaluation', {
      headers: { cookie: `forpost_demo_session=${DEMO_ASSERTION}; forpost_csrf=${'c'.repeat(40)}` },
    }));

    expect(response.status).toBe(status);
    expect(backend.proxyForpostApi).toHaveBeenCalledWith('/api/model-evaluation', { credential: DEMO_ASSERTION });
  });

  it('не принимает решение без доверенной пользовательской сессии', async () => {
    const request = new Request('http://127.0.0.1/api/predictions/id/decisions', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ decision: 'confirmed', reason: 'Проверка назначена.' }),
    });

    const response = await postDecision(request, {
      params: Promise.resolve({ predictionId: 'prediction-001' }),
    });

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual({
      error: 'Demo-сессия или CSRF-токен недействительны',
    });
    expect(backend.proxyForpostApi).not.toHaveBeenCalled();
  });

  it('отклоняет не-JSON решение до обращения к FastAPI', async () => {
    const request = new Request('http://127.0.0.1/api/predictions/id/decisions', {
      method: 'POST',
      headers: {
        'content-type': 'text/plain',
        origin: 'http://127.0.0.1',
        cookie: `forpost_demo_session=${DEMO_ASSERTION}; forpost_csrf=${'c'.repeat(40)}`,
        'x-forpost-csrf': 'c'.repeat(40),
      },
      body: 'confirmed',
    });

    const response = await postDecision(request, {
      params: Promise.resolve({ predictionId: 'prediction-001' }),
    });

    expect(response.status).toBe(415);
    expect(backend.proxyForpostApi).not.toHaveBeenCalled();
  });
});
