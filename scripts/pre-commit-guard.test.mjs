// @vitest-environment node
import { execFileSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import {
  findGuardViolations,
  getChangedPathsFromEntries,
  getChangedFiles,
  getNewBranchRange,
  getStagedFiles,
} from './pre-commit-guard.mjs';

describe('findGuardViolations', () => {
  it('allows ordinary staged files outside the protected directory', () => {
    expect(
      findGuardViolations([
        { path: 'src/mocks/objects.ts', size: 128 },
      ]),
    ).toEqual([]);
  });

  it('allows only the repository data README and blocks every other staged data file', () => {
    expect(
      findGuardViolations([
        { path: 'data/README.md', size: 128 },
        { path: 'data/raw/events.xlsx', size: 128 },
      ]),
    ).toEqual([
      'Запрещено добавлять в индекс файл данных: data/raw/events.xlsx',
    ]);
  });

  it('blocks Windows case variants of protected data paths', () => {
    expect(
      findGuardViolations([
        { path: 'Data/raw/events.xlsx', size: 128 },
        { path: 'data/readme.md', size: 128 },
      ]),
    ).toEqual([
      'Запрещено добавлять в индекс файл данных: Data/raw/events.xlsx',
      'Запрещено добавлять в индекс файл данных: data/readme.md',
    ]);
  });

  it('blocks common source-data exports outside the protected directory', () => {
    expect(
      findGuardViolations([
        { path: 'exports/current.xlsx', size: 128 },
        { path: 'archive/history.CSV', size: 128 },
        { path: 'exports/current.xlsm', size: 128 },
        { path: 'exports/current.ods', size: 128 },
        { path: 'archive/raw.rar', size: 128 },
        { path: 'archive/raw.tar.gz', size: 128 },
        { path: 'archive/observations.csv.gz', size: 128 },
        { path: 'docs/diagram.svg', size: 128 },
      ]),
    ).toEqual([
      'Запрещено добавлять потенциальную выгрузку данных вне data/: exports/current.xlsx',
      'Запрещено добавлять потенциальную выгрузку данных вне data/: archive/history.CSV',
      'Запрещено добавлять потенциальную выгрузку данных вне data/: exports/current.xlsm',
      'Запрещено добавлять потенциальную выгрузку данных вне data/: exports/current.ods',
      'Запрещено добавлять потенциальную выгрузку данных вне data/: archive/raw.rar',
      'Запрещено добавлять потенциальную выгрузку данных вне data/: archive/raw.tar.gz',
      'Запрещено добавлять потенциальную выгрузку данных вне data/: archive/observations.csv.gz',
    ]);
  });

  it('blocks any staged file larger than five million bytes', () => {
    expect(
      findGuardViolations([
        { path: 'docs/export.bin', size: 5_000_001 },
        { path: 'docs/limit.bin', size: 5_000_000 },
      ]),
    ).toEqual(['Размер staged-файла превышает 5 MB: docs/export.bin']);
  });
});

describe('разбор вывода Git для push-проверки', () => {
  it('извлекает исходный и конечный путь переименования и отклоняет неполную запись', () => {
    expect(
      getChangedPathsFromEntries([
        'A',
        'src/safe.ts',
        'R100',
        'src/old.xlsx',
        'data/raw/renamed.xlsx',
      ]),
    ).toEqual(['src/safe.ts', 'src/old.xlsx', 'data/raw/renamed.xlsx']);

    expect(() => getChangedPathsFromEntries(['R100', 'src/old.xlsx'])).toThrow(
      /неполную запись/i,
    );
  });
});

describe('Git index and revision range integration', () => {
  it('checks staged additions, ignores unstaged files, detects renames, and ignores deletions', () => {
    const repositoryPath = mkdtempSync(join(tmpdir(), 'forpost-guard-'));
    const git = (...args) => execFileSync('git', args, { cwd: repositoryPath, encoding: 'utf8' });

    try {
      git('init');
      git('config', 'user.email', 'guard-test@example.invalid');
      git('config', 'user.name', 'Guard Test');
      mkdirSync(join(repositoryPath, 'src'));
      writeFileSync(join(repositoryPath, 'src', 'rename.txt'), 'safe');
      git('add', '.');
      git('commit', '-m', 'initial');

      writeFileSync(join(repositoryPath, 'src', 'staged.txt'), 'staged');
      mkdirSync(join(repositoryPath, 'data', 'raw'), { recursive: true });
      writeFileSync(join(repositoryPath, 'data', 'raw', 'unstaged.xlsx'), 'not staged');
      git('add', 'src/staged.txt');
      expect(getStagedFiles(repositoryPath).map(({ path }) => path)).toEqual(['src/staged.txt']);

      renameSync(join(repositoryPath, 'src', 'rename.txt'), join(repositoryPath, 'data', 'raw', 'renamed.xlsx'));
      git('add', '-A', '--', 'src/rename.txt', 'data/raw/renamed.xlsx');
      git('commit', '-m', 'rename into protected directory');
      expect(findGuardViolations(getChangedFiles('HEAD~1..HEAD', repositoryPath))).toEqual([
        'Запрещено добавлять в индекс файл данных: data/raw/renamed.xlsx',
      ]);

      rmSync(join(repositoryPath, 'data', 'raw', 'renamed.xlsx'));
      git('add', '-u');
      git('commit', '-m', 'delete protected file');
      expect(getChangedFiles('HEAD~1..HEAD', repositoryPath)).toEqual([]);
    } finally {
      rmSync(repositoryPath, { recursive: true, force: true });
    }
  });

  it('blocks a protected path that is renamed out of data in pushed history', () => {
    const repositoryPath = mkdtempSync(join(tmpdir(), 'forpost-rename-out-'));
    const git = (...args) => execFileSync('git', args, { cwd: repositoryPath, encoding: 'utf8' });

    try {
      git('init', '--initial-branch=main');
      git('config', 'user.email', 'guard-test@example.invalid');
      git('config', 'user.name', 'Guard Test');
      mkdirSync(join(repositoryPath, 'data', 'raw'), { recursive: true });
      writeFileSync(join(repositoryPath, 'data', 'raw', 'protected.xlsx'), 'fixture');
      git('add', 'data/raw/protected.xlsx');
      git('commit', '-m', 'protected source added');

      mkdirSync(join(repositoryPath, 'docs'));
      renameSync(
        join(repositoryPath, 'data', 'raw', 'protected.xlsx'),
        join(repositoryPath, 'docs', 'renamed-export.xlsx'),
      );
      git('add', '-A');
      git('commit', '-m', 'protected source renamed out');

      expect(findGuardViolations(getChangedFiles('HEAD~1..HEAD', repositoryPath))).toEqual([
        'Запрещено добавлять в индекс файл данных: data/raw/protected.xlsx',
        'Запрещено добавлять потенциальную выгрузку данных вне data/: docs/renamed-export.xlsx',
      ]);
    } finally {
      rmSync(repositoryPath, { recursive: true, force: true });
    }
  });

  it('covers every commit of a newly pushed branch when its first commit is prohibited', () => {
    const repositoryPath = mkdtempSync(join(tmpdir(), 'forpost-new-branch-'));
    const git = (...args) => execFileSync('git', args, { cwd: repositoryPath, encoding: 'utf8' });

    try {
      git('init', '--initial-branch=main');
      git('config', 'user.email', 'guard-test@example.invalid');
      git('config', 'user.name', 'Guard Test');
      writeFileSync(join(repositoryPath, 'README.md'), 'base');
      git('add', 'README.md');
      git('commit', '-m', 'base');
      git('switch', '-c', 'feature/new-branch');

      mkdirSync(join(repositoryPath, 'data', 'raw'), { recursive: true });
      writeFileSync(join(repositoryPath, 'data', 'raw', 'first-commit.xlsx'), 'fixture');
      git('add', 'data/raw/first-commit.xlsx');
      git('commit', '-m', 'first feature commit');
      writeFileSync(join(repositoryPath, 'README.md'), 'feature tip');
      git('add', 'README.md');
      git('commit', '-m', 'second feature commit');

      const revisionRange = getNewBranchRange('main', 'HEAD', repositoryPath);
      expect(findGuardViolations(getChangedFiles(revisionRange, repositoryPath))).toEqual([
        'Запрещено добавлять в индекс файл данных: data/raw/first-commit.xlsx',
      ]);
    } finally {
      rmSync(repositoryPath, { recursive: true, force: true });
    }
  });

  it('detects a protected file added and deleted within the pushed range', () => {
    const repositoryPath = mkdtempSync(join(tmpdir(), 'forpost-history-guard-'));
    const git = (...args) => execFileSync('git', args, { cwd: repositoryPath, encoding: 'utf8' });

    try {
      git('init', '--initial-branch=main');
      git('config', 'user.email', 'guard-test@example.invalid');
      git('config', 'user.name', 'Guard Test');
      writeFileSync(join(repositoryPath, 'README.md'), 'base');
      git('add', 'README.md');
      git('commit', '-m', 'base');

      mkdirSync(join(repositoryPath, 'data', 'raw'), { recursive: true });
      writeFileSync(join(repositoryPath, 'data', 'raw', 'transient.xlsx'), 'fixture');
      git('add', 'data/raw/transient.xlsx');
      git('commit', '-m', 'add transient protected file');
      rmSync(join(repositoryPath, 'data', 'raw', 'transient.xlsx'));
      git('add', '-u');
      git('commit', '-m', 'delete transient protected file');

      expect(findGuardViolations(getChangedFiles('HEAD~2..HEAD', repositoryPath))).toEqual([
        'Запрещено добавлять в индекс файл данных: data/raw/transient.xlsx',
      ]);
    } finally {
      rmSync(repositoryPath, { recursive: true, force: true });
    }
  });

  it('scans a root push when the default-branch revision already equals its head', () => {
    const repositoryPath = mkdtempSync(join(tmpdir(), 'forpost-root-guard-'));
    const git = (...args) => execFileSync('git', args, { cwd: repositoryPath, encoding: 'utf8' });

    try {
      git('init', '--initial-branch=main');
      git('config', 'user.email', 'guard-test@example.invalid');
      git('config', 'user.name', 'Guard Test');
      mkdirSync(join(repositoryPath, 'data', 'raw'), { recursive: true });
      writeFileSync(join(repositoryPath, 'data', 'raw', 'root.xlsx'), 'fixture');
      git('add', 'data/raw/root.xlsx');
      git('commit', '-m', 'root protected file');

      const revisionRange = getNewBranchRange('HEAD', 'HEAD', repositoryPath);
      expect(findGuardViolations(getChangedFiles(revisionRange, repositoryPath))).toEqual([
        'Запрещено добавлять в индекс файл данных: data/raw/root.xlsx',
      ]);
    } finally {
      rmSync(repositoryPath, { recursive: true, force: true });
    }
  });

  it('scans all reachable commits when the default branch cannot be resolved', () => {
    const repositoryPath = mkdtempSync(join(tmpdir(), 'forpost-missing-default-guard-'));
    const git = (...args) => execFileSync('git', args, { cwd: repositoryPath, encoding: 'utf8' });

    try {
      git('init', '--initial-branch=main');
      git('config', 'user.email', 'guard-test@example.invalid');
      git('config', 'user.name', 'Guard Test');
      writeFileSync(join(repositoryPath, 'README.md'), 'base');
      git('add', 'README.md');
      git('commit', '-m', 'base');
      mkdirSync(join(repositoryPath, 'data', 'raw'), { recursive: true });
      writeFileSync(join(repositoryPath, 'data', 'raw', 'unreachable-default.xlsx'), 'fixture');
      git('add', 'data/raw/unreachable-default.xlsx');
      git('commit', '-m', 'protected file');
      writeFileSync(join(repositoryPath, 'README.md'), 'tip');
      git('add', 'README.md');
      git('commit', '-m', 'safe tip');

      const revisionRange = getNewBranchRange('missing-default-ref', 'HEAD', repositoryPath);
      expect(findGuardViolations(getChangedFiles(revisionRange, repositoryPath))).toEqual([
        'Запрещено добавлять в индекс файл данных: data/raw/unreachable-default.xlsx',
      ]);
    } finally {
      rmSync(repositoryPath, { recursive: true, force: true });
    }
  });
});
