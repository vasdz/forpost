import axios from 'axios';

import type {
  AuditVerifyResponse,
  MaintenanceGenerationResponse,
  MaintenanceOrder,
  RiskPrediction,
  SecurityContext,
} from '../types';

export const api = axios.create({
  baseURL: '/api/v1',
  timeout: 12000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const buildContextHeaders = (context: SecurityContext): Record<string, string> => ({
  'x-user-id': context.userId,
  'x-role': context.role,
  'x-districts': context.districts.join(','),
});

export const getRisks = async (context: SecurityContext): Promise<RiskPrediction[]> => {
  const response = await api.get<RiskPrediction[]>('/risks', {
    headers: buildContextHeaders(context),
  });

  return response.data;
};

export const verifyAuditChain = async (
  context: SecurityContext,
): Promise<AuditVerifyResponse> => {
  const response = await api.get<AuditVerifyResponse>('/risks/audit/verify', {
    headers: buildContextHeaders(context),
  });

  return response.data;
};

export const getMaintenanceOrders = async (
  context: SecurityContext,
): Promise<MaintenanceOrder[]> => {
  const response = await api.get<MaintenanceOrder[]>('/maintenance', {
    headers: buildContextHeaders(context),
  });

  return response.data;
};

export const generateMaintenanceOrders = async (
  context: SecurityContext,
  autoApprove: boolean = false,
): Promise<MaintenanceGenerationResponse> => {
  const response = await api.post<MaintenanceGenerationResponse>(
    '/maintenance/generate-from-prediction',
    {
      risk_prediction_ids: [],
      auto_approve: autoApprove,
    },
    {
      headers: buildContextHeaders(context),
    },
  );

  return response.data;
};

export const formatError = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    return error.response?.data?.detail ?? error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return 'Неизвестная ошибка';
};
