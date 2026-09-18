export const REAL_DATA_INTEGRATION_UNAVAILABLE_CODE = 'REAL_DATA_INTEGRATION_UNAVAILABLE';
export const REAL_DATA_INTEGRATION_UNAVAILABLE_MESSAGE =
  'Интеграция с реальными данными и обученной моделью пока недоступна.';

interface AvailabilityDetail {
  code: string;
  message: string;
}

const isAvailabilityDetail = (value: unknown): value is AvailabilityDetail => {
  if (typeof value !== 'object' || value === null) return false;

  const detail = value as Record<string, unknown>;
  return (
    detail.code === REAL_DATA_INTEGRATION_UNAVAILABLE_CODE &&
    typeof detail.message === 'string'
  );
};

export const getAvailabilityMessage = (responseData: unknown): string | null => {
  if (typeof responseData !== 'object' || responseData === null) return null;

  const response = responseData as Record<string, unknown>;
  return isAvailabilityDetail(response.detail) ? response.detail.message : null;
};
