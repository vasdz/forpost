import { describe, expect, it } from 'vitest';

import nextConfig from '../../next.config';

describe('Next.js security headers', () => {
  it('protects every browser response from embedding and active-content injection', async () => {
    expect(nextConfig.headers).toBeTypeOf('function');

    const configured = await nextConfig.headers!();
    const catchAll = configured.find((entry) => entry.source === '/:path*');
    const headers = Object.fromEntries(
      (catchAll?.headers ?? []).map(({ key, value }) => [key.toLowerCase(), value]),
    );

    expect(headers['x-frame-options']).toBe('DENY');
    expect(headers['x-content-type-options']).toBe('nosniff');
    expect(headers['referrer-policy']).toBe('no-referrer');
    expect(headers['permissions-policy']).toBe('geolocation=(), camera=(), microphone=()');
    expect(headers['content-security-policy']).toContain("object-src 'none'");
    expect(headers['content-security-policy']).toContain("frame-ancestors 'none'");
    expect(headers['content-security-policy']).not.toContain("script-src *");
  });
});
