import { proxyForpostApi } from '@/server/forpostApi';
import { readDemoMutationContext } from '@/server/demoSession';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

type RouteContext = { params: Promise<{ predictionId: string }> };

function errorResponse(status: number, error: string): Response {
  return Response.json({ error }, { status, headers: { 'Cache-Control': 'no-store' } });
}

export async function POST(request: Request, context: RouteContext): Promise<Response> {
  const { predictionId } = await context.params;
  if (!/^[A-Za-z0-9._:-]{1,128}$/.test(predictionId)) {
    return errorResponse(404, 'Прогноз не найден');
  }
  const session = readDemoMutationContext(request);
  if (session === null) return errorResponse(403, 'Demo-сессия или CSRF-токен недействительны');
  if (!request.headers.get('content-type')?.toLowerCase().startsWith('application/json')) {
    return errorResponse(415, 'Ожидается application/json');
  }
  const body = await request.text();
  if (body.length > 1_024) return errorResponse(413, 'Тело запроса слишком велико');
  try {
    const payload: unknown = JSON.parse(body);
    if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) throw new Error();
    const record = payload as Record<string, unknown>;
    if (Object.keys(record).length !== 0) throw new Error();
  } catch {
    return errorResponse(422, 'Тело запроса должно быть пустым объектом');
  }
  return proxyForpostApi(`/api/predictions/${predictionId}/service-request-drafts`, {
    method: 'POST', body, credential: session.credential,
  });
}
