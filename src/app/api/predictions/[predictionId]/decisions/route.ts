export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

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

  void context;
  // Серверный BFF-токен пригоден только для чтения и не идентифицирует человека.
  // Запись решений включается лишь вместе с доверенной пользовательской сессией и CSRF-защитой.
  return errorResponse(503, 'Доверенная пользовательская сессия не подключена');
}
