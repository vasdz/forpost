'use client';

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';

import {
  fetchLocalSituation,
  type LocalSituationLoadState,
} from './localSituationClient';

const LocalSituationContext = createContext<LocalSituationLoadState>({ status: 'loading' });
const REFRESH_INTERVAL_MS = 60_000;

export function LocalSituationProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<LocalSituationLoadState>({ status: 'loading' });
  const stateRef = useRef<LocalSituationLoadState>(state);

  const updateState = (next: LocalSituationLoadState) => {
    stateRef.current = next;
    setState(next);
  };

  useEffect(() => {
    let isCurrent = true;
    let isLoading = false;
    let controller: AbortController | null = null;

    const refresh = async () => {
      if (isLoading) return;
      isLoading = true;
      controller = new AbortController();
      const previous = stateRef.current;
      if (previous.status === 'ready') {
        updateState({ ...previous, isRefreshing: true });
      }
      const result = await fetchLocalSituation(globalThis.fetch, controller.signal);
      if (isCurrent) {
        if (result.status === 'ready') {
          updateState({
            ...result,
            refreshedAt: new Date().toISOString(),
            isRefreshing: false,
            refreshError: null,
          });
        } else if (previous.status === 'ready') {
          updateState({
            ...previous,
            isRefreshing: false,
            refreshError: result.message,
          });
        } else {
          updateState(result);
        }
      }
      isLoading = false;
    };

    void refresh();
    const timer = window.setInterval(() => { void refresh(); }, REFRESH_INTERVAL_MS);
    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') void refresh();
    };
    document.addEventListener('visibilitychange', refreshWhenVisible);

    return () => {
      isCurrent = false;
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
      controller?.abort();
    };
  }, []);

  return <LocalSituationContext.Provider value={state}>{children}</LocalSituationContext.Provider>;
}

export function useLocalSituation(): LocalSituationLoadState {
  return useContext(LocalSituationContext);
}
