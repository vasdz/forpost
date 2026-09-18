import { describe, expect, it } from 'vitest';
import { toCsv } from './csv';

describe('toCsv', () => {
  it('экранирует разделители и кавычки при экспорте', () => {
    const csv = toCsv([{ name: 'Коллектор, участок', note: 'Проверка "срочно"' }], [
      { key: 'name', label: 'Название' }, { key: 'note', label: 'Примечание' },
    ]);
    expect(csv).toBe('Название;Примечание\n"Коллектор, участок";"Проверка ""срочно"""');
  });

  it.each([
    ['=CMD()', "'=CMD()"],
    ['+SUM(A1:A2)', "'+SUM(A1:A2)"],
    ['-2+3', "'-2+3"],
    ['@SUM(A1:A2)', "'@SUM(A1:A2)"],
    ['\t=CMD()', "'\t=CMD()"],
    ['\r=CMD()', '"\'\r=CMD()"'],
    [' =CMD()', "' =CMD()"],
    ['\v+SUM(A1)', "'\v+SUM(A1)"],
    ['\u0085=CMD()', "'\u0085=CMD()"],
  ])('нейтрализует формульный префикс %j', (value, expected) => {
    const csv = toCsv([{ value }], [{ key: 'value', label: 'Значение' }]);

    expect(csv).toBe(`Значение\n${expected}`);
  });

  it('сохраняет числовые значения числами', () => {
    const csv = toCsv([{ value: -12 }], [{ key: 'value', label: 'Значение' }]);

    expect(csv).toBe('Значение\n-12');
  });
});
