// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from 'vitest';

const backend = vi.hoisted(() => ({
  proxyForpostApi: vi.fn(),
  requestDemoSession: vi.fn(),
}));
vi.mock('@/server/forpostApi', () => backend);

import { POST as createDemoSession } from './demo-session/route';
import { POST as recordDecision } from './incidents/[incidentId]/decisions/route';

const INCIDENT_ID = 'a'.repeat(64);
const ASSERTION = `demo.${'x'.repeat(40)}.${'y'.repeat(40)}`;

describe('операционные BFF-маршруты', () => {
  beforeEach(() => {
    backend.proxyForpostApi.mockReset();
    backend.requestDemoSession.mockReset();
    backend.requestDemoSession.mockResolvedValue({
      assertion: ASSERTION,
      expiresIn: 300,
      provenance: 'simulated',
    });
    backend.proxyForpostApi.mockResolvedValue(Response.json({ status: 'in_review' }, { status: 201 }));
  });

  it('создаёт HttpOnly Strict demo-сессию только для same-origin запроса', async () => {
    const request = new Request('http://localhost:3000/api/demo-session', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        host: '127.0.0.1:3000',
        origin: 'http://127.0.0.1:3000',
      },
      body: JSON.stringify({ profile: 'central-dispatcher' }),
    });

    const response = await createDemoSession(request);

    expect(response.status).toBe(201);
    const cookies = response.headers.getSetCookie().join(';');
    expect(cookies).toContain('forpost_demo_session=');
    expect(cookies).toContain('HttpOnly');
    expect(cookies.toLowerCase()).toContain('samesite=strict');
    expect(await response.json()).toMatchObject({ active: true, profile: 'central-dispatcher' });
  });

  it('отклоняет login CSRF с чужого Origin', async () => {
    const request = new Request('http://127.0.0.1/api/demo-session', {
      method: 'POST',
      headers: { 'content-type': 'application/json', origin: 'https://evil.invalid' },
      body: JSON.stringify({ profile: 'central-dispatcher' }),
    });

    const response = await createDemoSession(request);

    expect(response.status).toBe(403);
    expect(backend.requestDemoSession).not.toHaveBeenCalled();
  });

  it('не проксирует решение без совпадающего CSRF-токена', async () => {
    const request = new Request(
      `http://127.0.0.1/api/incidents/${INCIDENT_ID}/decisions`,
      {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          origin: 'http://127.0.0.1',
          cookie: `forpost_demo_session=${ASSERTION}; forpost_csrf=${'c'.repeat(40)}`,
          'x-forpost-csrf': 'wrong-token',
          'idempotency-key': 'decision-command-1',
        },
        body: JSON.stringify({ status: 'in_review', reason: 'Начата проверка тревоги' }),
      },
    );

    const response = await recordDecision(request, {
      params: Promise.resolve({ incidentId: INCIDENT_ID }),
    });

    expect(response.status).toBe(403);
    expect(backend.proxyForpostApi).not.toHaveBeenCalled();
  });

  it('проксирует валидированное решение с demo-личностью и Idempotency-Key', async () => {
    const assertion = ASSERTION;
    const request = new Request(
      `http://127.0.0.1/api/incidents/${INCIDENT_ID}/decisions`,
      {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          origin: 'http://127.0.0.1',
          cookie: `forpost_demo_session=${assertion}; forpost_csrf=${'c'.repeat(40)}`,
          'x-forpost-csrf': 'c'.repeat(40),
          'idempotency-key': 'decision-command-1',
        },
        body: JSON.stringify({ status: 'in_review', reason: 'Начата проверка тревоги' }),
      },
    );

    const response = await recordDecision(request, {
      params: Promise.resolve({ incidentId: INCIDENT_ID }),
    });

    expect(response.status).toBe(201);
    expect(backend.proxyForpostApi).toHaveBeenCalledWith(
      `/api/v1/incidents/${INCIDENT_ID}/decisions`,
      expect.objectContaining({
        method: 'POST',
        credential: assertion,
        idempotencyKey: 'decision-command-1',
      }),
    );
  });
});
