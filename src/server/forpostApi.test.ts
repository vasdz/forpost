// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest';

import { proxyForpostApi } from './forpostApi';

describe('proxyForpostApi', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it('fail-closed не обращается к backend без серверного токена', async () => {
    vi.stubEnv('FORPOST_API_SERVICE_TOKEN', '');
    const fetcher = vi.fn();

    const response = await proxyForpostApi('/api/predictions', { fetcher });

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({
      error: 'Backend временно недоступен',
      status: 'unavailable',
    });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('передаёт токен только разрешённому loopback backend', async () => {
    vi.stubEnv('FORPOST_API_SERVICE_TOKEN', 'x'.repeat(40));
    vi.stubEnv('FORPOST_BACKEND_URL', 'http://127.0.0.1:8000');
    const fetcher = vi.fn().mockResolvedValue(
      new Response('{"predictions":[]}', {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );

    const response = await proxyForpostApi('/api/predictions', { fetcher });

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ predictions: [] });
    expect(fetcher).toHaveBeenCalledOnce();
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toBe('http://127.0.0.1:8000/api/predictions');
    expect(init.headers).toEqual({
      Accept: 'application/json',
      Authorization: `Bearer ${'x'.repeat(40)}`,
    });
    expect(init.cache).toBe('no-store');
  });

  it('не отправляет токен на внешний URL из конфигурации', async () => {
    vi.stubEnv('FORPOST_API_SERVICE_TOKEN', 'x'.repeat(40));
    vi.stubEnv('FORPOST_BACKEND_URL', 'https://example.invalid');
    const fetcher = vi.fn();

    const response = await proxyForpostApi('/api/predictions', { fetcher });

    expect(response.status).toBe(503);
    expect(fetcher).not.toHaveBeenCalled();
  });
});
