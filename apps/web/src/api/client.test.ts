import { describe, expect, it } from 'vitest';

import { getAvailabilityMessage } from './availability';

describe('getAvailabilityMessage', () => {
  it('extracts the Russian availability message instead of treating a 503 response as data', () => {
    const responseData = {
      detail: {
        code: 'REAL_DATA_INTEGRATION_UNAVAILABLE',
        message: 'Интеграция с реальными данными и обученной моделью пока недоступна.',
      },
    };

    expect(getAvailabilityMessage(responseData)).toBe(
      'Интеграция с реальными данными и обученной моделью пока недоступна.',
    );
  });

  it('does not reinterpret an arbitrary response as the availability contract', () => {
    expect(
      getAvailabilityMessage({
        detail: {
          code: 'UNRELATED_ERROR',
          message: 'Неизвестная ошибка.',
        },
      }),
    ).toBeNull();
  });
});
