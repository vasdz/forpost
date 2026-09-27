import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

export function resolvePythonExecutable(
  repositoryRoot = process.cwd(),
  platform = process.platform,
  environment = process.env,
  fileExists = existsSync,
) {
  if (environment.FORPOST_PYTHON) return environment.FORPOST_PYTHON;

  const platformPath = platform === 'win32' ? path.win32 : path.posix;
  const virtualEnvironmentPython = platformPath.join(
    repositoryRoot,
    '.venv',
    platform === 'win32' ? 'Scripts' : 'bin',
    platform === 'win32' ? 'python.exe' : 'python',
  );

  return fileExists(virtualEnvironmentPython) ? virtualEnvironmentPython : 'python';
}

export function getSubmissionChecks(pythonExecutable = resolvePythonExecutable()) {
  return [
    { command: 'node', args: ['scripts/pre-commit-guard.mjs'] },
    { command: 'node', args: ['scripts/pre-commit-guard.mjs', '--tracked'] },
    { command: 'npm', args: ['run', 'typecheck'] },
    { command: 'npm', args: ['run', 'lint'] },
    { command: 'npm', args: ['test'] },
    { command: 'npm', args: ['run', 'build'] },
    { command: pythonExecutable, args: ['-m', 'pytest', 'tests', '-q'] },
    { command: pythonExecutable, args: ['-m', 'ruff', 'check', '.'] },
    { command: pythonExecutable, args: ['-m', 'ruff', 'format', '--check', '.'] },
    { command: pythonExecutable, args: ['-m', 'bandit', '-r', 'apps', 'packages', 'scripts', '-c', '.bandit.yaml'] },
    { command: pythonExecutable, args: ['scripts/load_check.py', '--users', '20', '--requests-per-user', '5'] },
  ];
}

export function resolveCheckCommand(
  check,
  platform = process.platform,
  comSpec = process.env.ComSpec,
  nodeExecutable = process.execPath,
  npmCliPath = path.join(path.dirname(process.execPath), 'node_modules', 'npm', 'bin', 'npm-cli.js'),
  fileExists = existsSync,
) {
  if (platform === 'win32' && check.command === 'npm') {
    if (fileExists(npmCliPath)) {
      return { command: nodeExecutable, args: [npmCliPath, ...check.args] };
    }
    return {
      command: comSpec ?? 'cmd.exe',
      args: ['/d', '/s', '/c', `npm ${check.args.join(' ')}`],
    };
  }
  return check;
}

function runCheck({ command, args }) {
  console.log(`\n> ${command} ${args.join(' ')}`);
  const resolved = resolveCheckCommand({ command, args });
  const result = spawnSync(resolved.command, resolved.args, {
    env: { ...process.env, NEXT_TELEMETRY_DISABLED: '1' },
    shell: false,
    stdio: 'inherit',
  });

  if (result.error) {
    throw new Error(`Не удалось запустить ${command}: ${result.error.message}`);
  }
  if (result.status !== 0) {
    throw new Error(`Проверка завершилась с кодом ${result.status}: ${command} ${args.join(' ')}`);
  }
}

export function runSubmissionVerification() {
  const checks = getSubmissionChecks();
  for (const check of checks) runCheck(check);
  console.log(`\nПроверка LTC 2026 пройдена: ${checks.length} обязательных команд.`);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  try {
    runSubmissionVerification();
  } catch (error) {
    console.error(`\nПроверка LTC 2026 не пройдена: ${error.message}`);
    process.exitCode = 1;
  }
}
