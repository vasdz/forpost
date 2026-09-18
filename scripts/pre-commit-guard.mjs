import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const MAX_FILE_BYTES = 5_000_000;
const DATA_EXPORT_EXTENSIONS = new Set([
  '.7z',
  '.arrow',
  '.bz2',
  '.csv',
  '.db',
  '.feather',
  '.gz',
  '.jsonl',
  '.ndjson',
  '.ods',
  '.parquet',
  '.rar',
  '.sqlite',
  '.tar',
  '.tsv',
  '.xls',
  '.xlsm',
  '.xlsx',
  '.xz',
  '.zip',
  '.zst',
]);

const DATA_README_PATH = 'data/README.md';

function normalizePath(filePath) {
  return filePath.replaceAll('\\', '/');
}

function hasProtectedExportExtension(normalizedPath) {
  const fileName = normalizedPath.split('/').at(-1)?.toLowerCase() ?? '';
  const extension = fileName.slice(fileName.lastIndexOf('.'));
  return DATA_EXPORT_EXTENSIONS.has(extension);
}

export function findGuardViolations(changedFiles) {
  return changedFiles.flatMap(({ path: filePath, size }) => {
    const normalizedPath = normalizePath(filePath);
    const windowsNormalizedPath = normalizedPath.toLowerCase();
    const violations = [];

    const isProtectedDataPath = windowsNormalizedPath.startsWith('data/');
    const isAllowedDataReadme = normalizedPath === DATA_README_PATH;
    if (isProtectedDataPath && !isAllowedDataReadme) {
      violations.push(`Запрещено добавлять в индекс файл данных: ${normalizedPath}`);
    }

    // Расширения не заменяют серверный DLP, но предотвращают случайный перенос
    // типовых выгрузок и архивов из защищённого корня в другой каталог репозитория.
    if (!isProtectedDataPath && hasProtectedExportExtension(normalizedPath)) {
      violations.push(
        `Запрещено добавлять потенциальную выгрузку данных вне data/: ${normalizedPath}`,
      );
    }

    if (size > MAX_FILE_BYTES) {
      violations.push(`Размер staged-файла превышает 5 MB: ${normalizedPath}`);
    }

    return violations;
  });
}

function getBlobSize(revision, filePath, workingDirectory) {
  return Number.parseInt(
    execFileSync('git', ['cat-file', '-s', `${revision}:${filePath}`], {
      cwd: workingDirectory,
      encoding: 'utf8',
    }),
    10,
  );
}

export function getStagedFiles(workingDirectory = process.cwd()) {
  const paths = execFileSync(
    'git',
    ['diff', '--cached', '--name-only', '-z', '--diff-filter=ACMR'],
    { cwd: workingDirectory, encoding: 'utf8' },
  )
    .split('\0')
    .filter(Boolean);

  return paths.map((filePath) => ({
    path: filePath,
    size: getBlobSize('', filePath, workingDirectory),
  }));
}

function getRevisionCommits(revisionRange, workingDirectory) {
  return execFileSync('git', ['rev-list', '--reverse', revisionRange], {
    cwd: workingDirectory,
    encoding: 'utf8',
  })
    .split('\n')
    .filter(Boolean);
}

function getChangedPathEntriesForCommit(revision, workingDirectory) {
  const entries = execFileSync(
    'git',
    [
      'diff-tree',
      '--root',
      '-m',
      '--no-commit-id',
      '--name-status',
      '-z',
      '--find-renames',
      '--diff-filter=ACMR',
      '-r',
      revision,
    ],
    { cwd: workingDirectory, encoding: 'utf8' },
  )
    .split('\0')
    .filter(Boolean);
  return getChangedPathEntriesFromEntries(entries);
}

function getChangedPathEntriesFromEntries(entries) {
  const paths = [];

  for (let index = 0; index < entries.length;) {
    const status = entries.at(index);
    if (typeof status !== 'string') {
      throw new Error('Git вернул неполную запись изменения.');
    }

    const sourcePath = entries.at(index + 1);
    if (typeof sourcePath !== 'string') {
      throw new Error('Git вернул неполную запись изменения.');
    }

    const isRenameOrCopy = status.startsWith('R') || status.startsWith('C');
    const destinationPath = entries.at(index + (isRenameOrCopy ? 2 : 1));
    if (typeof destinationPath !== 'string') {
      throw new Error('Git вернул неполную запись изменения.');
    }

    if (isRenameOrCopy) {
      paths.push({ path: sourcePath, previous: true });
    }
    paths.push({ path: destinationPath, previous: false });
    index += isRenameOrCopy ? 3 : 2;
  }

  return paths;
}

export function getChangedPathsFromEntries(entries) {
  return getChangedPathEntriesFromEntries(entries).map(({ path: filePath }) => filePath);
}

export function getChangedFiles(revisionRange, workingDirectory = process.cwd()) {
  return getRevisionCommits(revisionRange, workingDirectory).flatMap((revision) =>
    getChangedPathEntriesForCommit(revision, workingDirectory).map(({ path: filePath, previous }) => ({
      path: filePath,
      // Предыдущий путь rename/copy отсутствует в новом дереве; его размер не нужен
      // для проверки периметра, но сам путь обязательно остаётся в проверке.
      size: previous ? 0 : getBlobSize(revision, filePath, workingDirectory),
    })),
  );
}

export function getNewBranchRange(defaultBranchRevision, headRevision, workingDirectory = process.cwd()) {
  try {
    const resolvedHead = execFileSync('git', ['rev-parse', headRevision], {
      cwd: workingDirectory,
      encoding: 'utf8',
    }).trim();
    const mergeBase = execFileSync(
      'git',
      ['merge-base', defaultBranchRevision, headRevision],
      { cwd: workingDirectory, encoding: 'utf8' },
    ).trim();
    if (mergeBase === resolvedHead) {
      return headRevision;
    }
    return `${mergeBase}..${headRevision}`;
  } catch {
    return headRevision;
  }
}

function parseArguments(argumentsList) {
  if (argumentsList.length === 0) {
    return { mode: 'staged' };
  }

  if (argumentsList.length === 2 && argumentsList[0] === '--range') {
    return { mode: 'range', revisionRange: argumentsList[1] };
  }

  if (argumentsList.length === 3 && argumentsList[0] === '--new-branch-range') {
    return {
      mode: 'new-branch-range',
      defaultBranchRevision: argumentsList[1],
      headRevision: argumentsList[2],
    };
  }

  throw new Error(
    'Использование: node scripts/pre-commit-guard.mjs [--range <base>..<head> | --new-branch-range <default> <head>]',
  );
}

function main() {
  const { mode, revisionRange, defaultBranchRevision, headRevision } = parseArguments(process.argv.slice(2));
  const selectedRange =
    mode === 'new-branch-range'
      ? getNewBranchRange(defaultBranchRevision, headRevision)
      : revisionRange;
  const changedFiles = mode === 'staged' ? getStagedFiles() : getChangedFiles(selectedRange);
  const violations = findGuardViolations(changedFiles);

  if (violations.length > 0) {
    console.error('Проверка периметра данных не пройдена:');
    violations.forEach((violation) => console.error(`- ${violation}`));
    process.exitCode = 1;
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main();
}
