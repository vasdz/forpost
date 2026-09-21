// @vitest-environment node
import path from 'node:path';
import { EventEmitter } from 'node:events';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const childProcess = vi.hoisted(() => ({ spawn: vi.fn() }));

vi.mock('node:child_process', () => ({ spawn: childProcess.spawn }));

import { getLocalNextLaunch } from './run-local-next.mjs';
import { getLocalStackLaunches, runLocalStack } from './run-local-stack.mjs';

function createChild() {
  const child = new EventEmitter();
  child.exitCode = null;
  child.killed = false;
  child.kill = vi.fn((signal) => {
    child.killed = true;
    return signal;
  });
  return child;
}

let children;
let originalExitCode;
const originalPlatform = process.platform;

beforeEach(() => {
  Object.defineProperty(process, 'platform', { value: 'linux' });
  originalExitCode = process.exitCode;
  process.exitCode = undefined;
  children = [createChild(), createChild()];
  childProcess.spawn.mockReset();
  childProcess.spawn
    .mockImplementationOnce(() => children[0])
    .mockImplementationOnce(() => children[1]);
});

afterEach(() => {
  Object.defineProperty(process, 'platform', { value: originalPlatform });
  process.exitCode = originalExitCode;
});

describe('локальный стек', () => {
  it('на Windows завершает принадлежащее launcher дерево через PID без shell и секрета', () => {
    Object.defineProperty(process, 'platform', { value: 'win32' });
    children[0].pid = 1001;
    children[1].pid = 1002;
    childProcess.spawn.mockImplementation(() => createChild());
    const launches = runLocalStack([]);

    process.emit('SIGTERM');

    expect(launches.api.kill).not.toHaveBeenCalled();
    expect(launches.next.kill).not.toHaveBeenCalled();
    expect(childProcess.spawn).toHaveBeenNthCalledWith(3, 'taskkill', ['/PID', '1001', '/T', '/F'], {
      stdio: 'ignore', windowsHide: true, shell: false,
    });
    expect(childProcess.spawn).toHaveBeenNthCalledWith(4, 'taskkill', ['/PID', '1002', '/T', '/F'], {
      stdio: 'ignore', windowsHide: true, shell: false,
    });
    expect(process.exitCode).toBe(143);
  });

  it('на Windows завершает дерево Next после выхода API', () => {
    Object.defineProperty(process, 'platform', { value: 'win32' });
    children[1].pid = 2002;
    childProcess.spawn.mockImplementation(() => createChild());
    const launches = runLocalStack([]);
    launches.api.emit('exit', 1, null);
    expect(childProcess.spawn.mock.calls.filter(([command]) => command === 'taskkill')).toEqual([
      ['taskkill', ['/PID', '2002', '/T', '/F'], { stdio: 'ignore', windowsHide: true, shell: false }],
    ]);
  });
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

  it('изолирует окружение Next.js от глобального process.env', () => {
    const launch = getLocalNextLaunch('dev', [], { ONLY_INJECTED: 'yes' });

    expect(launch.env).toEqual({
      ONLY_INJECTED: 'yes',
      FORPOST_LOCAL_SNAPSHOT: '1',
    });
  });

  it('запускает оба дочерних процесса и завершает Next.js после выхода API', () => {
    const launches = runLocalStack([]);

    expect(childProcess.spawn).toHaveBeenNthCalledWith(
      1,
      'python',
      expect.arrayContaining(['-m', 'uvicorn', '--host', '127.0.0.1']),
      expect.objectContaining({ stdio: 'inherit' }),
    );
    expect(childProcess.spawn).toHaveBeenNthCalledWith(
      2,
      process.execPath,
      expect.arrayContaining(['dev', '--hostname', '127.0.0.1']),
      expect.objectContaining({ stdio: 'inherit' }),
    );

    launches.api.emit('exit', 0, null);

    expect(launches.next.kill).toHaveBeenCalledWith('SIGTERM');
    expect(process.exitCode).toBe(0);
  });

  it('завершает sibling и возвращает ошибку при ошибке запуска API', () => {
    const launches = runLocalStack([]);
    const error = new Error('python unavailable');
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

    launches.api.emit('error', error);

    expect(launches.next.kill).toHaveBeenCalledWith('SIGTERM');
    expect(process.exitCode).toBe(1);
    consoleError.mockRestore();
  });

  it.each([
    ['SIGINT', 130],
    ['SIGTERM', 143],
  ])('однократно завершает оба процесса при сигнале %s', (signal, exitCode) => {
    const launches = runLocalStack([]);

    process.emit(signal);
    process.emit(signal);
    launches.api.emit('exit', 1, null);

    expect(launches.api.kill).toHaveBeenCalledOnce();
    expect(launches.next.kill).toHaveBeenCalledOnce();
    expect(launches.api.kill).toHaveBeenCalledWith(signal);
    expect(launches.next.kill).toHaveBeenCalledWith(signal);
    expect(process.exitCode).toBe(exitCode);
  });
});
