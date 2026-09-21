import { randomBytes } from 'node:crypto';
import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { getLocalNextLaunch } from './run-local-next.mjs';

const REPOSITORY_ROOT = fileURLToPath(new URL('../', import.meta.url));
const API_SOURCE_PATHS = [
  'apps/api/src',
  'packages/domain/src',
  'packages/prediction/src',
  'packages/connectors/src',
  'packages/platform/src',
].map((sourcePath) => path.join(REPOSITORY_ROOT, sourcePath));

function createServiceToken() {
  return randomBytes(32).toString('hex');
}

function createPythonPath(env) {
  return [...API_SOURCE_PATHS, env.PYTHONPATH].filter(Boolean).join(path.delimiter);
}

export function getLocalStackLaunches(env = process.env, extraArguments = []) {
  if (extraArguments.length > 0) {
    throw new Error('Произвольные аргументы launcher не допускаются.');
  }

  const token = createServiceToken();
  const sharedEnv = {
    ...env,
    FORPOST_API_SERVICE_TOKEN: token,
  };
  const nextLaunch = getLocalNextLaunch('dev');

  return {
    api: {
      command: 'python',
      args: ['-m', 'uvicorn', 'forpost_api.main:app', '--host', '127.0.0.1', '--port', '8000'],
      env: {
        ...sharedEnv,
        PYTHONPATH: createPythonPath(env),
      },
      label: 'FastAPI (127.0.0.1:8000)',
    },
    next: {
      ...nextLaunch,
      env: {
        ...sharedEnv,
        FORPOST_LOCAL_SNAPSHOT: nextLaunch.env.FORPOST_LOCAL_SNAPSHOT,
      },
      label: 'Next.js (127.0.0.1:3000)',
    },
  };
}

function spawnLaunch(launch) {
  return spawn(launch.command, launch.args, {
    env: launch.env,
    stdio: 'inherit',
  });
}

export function runLocalStack(argumentsList = process.argv.slice(2)) {
  const launches = getLocalStackLaunches(process.env, argumentsList);
  const api = spawnLaunch(launches.api);
  const next = spawnLaunch(launches.next);
  let stopping = false;

  function stopSibling(sibling, code, signal) {
    if (stopping) return;
    stopping = true;
    if (sibling.exitCode === null && !sibling.killed) {
      sibling.kill('SIGTERM');
    }
    process.exitCode = signal === null ? (code ?? 1) : 1;
  }

  api.on('error', (error) => {
    console.error(`Не удалось запустить ${launches.api.label}.`, error);
    stopSibling(next, 1, null);
  });
  next.on('error', (error) => {
    console.error(`Не удалось запустить ${launches.next.label}.`, error);
    stopSibling(api, 1, null);
  });
  api.on('exit', (code, signal) => stopSibling(next, code, signal));
  next.on('exit', (code, signal) => stopSibling(api, code, signal));

  return { api, next };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  runLocalStack();
}
