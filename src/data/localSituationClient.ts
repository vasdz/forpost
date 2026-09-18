import {
  isLocalSituationSnapshot,
  type LocalSituationSnapshot,
} from './localSituationContract';

const unavailableMessage = 'Локальный снимок данных недоступен.';

export type LocalSituationLoadState =
  | { status: 'loading' }
  | { status: 'ready'; snapshot: LocalSituationSnapshot }
  | { status: 'unavailable'; message: string };

type LocalSituationLoadResult = Exclude<LocalSituationLoadState, { status: 'loading' }>;

export type LocalSituationFetcher = (
  input: string,
  init: RequestInit,
) => Promise<Response>;

function unavailable(): LocalSituationLoadResult {
  return { status: 'unavailable', message: unavailableMessage };
}

export async function fetchLocalSituation(
  fetcher: LocalSituationFetcher = globalThis.fetch,
): Promise<Exclude<LocalSituationLoadState, { status: 'loading' }>> {
  try {
    const response = await fetcher('/api/local-situation', {
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) {
      return unavailable();
    }

    const payload: unknown = await response.json();
    return isLocalSituationSnapshot(payload)
      ? { status: 'ready', snapshot: payload }
      : unavailable();
  } catch {
    return unavailable();
  }
}
