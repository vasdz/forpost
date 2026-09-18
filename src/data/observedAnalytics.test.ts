import { describe, expect, it } from 'vitest';

import type { LocalSituationEvent } from './localSituationContract';
import { aggregateObservedEvents } from './observedAnalytics';

const events: LocalSituationEvent[] = [
  { eventId: '1', channelId: 'a', recordedAt: '2026-08-01T10:01:00', isAlarm: true, sensorValue: '1' },
  { eventId: '2', channelId: 'a', recordedAt: '2026-08-01T10:59:00', isAlarm: false, sensorValue: '2' },
  { eventId: '3', channelId: 'b', recordedAt: '2026-08-01T12:00:00', isAlarm: null, sensorValue: '3' },
];

describe('агрегация наблюдаемой активности', () => {
  it('считает часовые бакеты и статусы без интерпретации как риск', () => {
    expect(aggregateObservedEvents(events)).toEqual({
      buckets: [
        { at: '2026-08-01T10:00:00', events: 2, alarms: 1 },
        { at: '2026-08-01T12:00:00', events: 1, alarms: 0 },
      ],
      statuses: [
        { name: 'Есть отметка', value: 1, color: 'var(--color-danger)' },
        { name: 'Нет отметки', value: 1, color: 'var(--color-success)' },
        { name: 'Не указана', value: 1, color: 'var(--color-text-muted)' },
      ],
    });
  });
});
