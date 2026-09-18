const DEFAULT_BACKEND_URL = 'http://127.0.0.1:8000';
const REQUEST_TIMEOUT_MS = 5_000;
const unavailablePayload = JSON.stringify({
  error: 'Backend временно недоступен',
  status: 'unavailable',
});

type ProxyOptions = {
  method?: 'GET' | 'POST';
  body?: string;
  fetcher?: typeof globalThis.fetch;
  credential?: string;
  idempotencyKey?: string;
};

export type DemoProfile = 'district-dispatcher' | 'central-dispatcher' | 'technician' | 'admin';
export type DemoAssertion = {
  assertion: string;
  expiresIn: number;
  provenance: 'simulated';
};

function unavailableResponse(): Response {
  return new Response(unavailablePayload, {
    status: 503,
    headers: {
      'Cache-Control': 'no-store, no-cache, must-revalidate, private',
      'Content-Type': 'application/json; charset=utf-8',
      'X-Content-Type-Options': 'nosniff',
    },
  });
}

function backendOrigin(): URL | null {
  try {
    const url = new URL(process.env.FORPOST_BACKEND_URL || DEFAULT_BACKEND_URL);
    const isLoopback = ['127.0.0.1', '::1', 'localhost'].includes(url.hostname);
    if (
      url.protocol !== 'http:'
      || !isLoopback
      || url.username !== ''
      || url.password !== ''
      || url.pathname !== '/'
      || url.search !== ''
      || url.hash !== ''
    ) {
      return null;
    }
    return url;
  } catch {
    return null;
  }
}

function isAllowedBackendPath(path: string): boolean {
  return path.startsWith('/api/')
    && !path.includes('..')
    && !path.includes('?')
    && !path.includes('#');
}

export async function proxyForpostApi(
  path: string,
  options: ProxyOptions = {},
): Promise<Response> {
  const token = options.credential ?? process.env.FORPOST_API_SERVICE_TOKEN ?? '';
  const origin = backendOrigin();
  const validCredential = options.credential === undefined
    ? token.length >= 32
    : /^demo\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(token) && token.length <= 4_101;
  if (!validCredential || origin === null || !isAllowedBackendPath(path)) {
    return unavailableResponse();
  }

  const fetcher = options.fetcher ?? globalThis.fetch;
  const method = options.method ?? 'GET';
  const headers: Record<string, string> = {
    Accept: 'application/json',
    Authorization: `Bearer ${token}`,
  };
  if (method === 'POST') {
    headers['Content-Type'] = 'application/json';
    if (options.idempotencyKey !== undefined) {
      headers['Idempotency-Key'] = options.idempotencyKey;
    }
  }

  try {
    const upstream = await fetcher(new URL(path, origin).toString(), {
      method,
      body: options.body,
      cache: 'no-store',
      headers,
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    if (!upstream.headers.get('content-type')?.toLowerCase().includes('application/json')) {
      return unavailableResponse();
    }
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: {
        'Cache-Control': 'no-store, no-cache, must-revalidate, private',
        'Content-Type': 'application/json; charset=utf-8',
        'X-Content-Type-Options': 'nosniff',
      },
    });
  } catch {
    return unavailableResponse();
  }
}

function isDemoAssertion(value: unknown): value is DemoAssertion {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  return Object.keys(record).sort().join(',') === 'assertion,expiresIn,provenance'
    && typeof record.assertion === 'string'
    && /^demo\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(record.assertion)
    && record.assertion.length <= 4_101
    && record.expiresIn === 300
    && record.provenance === 'simulated';
}

export async function requestDemoSession(
  profile: DemoProfile,
  fetcher: typeof globalThis.fetch = globalThis.fetch,
): Promise<DemoAssertion | null> {
  const accessKey = process.env.FORPOST_DEMO_ACCESS_KEY ?? '';
  const origin = backendOrigin();
  if (process.env.FORPOST_DEMO_MODE !== '1' || accessKey.length < 32 || origin === null) {
    return null;
  }
  try {
    const response = await fetcher(new URL('/api/v1/demo/session', origin), {
      method: 'POST',
      body: JSON.stringify({ profile }),
      cache: 'no-store',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-Demo-Access-Key': accessKey,
      },
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) {
      return null;
    }
    const payload: unknown = await response.json();
    return isDemoAssertion(payload) ? payload : null;
  } catch {
    return null;
  }
}
