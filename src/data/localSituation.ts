import { open, realpath } from 'node:fs/promises';
import path from 'node:path';
import {
  normalizeStoredLocalSituationSnapshot,
  type LocalSituationSnapshot,
} from './localSituationContract';

export type {
  LocalSituationChannel,
  LocalSituationEvent,
  LocalSituationObject,
  LocalSituationSnapshot,
  SourceAvailability,
} from './localSituationContract';

export class LocalSituationUnavailableError extends Error {
  constructor() {
    super('Локальный снимок данных недоступен.');
    this.name = 'LocalSituationUnavailableError';
  }
}

const SNAPSHOT_FILE_NAME = 'local-situation.json';
const PROCESSED_SEGMENTS = ['data', 'processed'];
// Снимок строится из ограниченной выборки и не должен безгранично занимать память API.
const MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024;

function getProjectRoot(): string {
  return path.resolve(process.cwd());
}

function getProcessedRoot(projectRoot: string): string {
  return path.resolve(projectRoot, ...PROCESSED_SEGMENTS);
}

function getSnapshotPath(projectRoot: string): string {
  return path.resolve(getProcessedRoot(projectRoot), SNAPSHOT_FILE_NAME);
}

function isWithin(root: string, target: string): boolean {
  const relative = path.relative(root, target);
  return relative === '' || (!relative.startsWith(`..${path.sep}`) && relative !== '..' && !path.isAbsolute(relative));
}

async function readSnapshotFile(): Promise<string> {
  const projectRoot = getProjectRoot();
  const processedRoot = getProcessedRoot(projectRoot);
  const snapshotPath = getSnapshotPath(projectRoot);
  const [canonicalProjectRoot, canonicalProcessedRoot, canonicalSnapshotPath] = await Promise.all([
    // eslint-disable-next-line security/detect-non-literal-fs-filename -- process.cwd() канонизируется как корень приложения.
    realpath(projectRoot),
    // eslint-disable-next-line security/detect-non-literal-fs-filename -- путь составлен из корня и фиксированных сегментов data/processed.
    realpath(processedRoot),
    // eslint-disable-next-line security/detect-non-literal-fs-filename -- имя снимка фиксировано и путь проверяется ниже после realpath.
    realpath(snapshotPath),
  ]);

  if (!isWithin(canonicalProjectRoot, canonicalProcessedRoot)
    || !isWithin(canonicalProcessedRoot, canonicalSnapshotPath)
    || path.basename(canonicalSnapshotPath) !== SNAPSHOT_FILE_NAME) {
    throw new LocalSituationUnavailableError();
  }

  // eslint-disable-next-line security/detect-non-literal-fs-filename -- путь канонизирован, ограничен data/processed и не зависит от HTTP-ввода.
  const snapshotFile = await open(canonicalSnapshotPath, 'r');
  try {
    const snapshotStats = await snapshotFile.stat();
    if (!snapshotStats.isFile() || snapshotStats.size > MAX_SNAPSHOT_BYTES) {
      throw new LocalSituationUnavailableError();
    }

    return await snapshotFile.readFile({ encoding: 'utf8' });
  } finally {
    await snapshotFile.close();
  }
}

export async function getLocalSituationSnapshot(): Promise<LocalSituationSnapshot> {
  try {
    const parsed: unknown = JSON.parse(await readSnapshotFile());
    const snapshot = normalizeStoredLocalSituationSnapshot(parsed);
    if (snapshot === null) {
      throw new LocalSituationUnavailableError();
    }
    return snapshot;
  } catch (error) {
    if (error instanceof LocalSituationUnavailableError) {
      throw error;
    }
    throw new LocalSituationUnavailableError();
  }
}
