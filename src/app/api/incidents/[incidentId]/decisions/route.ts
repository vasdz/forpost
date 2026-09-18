import { proxyForpostApi } from '@/server/forpostApi';
import { readDemoMutationContext } from '@/server/demoSession';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

type RouteContext = { params: Promise<{ incidentId: string }> };
const STATUSES = new Set([
  'new',
  'in_review',
  'crew_dispatch',
  'false_alarm',
  'confirmed_incident',
  'closed',
]);

function errorResponse(status: number, error: string): Response {
  return Response.json({ error }, { status, headers: { 'Cache-Control': 'no-store' } });
}

async function incidentPath(context: RouteContext): Promise<string | null> {
  const { incidentId } = await context.params;
  return /^[a-f0-9]{64}$/.test(incidentId)
    ? `/api/v1/incidents/${incidentId}/decisions`
    : null;
}

export async function GET(_request: Request, context: RouteContext): Promise<Response> {
  const path = await incidentPath(context);
  return path === null ? errorResponse(404, 'Инцидент не найден') : proxyForpostApi(path);
}

export async function POST(request: Request, context: RouteContext): Promise<Response> {
  const path = await incidentPath(context);
  if (path === null) return errorResponse(404, 'Инцидент не найден');
  const session = readDemoMutationContext(request);
  if (session === null) return errorResponse(403, 'Demo-сессия или CSRF-токен недействительны');
  if (!request.headers.get('content-type')?.toLowerCase().startsWith('application/json')) {
    return errorResponse(415, 'Ожидается application/json');
  }
  const idempotencyKey = request.headers.get('idempotency-key') ?? '';
  if (!/^[A-Za-z0-9._:-]{8,128}$/.test(idempotencyKey)) {
    return errorResponse(422, 'Некорректный Idempotency-Key');
  }
  const body = await request.text();
  if (body.length > 2_048) return errorResponse(413, 'Тело запроса слишком велико');
  try {
    const payload: unknown = JSON.parse(body);
    if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) throw new Error();
    const record = payload as Record<string, unknown>;
    const keys = Object.keys(record);
    if (
      !keys.every((key) => ['status', 'reason', 'correctsDecisionId'].includes(key))
      || !keys.includes('status')
      || !keys.includes('reason')
      || !STATUSES.has(String(record.status))
      || typeof record.reason !== 'string'
      || record.reason.trim().length < 5
      || record.reason.length > 1_000
      || (record.correctsDecisionId !== undefined && typeof record.correctsDecisionId !== 'string')
    ) throw new Error();
  } catch {
    return errorResponse(422, 'Недопустимое решение');
  }
  return proxyForpostApi(path, {
    method: 'POST',
    body,
    credential: session.credential,
    idempotencyKey,
  });
}
