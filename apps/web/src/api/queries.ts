import { useQuery } from '@tanstack/react-query';

import { getRisks } from './client';
import type { SecurityContext } from '../types';

export const useRisksQuery = (context: SecurityContext) =>
  useQuery({
    queryKey: ['risks', context.userId, context.role, context.districts.join(',')],
    queryFn: () => getRisks(context),
    staleTime: 30_000,
    retry: 1,
  });
