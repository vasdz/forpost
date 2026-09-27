import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

import { resolveCheckCommand, resolvePythonExecutable } from './verify-submission.mjs';

const REVIEWER_DOCUMENTS = [
  'README.md',
  'START_HERE.md',
  'LTC_2026_SUBMISSION.md',
  'docs/TZ_COMPLIANCE.md',
  'docs/ML_METHODS.md',
  'docs/ML_CAPABILITIES.md',
  'docs/DATA_CARD.md',
  'docs/PERFORMANCE.md',
  'docs/SECURITY_AUDIT.md',
  'docs/SECURITY_BY_DESIGN.md',
  'docs/SECURITY_EVIDENCE.md',
  'docs/TEST_PROTOCOL.md',
];

export function getFastSubmissionChecks(pythonExecutable = resolvePythonExecutable()) {
  return [
    { command: 'node', args: ['scripts/pre-commit-guard.mjs'] },
    { command: 'node', args: ['scripts/pre-commit-guard.mjs', '--tracked'] },
    { command: 'npm', args: ['run', 'typecheck'] },
    { command: 'npm', args: ['run', 'lint'] },
    { command: pythonExecutable, args: ['-m', 'ruff', 'check', '.'] },
    { command: 'git', args: ['diff', '--check'] },
  ];
}

export function getReviewerDocumentIssues(contentsByPath) {
  const issues = REVIEWER_DOCUMENTS
    .filter((documentPath) => !(documentPath in contentsByPath))
    .map((documentPath) => `Отсутствует обязательный reviewer-файл: ${documentPath}`);

  for (const [documentPath, content] of Object.entries(contentsByPath)) {
    if (/текущ\S*[\s\S]{0,60}\bv9\b/i.test(content)) {
      issues.push(`${documentPath} содержит устаревшее current-release упоминание v9.`);
    }
  }
  return issues;
}

function readReviewerDocuments(repositoryRoot) {
  return Object.fromEntries(
    REVIEWER_DOCUMENTS
      // Пути ограничены константным allowlist выше, пользовательский ввод отсутствует.
      // eslint-disable-next-line security/detect-non-literal-fs-filename
      .filter((documentPath) => existsSync(path.join(repositoryRoot, documentPath)))
      .map((documentPath) => [
        documentPath,
        // Пути ограничены константным allowlist выше, пользовательский ввод отсутствует.
        // eslint-disable-next-line security/detect-non-literal-fs-filename
        readFileSync(path.join(repositoryRoot, documentPath), 'utf8'),
      ]),
  );
}

function runCheck(check) {
  console.log(`\n> ${check.command} ${check.args.join(' ')}`);
  const resolved = resolveCheckCommand(check);
  const result = spawnSync(resolved.command, resolved.args, {
    env: { ...process.env, NEXT_TELEMETRY_DISABLED: '1' },
    shell: false,
    stdio: 'inherit',
  });
  if (result.error) throw new Error(`Не удалось запустить ${check.command}: ${result.error.message}`);
  if (result.status !== 0) {
    throw new Error(`Проверка завершилась с кодом ${result.status}: ${check.command} ${check.args.join(' ')}`);
  }
}

export function runFastSubmissionVerification(repositoryRoot = process.cwd()) {
  const documentIssues = getReviewerDocumentIssues(readReviewerDocuments(repositoryRoot));
  if (documentIssues.length > 0) {
    documentIssues.forEach((issue) => console.error(`FAIL: ${issue}`));
    throw new Error('Проверка reviewer-документации не пройдена.');
  }

  const checks = getFastSubmissionChecks();
  for (const check of checks) runCheck(check);
  console.log(`\nPASS: быстрый LTC submission verify (${checks.length} checks + reviewer docs).`);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  try {
    runFastSubmissionVerification();
  } catch (error) {
    console.error(`\nFAIL: ${error.message}`);
    process.exitCode = 1;
  }
}
