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
  const token = process.env.FORPOST_API_SERVICE_TOKEN || '';
  const origin = backendOrigin();
  if (token.length < 32 || origin === null || !isAllowedBackendPath(path)) {
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
