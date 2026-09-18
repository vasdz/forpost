import { randomBytes } from 'node:crypto';

import { NextResponse } from 'next/server';

import { requestDemoSession, type DemoProfile } from '@/server/forpostApi';
import {
  CSRF_COOKIE,
  DEMO_SESSION_COOKIE,
  isSameOriginMutation,
  readDemoSession,
} from '@/server/demoSession';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const PROFILES = new Set<DemoProfile>([
  'district-dispatcher',
  'central-dispatcher',
  'technician',
  'admin',
]);
const MAX_BODY_CHARS = 1_024;

function jsonError(status: number, error: string): NextResponse {
  return NextResponse.json({ error }, { status, headers: { 'Cache-Control': 'no-store' } });
}

export async function GET(request: Request): Promise<NextResponse> {
  const session = readDemoSession(request);
  return NextResponse.json(
    session === null
      ? { active: false, provenance: 'unavailable' }
      : { active: true, csrfToken: session.csrfToken, provenance: 'simulated' },
    { headers: { 'Cache-Control': 'no-store' } },
  );
}

export async function POST(request: Request): Promise<NextResponse> {
  if (!isSameOriginMutation(request)) return jsonError(403, 'Источник запроса отклонён');
  if (!request.headers.get('content-type')?.toLowerCase().startsWith('application/json')) {
    return jsonError(415, 'Ожидается application/json');
  }
  const declaredLength = Number(request.headers.get('content-length') ?? '0');
  if (Number.isFinite(declaredLength) && declaredLength > MAX_BODY_CHARS) {
    return jsonError(413, 'Тело запроса слишком велико');
  }
  const body = await request.text();
  if (body.length > MAX_BODY_CHARS) return jsonError(413, 'Тело запроса слишком велико');
  let profile: DemoProfile;
  try {
    const payload: unknown = JSON.parse(body);
    if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) throw new Error();
    const record = payload as Record<string, unknown>;
    if (Object.keys(record).length !== 1 || !PROFILES.has(record.profile as DemoProfile)) {
      throw new Error();
    }
    profile = record.profile as DemoProfile;
  } catch {
    return jsonError(422, 'Недопустимый demo-профиль');
  }
  const issued = await requestDemoSession(profile);
  if (issued === null) return jsonError(503, 'Demo-сессия не настроена');

  const csrfToken = randomBytes(32).toString('base64url');
  const response = NextResponse.json(
    { active: true, profile, csrfToken, provenance: 'simulated' },
    { status: 201, headers: { 'Cache-Control': 'no-store' } },
  );
  const secure = process.env.NODE_ENV === 'production';
  response.cookies.set(DEMO_SESSION_COOKIE, issued.assertion, {
    httpOnly: true,
    sameSite: 'strict',
    secure,
    path: '/',
    maxAge: issued.expiresIn,
  });
  response.cookies.set(CSRF_COOKIE, csrfToken, {
    httpOnly: true,
    sameSite: 'strict',
    secure,
    path: '/',
    maxAge: issued.expiresIn,
  });
  return response;
}
