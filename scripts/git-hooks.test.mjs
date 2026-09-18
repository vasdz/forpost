// @vitest-environment node
import { execFileSync, spawnSync } from 'node:child_process';
import {
  chmodSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import {
  getPrePushGuardArguments,
  installHooks,
  parsePrePushUpdates,
} from './git-hooks.mjs';

const scriptsDirectory = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = resolve(scriptsDirectory, '..');
const hooksScript = join(scriptsDirectory, 'git-hooks.mjs');
const guardScript = join(scriptsDirectory, 'pre-commit-guard.mjs');

describe('versioned Git perimeter hooks', () => {
  it('checks exactly the commits being sent and skips ref deletions', () => {
    const updates = parsePrePushUpdates(
      [
        'refs/heads/main aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa refs/heads/main bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
        '(delete) 0000000000000000000000000000000000000000 refs/heads/retired cccccccccccccccccccccccccccccccccccccccc',
      ].join('\n'),
    );

    expect(getPrePushGuardArguments(updates, 'origin', () => undefined)).toEqual([
      [
        '--range',
        'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb..aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      ],
    ]);
  });

  it('uses the remote default baseline for a new branch and the full history only without one', () => {
    const updates = parsePrePushUpdates(
      [
        'refs/heads/new aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa refs/heads/new 0000000000000000000000000000000000000000',
        'refs/heads/another bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb refs/heads/another 0000000000000000000000000000000000000000',
      ].join('\n'),
    );

    expect(getPrePushGuardArguments(updates, 'origin', () => 'refs/remotes/origin/main')).toEqual([
      ['--new-branch-range', 'refs/remotes/origin/main', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'],
      ['--new-branch-range', 'refs/remotes/origin/main', 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'],
    ]);
    expect(getPrePushGuardArguments(updates, 'origin', () => undefined)).toEqual([
      ['--range', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'],
      ['--range', 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'],
    ]);
  });

  it('rejects tag and notes updates instead of silently skipping their objects', () => {
    const tagUpdate = 'refs/tags/release aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa refs/tags/release 0000000000000000000000000000000000000000';
    const notesUpdate = 'refs/notes/commits aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa refs/notes/commits 0000000000000000000000000000000000000000';

    expect(() => getPrePushGuardArguments(parsePrePushUpdates(tagUpdate), 'origin', () => undefined)).toThrow(
      /ветки refs\/heads\//,
    );
    expect(() => getPrePushGuardArguments(parsePrePushUpdates(notesUpdate), 'origin', () => undefined)).toThrow(
      /ветки refs\/heads\//,
    );
  });

  it('accepts SHA-1 and SHA-256 deletion updates explicitly and rejects malformed object ids', () => {
    const sha1Deletion = '(delete) 0000000000000000000000000000000000000000 refs/heads/old aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
    const sha256Deletion = '(delete) 0000000000000000000000000000000000000000000000000000000000000000 refs/heads/old aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
    const malformed = 'refs/heads/main not-an-object-id refs/heads/main bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';

    expect(getPrePushGuardArguments(parsePrePushUpdates(sha1Deletion), 'origin', () => undefined)).toEqual([]);
    expect(getPrePushGuardArguments(parsePrePushUpdates(sha256Deletion), 'origin', () => undefined)).toEqual([]);
    expect(() => parsePrePushUpdates(malformed)).toThrow(/object id/i);
  });

  it('blocks a staged protected path before Git can start a push', () => {
    const repositoryPath = mkdtempSync(join(tmpdir(), 'forpost-hook-'));
    const git = (...args) => execFileSync('git', args, { cwd: repositoryPath, encoding: 'utf8' });

    try {
      git('init');
      git('config', 'user.email', 'hook-test@example.invalid');
      git('config', 'user.name', 'Hook Test');
      mkdirSync(join(repositoryPath, 'scripts'));
      writeFileSync(join(repositoryPath, 'scripts', 'git-hooks.mjs'), readFileSync(hooksScript));
      writeFileSync(join(repositoryPath, 'scripts', 'pre-commit-guard.mjs'), readFileSync(guardScript));
      mkdirSync(join(repositoryPath, 'data', 'raw'), { recursive: true });
      writeFileSync(join(repositoryPath, 'data', 'raw', 'fixture.xlsx'), 'fixture');
      git('add', 'data/raw/fixture.xlsx');

      const result = spawnSync(process.execPath, [join(repositoryPath, 'scripts', 'git-hooks.mjs'), 'pre-commit'], {
        cwd: repositoryPath,
        encoding: 'utf8',
      });
      expect(result.status).toBe(1);
      expect(result.stderr).toContain('Проверка периметра данных не пройдена');
    } finally {
      rmSync(repositoryPath, { recursive: true, force: true });
    }
  });

  it('installs repository-local hooks that stop a Git commit before it is created', () => {
    const repositoryPath = mkdtempSync(join(tmpdir(), 'forpost-hook-install-'));
    const git = (...args) => execFileSync('git', args, { cwd: repositoryPath, encoding: 'utf8' });

    try {
      git('init');
      git('config', 'user.email', 'hook-install-test@example.invalid');
      git('config', 'user.name', 'Hook Install Test');
      mkdirSync(join(repositoryPath, '.githooks'));
      mkdirSync(join(repositoryPath, 'scripts'));
      writeFileSync(join(repositoryPath, 'scripts', 'git-hooks.mjs'), readFileSync(hooksScript));
      writeFileSync(join(repositoryPath, 'scripts', 'pre-commit-guard.mjs'), readFileSync(guardScript));
      for (const hookName of ['pre-commit', 'pre-push']) {
        const hookPath = join(repositoryPath, '.githooks', hookName);
        writeFileSync(hookPath, readFileSync(join(repositoryRoot, '.githooks', hookName)));
        chmodSync(hookPath, 0o755);
      }
      mkdirSync(join(repositoryPath, 'data', 'raw'), { recursive: true });
      writeFileSync(join(repositoryPath, 'data', 'raw', 'blocked.xlsx'), 'fixture');
      git('add', 'data/raw/blocked.xlsx');

      installHooks(repositoryPath);

      expect(git('config', '--local', '--get', 'core.hooksPath').trim()).toBe('.githooks');
      if (process.platform !== 'win32') {
        expect(statSync(join(repositoryPath, '.githooks', 'pre-commit')).mode & 0o111).not.toBe(0);
        expect(statSync(join(repositoryPath, '.githooks', 'pre-push')).mode & 0o111).not.toBe(0);
      }
      const commit = spawnSync('git', ['commit', '-m', 'must be blocked'], {
        cwd: repositoryPath,
        encoding: 'utf8',
      });
      expect(commit.status).toBe(1);
      expect(`${commit.stdout}${commit.stderr}`).toContain('Проверка периметра данных не пройдена');
    } finally {
      rmSync(repositoryPath, { recursive: true, force: true });
    }
  });
});
