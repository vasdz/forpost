import { describe, expect, it } from 'vitest';

import { getPageName, getSourceLabel } from './Header';

describe('getPageName', () => {
  it('возвращает известное имя раздела и безопасное имя для неизвестного пути', () => {
    expect(getPageName('/sensor-failure')).toBe('Отказ датчика');
    expect(getPageName('/untrusted-path')).toBe('Раздел');
  });
});

describe('getSourceLabel', () => {
  it('показывает исторический режим и ошибку фонового обновления', () => {
    expect(getSourceLabel('ready', 'historical', false, null)).toBe('Исторический источник');
    expect(getSourceLabel('ready', 'historical', true, null)).toBe('Обновление снимка');
    expect(getSourceLabel('ready', 'historical', false, 'error')).toBe('Исторический источник · обновление недоступно');
  });
});
