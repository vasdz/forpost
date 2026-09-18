import { proxyForpostApi } from '@/server/forpostApi';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(): Promise<Response> {
  return proxyForpostApi('/api/predictions');
}
