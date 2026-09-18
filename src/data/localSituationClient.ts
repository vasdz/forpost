import {
  isLocalSituationSnapshot,
  type LocalSituationSnapshot,
} from './localSituationContract';

const unavailableMessage = 'Локальный снимок данных недоступен.';

export type LocalSituationLoadState =
  | { status: 'loading' }
  | {
    status: 'ready';
    snapshot: LocalSituationSnapshot;
    refreshedAt: string;
    isRefreshing: boolean;
    refreshError: string | null;
  }
  | { status: 'unavailable'; message: string };

export type LocalSituationFetchResult =
  | { status: 'ready'; snapshot: LocalSituationSnapshot }
  | { status: 'unavailable'; message: string };

export type LocalSituationFetcher = (
  input: string,
  init: RequestInit,
) => Promise<Response>;

function unavailable(): LocalSituationFetchResult {
  return { status: 'unavailable', message: unavailableMessage };
}

export async function fetchLocalSituation(
  fetcher: LocalSituationFetcher = globalThis.fetch,
  signal?: AbortSignal,
): Promise<LocalSituationFetchResult> {
  try {
    const init: RequestInit = {
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    };
    if (signal !== undefined) {
      init.signal = signal;
    }
    const response = await fetcher('/api/local-situation', init);
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
