import type { LocalSituationEvent } from './localSituationContract';
import { getTimelineBounds, type TimelineRange } from '@/stores/timelineStore';

/** Возвращает подтверждённые наблюдения внутри выбранного окна и позиции воспроизведения. */
export function selectObservedEventsAtTimeline(
  events: readonly LocalSituationEvent[],
  range: TimelineRange,
  position: string | null,
): LocalSituationEvent[] {
  const bounds = getTimelineBounds(range, events.map((event) => event.recordedAt));
  if (bounds === null) {
    return [];
  }

  const requestedEnd = position === null ? bounds.end.getTime() : new Date(position).getTime();
  const end = Number.isFinite(requestedEnd)
    ? Math.min(Math.max(requestedEnd, bounds.start.getTime()), bounds.end.getTime())
    : bounds.end.getTime();

  return events.filter((event) => {
    const observedAt = new Date(event.recordedAt).getTime();
    return observedAt >= bounds.start.getTime() && observedAt <= end;
  });
}
