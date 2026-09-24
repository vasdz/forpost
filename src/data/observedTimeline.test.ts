import { describe, expect, it } from 'vitest';

import type { LocalSituationEvent } from './localSituationContract';
import { getObservedTimelineWindow, selectObservedEventsAtTimeline } from './observedTimeline';

const events: LocalSituationEvent[] = [
  { canonicalId: '1'.repeat(64), eventId: 'old', channelId: 'c-1', recordedAt: '2026-08-01T08:00:00', isAlarm: false, sensorValue: '0', qualityCode: 'valid', analysisEligible: true, provenance: 'observed' },
  { canonicalId: '2'.repeat(64), eventId: 'start', channelId: 'c-1', recordedAt: '2026-08-01T12:00:00', isAlarm: false, sensorValue: '1', qualityCode: 'valid', analysisEligible: true, provenance: 'observed' },
  { canonicalId: '3'.repeat(64), eventId: 'current', channelId: 'c-2', recordedAt: '2026-08-02T06:00:00', isAlarm: true, sensorValue: '2', qualityCode: 'valid', analysisEligible: true, provenance: 'observed' },
  { canonicalId: '4'.repeat(64), eventId: 'future', channelId: 'c-2', recordedAt: '2026-08-02T12:00:00', isAlarm: true, sensorValue: '3', qualityCode: 'valid', analysisEligible: true, provenance: 'observed' },
];

describe('выбор наблюдений по общей временной шкале', () => {
  it('оставляет только события выбранного диапазона до текущей позиции включительно', () => {
    expect(selectObservedEventsAtTimeline(events, 'day', '2026-08-02T06:00:00').map((event) => event.eventId))
      .toEqual(['start', 'current']);
  });

  it('использует последнее наблюдение, пока позиция ещё не инициализирована', () => {
    expect(selectObservedEventsAtTimeline(events, 'day', null).map((event) => event.eventId))
      .toEqual(['start', 'current', 'future']);
  });

  it('не синтезирует события при пустом наборе', () => {
    expect(selectObservedEventsAtTimeline([], 'month', null)).toEqual([]);
  });

  it('возвращает явные границы того же окна, которым фильтрует события', () => {
    expect(getObservedTimelineWindow(events, 'day', '2026-08-02T06:00:00')).toEqual({
      startAt: '2026-08-01T12:00:00',
      endAt: '2026-08-02T06:00:00',
    });
  });
});
