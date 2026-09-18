import { execFileSync, spawnSync } from 'node:child_process';
import { chmodSync, existsSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const OBJECT_ID_PATTERN = /^(?:[0-9a-f]{40}|[0-9a-f]{64})$/i;
const scriptsDirectory = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = resolve(scriptsDirectory, '..');
const guardScript = resolve(scriptsDirectory, 'pre-commit-guard.mjs');

function git(args, { workingDirectory = repositoryRoot, ...options } = {}) {
  return execFileSync('git', args, {
    cwd: workingDirectory,
    encoding: 'utf8',
    ...options,
  }).trim();
}

export function parsePrePushUpdates(input) {
  return input
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => {
      const [localRef, localObjectId, remoteRef, remoteObjectId, ...rest] = line.split(/\s+/);
      if (!localRef || !localObjectId || !remoteRef || !remoteObjectId || rest.length > 0) {
        throw new Error('Получена некорректная строка pre-push от Git.');
      }
      if (!OBJECT_ID_PATTERN.test(localObjectId) || !OBJECT_ID_PATTERN.test(remoteObjectId)) {
        throw new Error('Git передал некорректный object id в pre-push.');
      }
      return { localRef, localObjectId, remoteRef, remoteObjectId };
    });
}

function isZeroObjectId(objectId) {
  return /^0+$/.test(objectId);
}

function isBranchRef(refName) {
  return refName.startsWith('refs/heads/');
}

function getRemoteDefaultBranch(remoteName) {
  try {
    const remoteHead = git(['symbolic-ref', `refs/remotes/${remoteName}/HEAD`]);
    return remoteHead || undefined;
  } catch {
    return undefined;
  }
}

export function getPrePushGuardArguments(updates, remoteName, resolveDefaultBranch = getRemoteDefaultBranch) {
  const defaultBranch = resolveDefaultBranch(remoteName);
  const guardArguments = updates.flatMap(({ localRef, localObjectId, remoteRef, remoteObjectId }) => {
    if (!isBranchRef(remoteRef)) {
      throw new Error('Pre-push разрешает отправлять только ветки refs/heads/.');
    }
    if (isZeroObjectId(localObjectId)) {
      if (localRef !== '(delete)') {
        throw new Error('Удаление ветки должно быть явно обозначено Git как (delete).');
      }
      return [];
    }
    if (!isBranchRef(localRef)) {
      throw new Error('Pre-push разрешает отправлять только ветки refs/heads/.');
    }
    if (!isZeroObjectId(remoteObjectId)) {
      return [['--range', `${remoteObjectId}..${localObjectId}`]];
    }
    if (defaultBranch) {
      return [['--new-branch-range', defaultBranch, localObjectId]];
    }
    return [['--range', localObjectId]];
  });
  return guardArguments.filter(
    (argumentsList, index) =>
      guardArguments.findIndex((candidate) => candidate.join('\0') === argumentsList.join('\0')) === index,
  );
}

function runGuard(argumentsList) {
  const result = spawnSync(process.execPath, [guardScript, ...argumentsList], {
    cwd: repositoryRoot,
    stdio: 'inherit',
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    process.exitCode = result.status ?? 1;
  }
}

function runPrePush() {
  const updates = parsePrePushUpdates(readStdin());
  const remoteName = process.argv[3] || 'origin';
  for (const argumentsList of getPrePushGuardArguments(updates, remoteName)) {
    runGuard(argumentsList);
    if (process.exitCode) {
      return;
    }
  }
}

function readStdin() {
  return process.stdin.isTTY ? '' : readFileSync(0, 'utf8');
}

export function installHooks(workingDirectory = repositoryRoot) {
  const hooksDirectory = join(workingDirectory, '.githooks');
  for (const hookName of ['pre-commit', 'pre-push']) {
    const hookPath = join(hooksDirectory, hookName);
    // Путь строится только из заданного корня репозитория и фиксированного имени hook.
    // eslint-disable-next-line security/detect-non-literal-fs-filename
    if (!existsSync(hookPath)) {
      throw new Error(`Не найден versioned hook: .githooks/${hookName}`);
    }
    // Путь проверен выше и не получает пользовательские сегменты.
    // eslint-disable-next-line security/detect-non-literal-fs-filename
    chmodSync(hookPath, 0o755);
  }
  git(['config', '--local', 'core.hooksPath', '.githooks'], { workingDirectory });
  console.log('Локальные hooks периметра данных установлены.');
}

function main() {
  const command = process.argv[2];
  if (command === 'install') {
    installHooks();
    return;
  }
  if (command === 'pre-commit') {
    runGuard([]);
    return;
  }
  if (command === 'pre-push') {
    runPrePush();
    return;
  }
  throw new Error('Использование: node scripts/git-hooks.mjs <install|pre-commit|pre-push>.');
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main();
}
