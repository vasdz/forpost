import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { findGuardViolations, getChangedFiles } from './pre-commit-guard.mjs';

const OBJECT_ID_PATTERN = /^(?:[0-9a-f]{40}|[0-9a-f]{64})$/i;

function isZeroObjectId(objectId) {
  return /^0+$/.test(objectId);
}

export function parsePreReceiveUpdates(input) {
  return input
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => {
      const [oldObjectId, newObjectId, refName, ...rest] = line.split(/\s+/);
      if (!oldObjectId || !newObjectId || !refName || rest.length > 0) {
        throw new Error('Получена некорректная строка pre-receive от Git.');
      }
      if (!OBJECT_ID_PATTERN.test(oldObjectId) || !OBJECT_ID_PATTERN.test(newObjectId)) {
        throw new Error('Git передал некорректный object id в pre-receive.');
      }
      return { oldObjectId, newObjectId, refName };
    });
}

export function getPreReceiveGuardRanges(updates) {
  const ranges = [];
  for (const { oldObjectId, newObjectId, refName } of updates) {
    if (!refName.startsWith('refs/heads/')) {
      throw new Error('Server-side perimeter guard разрешает обновлять только ветки refs/heads/.');
    }
    if (isZeroObjectId(newObjectId)) {
      continue;
    }
    ranges.push(isZeroObjectId(oldObjectId) ? newObjectId : `${oldObjectId}..${newObjectId}`);
  }
  return [...new Set(ranges)];
}

export function findPreReceiveViolations(input, workingDirectory = process.cwd()) {
  const updates = parsePreReceiveUpdates(input);
  return getPreReceiveGuardRanges(updates).flatMap((revisionRange) =>
    findGuardViolations(getChangedFiles(revisionRange, workingDirectory)),
  );
}

function main() {
  try {
    const violations = findPreReceiveViolations(readFileSync(0, 'utf8'));
    if (violations.length > 0) {
      console.error('Server-side проверка периметра данных не пройдена:');
      violations.forEach((violation) => console.error(`- ${violation}`));
      process.exitCode = 1;
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Неизвестная ошибка проверки.';
    console.error(`Server-side проверка периметра не выполнена: ${message}`);
    process.exitCode = 1;
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main();
}
