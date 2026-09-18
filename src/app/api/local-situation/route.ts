import { NextResponse } from 'next/server';

import {
  getLocalSituationSnapshot,
  LocalSituationUnavailableError,
} from '@/data/localSituation';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const localResponseHeaders = {
  'Cache-Control': 'no-store, no-cache, must-revalidate, private',
  'Content-Security-Policy': "default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
  'Permissions-Policy': 'geolocation=(), camera=(), microphone=()',
  'Referrer-Policy': 'no-referrer',
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
  'X-Robots-Tag': 'noindex, nofollow',
};

function isLocalSnapshotRuntime(): boolean {
  return process.env.FORPOST_LOCAL_SNAPSHOT === '1';
}

export async function GET(request: Request): Promise<Response> {
  void request;
  // Route Handler не получает доверенный TCP peer. Доступ к снимку ограничен
  // listener-ом launcher на 127.0.0.1; Host и forwarded-заголовки не являются auth.
  if (!isLocalSnapshotRuntime()) {
    return new Response(null, { status: 404, headers: localResponseHeaders });
  }

  try {
    const snapshot = await getLocalSituationSnapshot();
    return NextResponse.json(snapshot, { headers: localResponseHeaders });
  } catch (error) {
    if (!(error instanceof LocalSituationUnavailableError)) {
      throw error;
    }

    return NextResponse.json(
      {
        code: 'LOCAL_SITUATION_UNAVAILABLE',
        message: 'Локальный снимок данных недоступен.',
      },
      { status: 503, headers: localResponseHeaders },
    );
  }
}
