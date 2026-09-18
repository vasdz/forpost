// @vitest-environment node
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

const productionRoots = ['src/app', 'src/components', 'src/data', 'src/hooks', 'src/stores'];
const forbiddenReferences = [
  '@/mocks',
  '/mocks/',
  'situationRepository',
  'mockDatabase',
  'generateMockData',
  'DATA_NOW',
];

function productionFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      return productionFiles(path);
    }
    return /\.(?:ts|tsx)$/.test(entry.name) && !/\.test\.(?:ts|tsx)$/.test(entry.name) ? [path] : [];
  });
}

describe('граф production-кода', () => {
  it('не содержит генераторов и репозитория искусственных данных', () => {
    const source = productionRoots.flatMap(productionFiles)
      .map((path) => ({ path, content: readFileSync(path, 'utf8') }));
    const violations = source.flatMap(({ path, content }) => forbiddenReferences
      .filter((reference) => content.includes(reference))
      .map((reference) => `${path}: ${reference}`));

    expect(existsSync('src/mocks')).toBe(false);
    expect(violations).toEqual([]);
  });

  it('соблюдает плоский интерфейс SPEC без стекла и blur', () => {
    const files = productionRoots.flatMap(productionFiles)
      .map((path) => ({ path, content: readFileSync(path, 'utf8') }));
    const forbiddenStyles = ['glass-surface', 'backdrop-blur', 'backdrop-filter'];
    const violations = files.flatMap(({ path, content }) => forbiddenStyles
      .filter((style) => content.includes(style))
      .map((style) => `${path}: ${style}`));

    expect(violations).toEqual([]);
  });
});
