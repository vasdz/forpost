import { proxyForpostApi } from '@/server/forpostApi';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const MAX_DECISION_BODY_BYTES = 4_096;

type RouteContext = {
  params: Promise<{ predictionId: string }>;
};

function errorResponse(status: number, error: string): Response {
  return Response.json(
    { error },
    {
      status,
      headers: {
        'Cache-Control': 'no-store, no-cache, must-revalidate, private',
        'X-Content-Type-Options': 'nosniff',
      },
    },
  );
}

export async function POST(request: Request, context: RouteContext): Promise<Response> {
  if (!request.headers.get('content-type')?.toLowerCase().startsWith('application/json')) {
    return errorResponse(415, 'Ожидается application/json');
  }

  const declaredLength = Number(request.headers.get('content-length') ?? '0');
  if (!Number.isFinite(declaredLength) || declaredLength > MAX_DECISION_BODY_BYTES) {
    return errorResponse(413, 'Размер решения превышает допустимый лимит');
  }

  let body: string;
  try {
    body = await request.text();
    if (new TextEncoder().encode(body).byteLength > MAX_DECISION_BODY_BYTES) {
      return errorResponse(413, 'Размер решения превышает допустимый лимит');
    }
    JSON.parse(body);
  } catch {
    return errorResponse(400, 'Некорректный JSON');
  }

  const { predictionId } = await context.params;
  return proxyForpostApi(
    `/api/predictions/${encodeURIComponent(predictionId)}/decisions`,
    { method: 'POST', body },
  );
}
