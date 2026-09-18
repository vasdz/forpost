import { proxyForpostApi } from '@/server/forpostApi';
import { readDemoMutationContext } from '@/server/demoSession';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const PRIORITIES = new Set(['low', 'medium', 'high', 'critical']);

function isTimestampWithTimezone(value: unknown): value is string {
  if (typeof value !== 'string' || value.length < 20 || value.length > 35 || !value.includes('T')) {
    return false;
  }
  const timezoneMarker = value.endsWith('Z')
    || value.lastIndexOf('+') > value.indexOf('T')
    || value.lastIndexOf('-') > value.indexOf('T');
  return timezoneMarker && !Number.isNaN(Date.parse(value));
}

function errorResponse(status: number, error: string): Response {
  return Response.json({ error }, { status, headers: { 'Cache-Control': 'no-store' } });
}

export async function GET(): Promise<Response> {
  return proxyForpostApi('/api/v1/service-request-drafts');
}

export async function POST(request: Request): Promise<Response> {
  const session = readDemoMutationContext(request);
  if (session === null) return errorResponse(403, 'Demo-сессия или CSRF-токен недействительны');
  if (!request.headers.get('content-type')?.toLowerCase().startsWith('application/json')) {
    return errorResponse(415, 'Ожидается application/json');
  }
  const body = await request.text();
  if (body.length > 4_096) return errorResponse(413, 'Тело запроса слишком велико');
  try {
    const payload: unknown = JSON.parse(body);
    if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) throw new Error();
    const record = payload as Record<string, unknown>;
    const expected = [
      'category',
      'dueAt',
      'incidentId',
      'priority',
      'recommendedAction',
      'targetId',
    ];
    if (
      Object.keys(record).sort().join(',') !== expected.sort().join(',')
      || typeof record.incidentId !== 'string'
      || !/^[a-f0-9]{64}$/.test(record.incidentId)
      || typeof record.targetId !== 'string'
      || record.targetId.length < 1
      || record.targetId.length > 256
      || typeof record.category !== 'string'
      || record.category.length < 1
      || record.category.length > 128
      || !PRIORITIES.has(String(record.priority))
      || typeof record.recommendedAction !== 'string'
      || record.recommendedAction.trim().length < 5
      || record.recommendedAction.length > 2_000
      || !isTimestampWithTimezone(record.dueAt)
    ) throw new Error();
  } catch {
    return errorResponse(422, 'Недопустимый черновик заявки');
  }
  return proxyForpostApi('/api/v1/service-request-drafts', {
    method: 'POST',
    body,
    credential: session.credential,
  });
}
