import { timingSafeEqual } from 'node:crypto';

export const DEMO_SESSION_COOKIE = 'forpost_demo_session';
export const CSRF_COOKIE = 'forpost_csrf';
export const CSRF_HEADER = 'x-forpost-csrf';

export type DemoMutationContext = {
  credential: string;
  csrfToken: string;
};

function readCookie(request: Request, name: string): string | null {
  const header = request.headers.get('cookie');
  if (header === null) return null;
  for (const part of header.split(';')) {
    const [key, ...valueParts] = part.trim().split('=');
    if (key === name) {
      try {
        return decodeURIComponent(valueParts.join('='));
      } catch {
        return null;
      }
    }
  }
  return null;
}

function equalTokens(left: string, right: string): boolean {
  const leftBuffer = Buffer.from(left, 'utf8');
  const rightBuffer = Buffer.from(right, 'utf8');
  return leftBuffer.length === rightBuffer.length && timingSafeEqual(leftBuffer, rightBuffer);
}

export function isSameOriginMutation(request: Request): boolean {
  const origin = request.headers.get('origin');
  if (origin === null) return false;
  try {
    const parsedOrigin = new URL(origin);
    const externalHost = request.headers.get('host');
    const isLoopback = ['127.0.0.1', '::1', 'localhost'].includes(parsedOrigin.hostname);
    return isLoopback
      && ['http:', 'https:'].includes(parsedOrigin.protocol)
      && externalHost !== null
      && !externalHost.includes(',')
      && parsedOrigin.host.toLowerCase() === externalHost.toLowerCase();
  } catch {
    return false;
  }
}

export function readDemoMutationContext(request: Request): DemoMutationContext | null {
  if (!isSameOriginMutation(request)) return null;
  const credential = readCookie(request, DEMO_SESSION_COOKIE);
  const cookieToken = readCookie(request, CSRF_COOKIE);
  const headerToken = request.headers.get(CSRF_HEADER);
  if (
    credential === null
    || !/^demo\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(credential)
    || credential.length > 4_101
    || cookieToken === null
    || headerToken === null
    || cookieToken.length < 32
    || !equalTokens(cookieToken, headerToken)
  ) {
    return null;
  }
  return { credential, csrfToken: cookieToken };
}

export function readDemoSession(request: Request): DemoMutationContext | null {
  const credential = readCookie(request, DEMO_SESSION_COOKIE);
  const csrfToken = readCookie(request, CSRF_COOKIE);
  if (
    credential === null
    || !/^demo\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(credential)
    || credential.length > 4_101
    || csrfToken === null
    || csrfToken.length < 32
  ) {
    return null;
  }
  return { credential, csrfToken };
}
