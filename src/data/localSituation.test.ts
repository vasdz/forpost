import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { tmpdir } from 'node:os';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  LocalSituationUnavailableError,
  getLocalSituationSnapshot,
  type LocalSituationSnapshot,
} from './localSituation';
import { GET } from '@/app/api/local-situation/route';

const validSnapshot: LocalSituationSnapshot = {
  sourceAvailability: {
    events: true,
    channels: true,
    objects: true,
    access_events: false,
    maintenance_history: false,
    ml_predictions: false,
    work_permits: false,
  },
  dataQuality: {
    builtAt: '2026-09-18T10:00:00Z',
    latestObservedAt: '2026-08-01T23:59:58',
    eventCount: 1,
    skippedTimestampCount: 0,
    technicalAnomalyCount: 0,
    unmappedChannelCount: 1,
    objectLinkAvailable: false,
    freshness: 'historical',
  },
  channels: [
    {
      channelId: 'test-channel',
      engineeringSystemType: 'test-system',
      sensorType: 'test-sensor',
      engineeringSystemTag: 'test-tag',
      sensorName: 'test-name',
      objectId: null,
    },
  ],
  objects: [
    {
      objectId: 'test-object',
      hierarchyLevel: '1',
      parentId: null,
      objectKind: 'test-kind',
      dispatcherName: 'test-dispatcher-name',
    },
  ],
  events: [
    {
      canonicalId: 'a'.repeat(64),
      eventId: 'test-event',
      channelId: 'test-channel',
      recordedAt: '2026-08-01T23:59:58',
      isAlarm: true,
      sensorValue: 'test-value',
      qualityCode: 'valid',
      analysisEligible: true,
      provenance: 'observed',
    },
  ],
};

const publicSnapshot: LocalSituationSnapshot = {
  sourceAvailability: validSnapshot.sourceAvailability,
  dataQuality: validSnapshot.dataQuality,
  channels: validSnapshot.channels,
  objects: validSnapshot.objects,
  events: validSnapshot.events,
};

describe.sequential('локальный снимок ситуации', () => {
  let fixtureRoot = '';

  beforeEach(async () => {
    fixtureRoot = await mkdtemp(join(tmpdir(), 'forpost-local-situation-'));
    vi.spyOn(process, 'cwd').mockReturnValue(fixtureRoot);
    vi.stubEnv('FORPOST_LOCAL_SNAPSHOT', '1');
  });

  afterEach(async () => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    await rm(fixtureRoot, { force: true, recursive: true });
  });

  async function writeSnapshot(snapshot: unknown = validSnapshot): Promise<void> {
    const path = join(fixtureRoot, 'data', 'processed', 'local-situation.json');
    // eslint-disable-next-line security/detect-non-literal-fs-filename -- test fixture создаётся mkdtemp и не получает путь из HTTP-ввода.
    await mkdir(dirname(path), { recursive: true });
    // eslint-disable-next-line security/detect-non-literal-fs-filename -- test fixture создаётся mkdtemp и не получает путь из HTTP-ввода.
    await writeFile(path, JSON.stringify(snapshot), 'utf8');
  }

  it('отдаёт снимок в штатном локальном процессе', async () => {
    await writeSnapshot();

    const response = await GET(new Request('http://service.invalid/api/local-situation'));

    expect(response.status).toBe(200);
    expect(response.headers.get('cache-control')).toContain('no-store');
    expect(response.headers.get('x-robots-tag')).toBe('noindex, nofollow');
    await expect(response.json()).resolves.toEqual(publicSnapshot);
  });

  it('возвращает общее сообщение доступности при отсутствии снимка', async () => {
    const response = await GET(
      new Request('http://service.invalid/api/local-situation', { headers: { host: 'localhost' } }),
    );

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({
      code: 'LOCAL_SITUATION_UNAVAILABLE',
      message: 'Локальный снимок данных недоступен.',
    });
  });

  it('отклоняет снимок с неподтверждённой схемой', async () => {
    await writeSnapshot({ ...validSnapshot, rawRoot: 'outside-fixture' });

    await expect(getLocalSituationSnapshot()).rejects.toBeInstanceOf(
      LocalSituationUnavailableError,
    );
  });

  it('не выдаёт снимок с некорректным временем наблюдения', async () => {
    await writeSnapshot({
      ...validSnapshot,
      events: [{ ...validSnapshot.events[0], recordedAt: 'not-an-observed-timestamp' }],
    });

    const response = await GET(
      new Request('http://service.invalid/api/local-situation', { headers: { host: 'localhost:3000' } }),
    );

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({
      code: 'LOCAL_SITUATION_UNAVAILABLE',
      message: 'Локальный снимок данных недоступен.',
    });
  });

  it('отклоняет событие с неподтверждённым происхождением', async () => {
    await writeSnapshot({
      ...validSnapshot,
      events: [{ ...validSnapshot.events[0], provenance: 'guessed' }],
    });

    await expect(getLocalSituationSnapshot()).rejects.toBeInstanceOf(
      LocalSituationUnavailableError,
    );
  });

  it('отклоняет несогласованный агрегат числа событий', async () => {
    await writeSnapshot({
      ...validSnapshot,
      dataQuality: { ...validSnapshot.dataQuality, eventCount: 2 },
    });

    await expect(getLocalSituationSnapshot()).rejects.toBeInstanceOf(
      LocalSituationUnavailableError,
    );
  });

  it('принимает известный legacy-конверт, но не выдаёт служебные метаданные', async () => {
    await writeSnapshot({
      ...validSnapshot,
      sourceMetadata: {
        journalFileCount: 1,
        selectedJournalFileCount: 1,
        scannedEventCount: 12,
        skippedEventCount: 0,
        channelCount: 1,
        objectCount: 1,
        latestObservedAt: '2026-08-01T23:59:58',
      },
    });

    const response = await GET(
      new Request('http://service.invalid/api/local-situation', { headers: { host: 'localhost:3000' } }),
    );

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual(publicSnapshot);
  });

  it('отклоняет legacy-конверт с неполной схемой метаданных', async () => {
    await writeSnapshot({
      ...validSnapshot,
      sourceMetadata: {
        journalFileCount: 1,
      },
    });

    await expect(getLocalSituationSnapshot()).rejects.toBeInstanceOf(
      LocalSituationUnavailableError,
    );
  });

  it('не выдаёт снимок с числом наблюдений выше документированного предела', async () => {
    await writeSnapshot({
      ...validSnapshot,
      events: Array.from({ length: 501 }, () => ({ ...validSnapshot.events[0] })),
    });

    const response = await GET(
      new Request('http://service.invalid/api/local-situation', { headers: { host: 'localhost:3000' } }),
    );

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({
      code: 'LOCAL_SITUATION_UNAVAILABLE',
      message: 'Локальный снимок данных недоступен.',
    });
  });

  it('не читает в API формально корректный снимок выше предела размера', async () => {
    await writeSnapshot({
      ...validSnapshot,
      channels: [{ ...validSnapshot.channels[0], sensorName: 'x'.repeat(8 * 1024 * 1024) }],
    });

    const response = await GET(
      new Request('http://service.invalid/api/local-situation', { headers: { host: 'localhost:3000' } }),
    );

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({
      code: 'LOCAL_SITUATION_UNAVAILABLE',
      message: 'Локальный снимок данных недоступен.',
    });
  });

  it('игнорирует query-путь и внешний URL, читая только фиксированный снимок', async () => {
    await writeSnapshot();
    const outsidePath = join(fixtureRoot, 'outside-fixture.json');
    // eslint-disable-next-line security/detect-non-literal-fs-filename -- отдельный OS-временный test fixture, не production-путь.
    await writeFile(
      outsidePath,
      JSON.stringify({
        ...validSnapshot,
        events: [],
      }),
      'utf8',
    );

    const response = await GET(
      new Request(
        `http://service.invalid/api/local-situation?path=${encodeURIComponent(outsidePath)}&url=https%3A%2F%2Fexample.test%2Fsnapshot.json`,
        { headers: { host: 'localhost' } },
      ),
    );
    const snapshot = await response.json() as LocalSituationSnapshot;

    expect(response.status).toBe(200);
    expect(snapshot.events).toEqual(publicSnapshot.events);
  });
});
