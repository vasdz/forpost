// @vitest-environment node
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

import { getLocalNextLaunch } from './run-local-next.mjs';

function isIgnoredByGit(path) {
  return spawnSync(
    'git',
    ['check-ignore', '-q', '--no-index', '--', path],
    { encoding: 'utf8' },
  ).status === 0;
}

describe('локальный периметр Next.js', () => {
  it('не запускает dev и start на всех сетевых интерфейсах', () => {
    const packageJson = JSON.parse(readFileSync('package.json', 'utf8'));

    expect(packageJson.scripts.dev).toBe('node scripts/run-local-next.mjs dev');
    expect(packageJson.scripts.start).toBe('node scripts/run-local-next.mjs start');
  });

  it('запускает Next только на loopback и включает локальный режим маршрута', () => {
    const launch = getLocalNextLaunch('dev');

    expect(launch.args).toContain('--hostname');
    expect(launch.args).toContain('127.0.0.1');
    expect(launch.env.FORPOST_LOCAL_SNAPSHOT).toBe('1');
  });

  it('не принимает произвольный режим Next или аргументы launcher', () => {
    expect(() => getLocalNextLaunch('build')).toThrow(/dev или start/i);
    expect(() => getLocalNextLaunch('dev', ['--hostname', '0.0.0.0'])).toThrow(/аргументы/i);
  });

  it('игнорирует только корневой каталог данных, а не код src/data', () => {
    expect(isIgnoredByGit('data/raw/perimeter-marker.csv')).toBe(true);
    expect(isIgnoredByGit('src/data/localSituation.ts')).toBe(false);
  });

  it('исключает корневые данные из TruffleHog на Windows и не исключает src/data', () => {
    const exclusions = readFileSync('.trufflehog-exclude', 'utf8').trim().split(/\r?\n/);
    const dataRule = exclusions.find((rule) => rule.includes('data'));

    expect(dataRule).toBe('^(?:data|node_modules|\\.next|references|\\.venv|coverage|out|\\.worktrees|\\.superpowers|tmp)(?:[\\\\/]|$)');
    const matcher = /^(?:data|node_modules|\.next|references|\.venv|coverage|out|\.worktrees|\.superpowers|tmp)(?:[\\/]|$)/;
    expect(matcher.test('data\\raw\\perimeter-marker.csv')).toBe(true);
    expect(matcher.test('data/raw/perimeter-marker.csv')).toBe(true);
    expect(matcher.test('src\\data\\localSituation.ts')).toBe(false);
  });
});
