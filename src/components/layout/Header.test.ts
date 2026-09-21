import { describe, expect, it } from 'vitest';

import { getModelLabel, getPageName, getSourceLabel } from './Header';

describe('getPageName', () => {
  it('возвращает известное имя раздела и безопасное имя для неизвестного пути', () => {
    expect(getPageName('/sensor-failure')).toBe('Отказ датчика');
    expect(getPageName('/topology')).toBe('Схема объектов');
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

describe('getModelLabel', () => {
  it('не противоречит фактической доступности проверенного экспорта', () => {
    expect(getModelLabel('loading')).toBe('ML-модель: проверка');
    expect(getModelLabel('ready')).toBe('ML-модель: доступна');
    expect(getModelLabel('unavailable')).toBe('ML-модель: недоступна');
  });
});
