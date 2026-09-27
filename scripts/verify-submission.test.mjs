// @vitest-environment node
import { describe, expect, it } from 'vitest';

import { getSubmissionChecks, resolveCheckCommand, resolvePythonExecutable } from './verify-submission.mjs';

describe('getSubmissionChecks', () => {
  it('composes the local offline reviewer checks without scanning local data', () => {
    expect(getSubmissionChecks('python')).toEqual([
      { command: 'node', args: ['scripts/pre-commit-guard.mjs'] },
      { command: 'node', args: ['scripts/pre-commit-guard.mjs', '--tracked'] },
      { command: 'npm', args: ['run', 'typecheck'] },
      { command: 'npm', args: ['run', 'lint'] },
      { command: 'npm', args: ['test'] },
      { command: 'npm', args: ['run', 'build'] },
      { command: 'python', args: ['-m', 'pytest', 'tests', '-q'] },
      { command: 'python', args: ['-m', 'ruff', 'check', '.'] },
      { command: 'python', args: ['-m', 'ruff', 'format', '--check', '.'] },
      { command: 'python', args: ['-m', 'bandit', '-r', 'apps', 'packages', 'scripts', '-c', '.bandit.yaml'] },
      { command: 'python', args: ['scripts/load_check.py', '--users', '20', '--requests-per-user', '5'] },
    ]);
  });
});

describe('resolveCheckCommand', () => {
  it('runs npm through cmd.exe on Windows because npm is a command shim', () => {
    expect(
      resolveCheckCommand(
        { command: 'npm', args: ['run', 'typecheck'] },
        'win32',
        'C:\\Windows\\System32\\cmd.exe',
        'C:\\Program Files\\nodejs\\node.exe',
        'C:\\missing\\npm-cli.js',
      ),
    ).toEqual({
      command: 'C:\\Windows\\System32\\cmd.exe',
      args: ['/d', '/s', '/c', 'npm run typecheck'],
    });
  });

  it('calls the npm CLI directly on Windows when it is available', () => {
    expect(
      resolveCheckCommand(
        { command: 'npm', args: ['run', 'typecheck'] },
        'win32',
        'C:\\Windows\\System32\\cmd.exe',
        'C:\\Program Files\\nodejs\\node.exe',
        'C:\\Program Files\\nodejs\\node_modules\\npm\\bin\\npm-cli.js',
        (candidate) => candidate.endsWith('npm-cli.js'),
      ),
    ).toEqual({
      command: 'C:\\Program Files\\nodejs\\node.exe',
      args: ['C:\\Program Files\\nodejs\\node_modules\\npm\\bin\\npm-cli.js', 'run', 'typecheck'],
    });
  });

  it('keeps direct executable invocation on POSIX', () => {
    expect(
      resolveCheckCommand({ command: 'npm', args: ['run', 'typecheck'] }, 'linux'),
    ).toEqual({ command: 'npm', args: ['run', 'typecheck'] });
  });
});

describe('resolvePythonExecutable', () => {
  it('prefers the project virtual environment over a system Python', () => {
    expect(
      resolvePythonExecutable(
        'C:\\repository',
        'win32',
        {},
        (candidate) => candidate === 'C:\\repository\\.venv\\Scripts\\python.exe',
      ),
    ).toBe('C:\\repository\\.venv\\Scripts\\python.exe');
  });
});
