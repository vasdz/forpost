import { useContext } from 'react';
import { createContext } from 'react';
import type { SecurityContext as SecType } from '../types';

interface ProviderValue {
  context: SecType;
  contexts: SecType[];
  setContextIndex: (i: number) => void;
}

export const SecurityCtx = createContext<ProviderValue | undefined>(undefined);

export const useSecurityContext = () => {
  const ctx = useContext(SecurityCtx);
  if (!ctx) throw new Error('useSecurityContext must be used within SecurityProvider');
  return ctx;
};
