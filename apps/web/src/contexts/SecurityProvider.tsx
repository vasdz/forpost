import React, { useState } from 'react';
import type { SecurityContext as SecType } from '../types';
import { SecurityCtx } from './security';

const PREDEFINED: SecType[] = [
  { userId: 'disp-01', label: 'Диспетчер РЭК-1', role: 'dispatcher', districts: ['rek-1', 'rek-2'] },
  { userId: 'disp-03', label: 'Диспетчер РЭК-3', role: 'dispatcher', districts: ['rek-3'] },
  { userId: 'aud-01', label: 'Офицер ИБ', role: 'auditor', districts: ['rek-1', 'rek-2', 'rek-3', 'rek-4'] },
];

export const SecurityProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [index, setIndex] = useState<number>(0);
  const [contexts] = useState<SecType[]>(PREDEFINED);

  const value = {
    context: contexts[index],
    contexts,
    setContextIndex: (i: number) => setIndex(i),
  };

  return <SecurityCtx.Provider value={value}>{children}</SecurityCtx.Provider>;
};
