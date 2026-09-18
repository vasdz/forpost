// @vitest-environment node
import { readFileSync } from 'node:fs';
import yaml from 'js-yaml';
import { describe, expect, it } from 'vitest';

describe('semgrep.yml', () => {
  it('is valid YAML with root-only data exclusions on every local rule', () => {
    const config = yaml.load(readFileSync('semgrep.yml', 'utf8'));

    expect(config).toMatchObject({ rules: expect.any(Array) });
    expect(config.rules).not.toHaveLength(0);
    config.rules.forEach((rule) => {
      expect(rule.paths.exclude).toEqual(
        expect.arrayContaining([
          '/data/**',
          '**/node_modules/**',
          '**/.next/**',
          '**/references/**',
        ]),
      );
    });
  });

  it('uses the supported JSX sink pattern and keeps regression fixtures', () => {
    const config = yaml.load(readFileSync('semgrep.yml', 'utf8'));
    const sinkRule = config.rules.find(
      (rule) => rule.id === 'javascript-no-dangerously-set-inner-html',
    );

    expect(sinkRule?.pattern).toBe('<$ELEMENT dangerouslySetInnerHTML={$VALUE} ... />');
    expect(
      readFileSync('scripts/fixtures/semgrep/unsafe-inner-html.tsx', 'utf8'),
    ).toContain('dangerouslySetInnerHTML');
    expect(
      readFileSync('scripts/fixtures/semgrep/safe-text.tsx', 'utf8'),
    ).not.toContain('dangerouslySetInnerHTML');
  });
});
