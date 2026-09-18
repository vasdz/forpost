import type { LocalSituationEvent } from './localSituationContract';

export type ObservedActivityBucket = { at: string; events: number; alarms: number };

export function aggregateObservedEvents(events: readonly LocalSituationEvent[]) {
  const byHour = new Map<string, ObservedActivityBucket>();
  for (const event of events) {
    const at = `${event.recordedAt.slice(0, 13)}:00:00`;
    const current = byHour.get(at) ?? { at, events: 0, alarms: 0 };
    current.events += 1;
    current.alarms += event.isAlarm === true ? 1 : 0;
    byHour.set(at, current);
  }

  const statusCounts = events.reduce((counts, event) => {
    if (event.isAlarm === true) counts.alarm += 1;
    else if (event.isAlarm === false) counts.normal += 1;
    else counts.unknown += 1;
    return counts;
  }, { alarm: 0, normal: 0, unknown: 0 });

  return {
    buckets: [...byHour.values()].sort((left, right) => left.at.localeCompare(right.at)),
    statuses: [
      { name: 'Есть отметка', value: statusCounts.alarm, color: 'var(--color-danger)' },
      { name: 'Нет отметки', value: statusCounts.normal, color: 'var(--color-success)' },
      { name: 'Не указана', value: statusCounts.unknown, color: 'var(--color-text-muted)' },
    ],
  };
}
