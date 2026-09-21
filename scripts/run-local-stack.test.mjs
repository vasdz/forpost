// @vitest-environment node
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { getLocalStackLaunches } from './run-local-stack.mjs';

describe('локальный стек', () => {
  it('запускает API и Next.js только на loopback с общим service token', () => {
    const launches = getLocalStackLaunches({ PATH: process.env.PATH ?? '' });

    expect(launches.api.command).toBe('python');
    expect(launches.api.args).toEqual([
      '-m',
      'uvicorn',
      'forpost_api.main:app',
      '--host',
      '127.0.0.1',
      '--port',
      '8000',
    ]);
    expect(launches.next.args).toContain('--hostname');
    expect(launches.next.args).toContain('127.0.0.1');
    expect(launches.api.env.FORPOST_API_SERVICE_TOKEN).toHaveLength(64);
    expect(launches.next.env.FORPOST_API_SERVICE_TOKEN).toBe(
      launches.api.env.FORPOST_API_SERVICE_TOKEN,
    );
  });

  it('передаёт API исходные Python-пути репозитория', () => {
    const launches = getLocalStackLaunches({ PATH: process.env.PATH ?? '' });
    const pythonPaths = launches.api.env.PYTHONPATH.split(path.delimiter);

    expect(pythonPaths).toEqual(
      expect.arrayContaining([
        path.resolve('apps/api/src'),
        path.resolve('packages/domain/src'),
        path.resolve('packages/prediction/src'),
        path.resolve('packages/connectors/src'),
        path.resolve('packages/platform/src'),
      ]),
    );
  });

  it('не раскрывает service token в отображаемых подписях запусков', () => {
    const launches = getLocalStackLaunches({ PATH: process.env.PATH ?? '' });
    const token = launches.api.env.FORPOST_API_SERVICE_TOKEN;

    expect(launches.api.label).not.toContain(token);
    expect(launches.next.label).not.toContain(token);
  });

  it('отклоняет произвольные аргументы launcher', () => {
    expect(() => getLocalStackLaunches({}, ['--host', '0.0.0.0'])).toThrow(/аргументы/i);
  });
});
