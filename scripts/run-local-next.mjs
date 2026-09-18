import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const NEXT_CLI_PATH = fileURLToPath(new URL('../node_modules/next/dist/bin/next', import.meta.url));
const LOCAL_HOSTNAME = '127.0.0.1';

export function getLocalNextLaunch(mode, extraArguments = []) {
  if (mode !== 'dev' && mode !== 'start') {
    throw new Error('Поддерживаются только режимы Next dev или start.');
  }
  if (extraArguments.length > 0) {
    throw new Error('Произвольные аргументы launcher не допускаются.');
  }

  return {
    command: process.execPath,
    args: [NEXT_CLI_PATH, mode, '--hostname', LOCAL_HOSTNAME],
    env: {
      ...process.env,
      FORPOST_LOCAL_SNAPSHOT: '1',
    },
  };
}

export function runLocalNext(argumentsList = process.argv.slice(2)) {
  const [mode, ...extraArguments] = argumentsList;
  const launch = getLocalNextLaunch(mode, extraArguments);
  const child = spawn(launch.command, launch.args, {
    env: launch.env,
    stdio: 'inherit',
  });
  child.on('error', (error) => {
    console.error('Не удалось запустить локальный Next.js.', error);
    process.exitCode = 1;
  });
  child.on('exit', (code, signal) => {
    if (signal !== null) {
      process.exitCode = 1;
      return;
    }
    process.exitCode = code ?? 1;
  });
  return child;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  runLocalNext();
}
