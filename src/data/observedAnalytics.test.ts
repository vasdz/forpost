import { describe, expect, it } from 'vitest';

import type { LocalSituationEvent } from './localSituationContract';
import { aggregateObservedEvents } from './observedAnalytics';

const events: LocalSituationEvent[] = [
  { canonicalId: '1'.repeat(64), eventId: '1', channelId: 'a', recordedAt: '2026-08-01T10:01:00', isAlarm: true, sensorValue: '1', qualityCode: 'valid', analysisEligible: true, provenance: 'observed' },
  { canonicalId: '2'.repeat(64), eventId: '2', channelId: 'a', recordedAt: '2026-08-01T10:59:00', isAlarm: false, sensorValue: '2', qualityCode: 'valid', analysisEligible: true, provenance: 'observed' },
  { canonicalId: '3'.repeat(64), eventId: '3', channelId: 'b', recordedAt: '2026-08-01T12:00:00', isAlarm: null, sensorValue: '3', qualityCode: 'valid', analysisEligible: true, provenance: 'observed' },
];

describe('агрегация наблюдаемой активности', () => {
  it('сохраняет тихие часы внутри явного календарного окна', () => {
    expect(aggregateObservedEvents(events, {
      startAt: '2026-08-01T10:00:00',
      endAt: '2026-08-01T12:59:59',
    })).toEqual({
      buckets: [
        { at: '2026-08-01T10:00:00', events: 2, alarms: 1 },
        { at: '2026-08-01T11:00:00', events: 0, alarms: 0 },
        { at: '2026-08-01T12:00:00', events: 1, alarms: 0 },
      ],
      statuses: [
        { name: 'Есть отметка', value: 1, color: 'var(--color-danger)' },
        { name: 'Нет отметки', value: 1, color: 'var(--color-success)' },
        { name: 'Не указана', value: 1, color: 'var(--color-text-muted)' },
      ],
    });
  });

  it('не включает в график и структуру события за границами окна', () => {
    expect(aggregateObservedEvents(events, {
      startAt: '2026-08-01T11:00:00',
      endAt: '2026-08-01T12:00:00',
    })).toEqual({
      buckets: [
        { at: '2026-08-01T11:00:00', events: 0, alarms: 0 },
        { at: '2026-08-01T12:00:00', events: 1, alarms: 0 },
      ],
      statuses: [
        { name: 'Есть отметка', value: 0, color: 'var(--color-danger)' },
        { name: 'Нет отметки', value: 0, color: 'var(--color-success)' },
        { name: 'Не указана', value: 1, color: 'var(--color-text-muted)' },
      ],
    });
  });
});
