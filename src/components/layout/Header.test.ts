import { describe, expect, it } from 'vitest';

import { getPageName } from './Header';

describe('getPageName', () => {
  it('возвращает известное имя раздела и безопасное имя для неизвестного пути', () => {
    expect(getPageName('/sensor-failure')).toBe('Отказ датчика');
    expect(getPageName('/untrusted-path')).toBe('Раздел');
  });
});
