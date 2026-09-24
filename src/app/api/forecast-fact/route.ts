import { proxyForpostApi } from '@/server/forpostApi';
import { readDemoSession } from '@/server/demoSession';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request: Request): Promise<Response> {
  const session = readDemoSession(request);
  if (session === null) {
    return Response.json(
      { error: 'Требуется доверенная пользовательская сессия' },
      { status: 401, headers: { 'Cache-Control': 'no-store' } },
    );
  }
  return proxyForpostApi('/api/forecast-fact', { credential: session.credential });
}
