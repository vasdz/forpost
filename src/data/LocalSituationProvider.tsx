'use client';

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

import {
  fetchLocalSituation,
  type LocalSituationLoadState,
} from './localSituationClient';

const LocalSituationContext = createContext<LocalSituationLoadState>({ status: 'loading' });

export function LocalSituationProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<LocalSituationLoadState>({ status: 'loading' });

  useEffect(() => {
    let isCurrent = true;

    void fetchLocalSituation().then((nextState) => {
      if (isCurrent) {
        setState(nextState);
      }
    });

    return () => {
      isCurrent = false;
    };
  }, []);

  return <LocalSituationContext.Provider value={state}>{children}</LocalSituationContext.Provider>;
}

export function useLocalSituation(): LocalSituationLoadState {
  return useContext(LocalSituationContext);
}
