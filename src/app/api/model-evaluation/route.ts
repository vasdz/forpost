import { proxyForpostApi } from '@/server/forpostApi';

export async function GET() {
  return proxyForpostApi('/api/model-evaluation');
}
