import { beforeEach, describe, expect, it } from 'vitest';

import { getTimelineBounds, useTimelineStore, type TimelineRange } from './timelineStore';

const observedTimestamps = [
  '2026-08-01T09:00:00',
  '2026-08-01T12:00:00',
  '2026-08-02T12:00:00',
];

describe('timeline store', () => {
  beforeEach(() => {
    useTimelineStore.getState().reset();
  });

  it('не создаёт границы времени без наблюдаемых событий', () => {
    expect(getTimelineBounds('day', [])).toBeNull();
    useTimelineStore.getState().play();
    expect(useTimelineStore.getState().isPlaying).toBe(false);
  });

  it('выводит границы и начальное положение только из времени наблюдений', () => {
    useTimelineStore.getState().setObservedTimestamps(observedTimestamps);

    expect(useTimelineStore.getState().position).toBe(new Date('2026-08-02T12:00:00').toISOString());
    expect(getTimelineBounds('day', observedTimestamps)).toEqual({
      start: new Date('2026-08-01T12:00:00'),
      end: new Date('2026-08-02T12:00:00'),
    });
  });

  it('не позволяет произвольному runtime-значению диапазона сломать расчёт границ', () => {
    expect(getTimelineBounds('unknown' as TimelineRange, observedTimestamps)).toEqual({
      start: new Date('2026-08-01T12:00:00'),
      end: new Date('2026-08-02T12:00:00'),
    });
  });

  it('ограничивает ручное положение границами фактических наблюдений', () => {
    useTimelineStore.getState().setObservedTimestamps(observedTimestamps);
    useTimelineStore.getState().setPosition('2026-07-01T00:00:00');

    expect(useTimelineStore.getState().position).toBe(new Date('2026-08-01T12:00:00').toISOString());
  });

  it('останавливает воспроизведение на последнем наблюдении', () => {
    useTimelineStore.getState().setObservedTimestamps(observedTimestamps);
    useTimelineStore.getState().setSpeed(100);
    useTimelineStore.getState().play();
    useTimelineStore.getState().tick(1_000_000);

    expect(useTimelineStore.getState()).toMatchObject({
      position: new Date('2026-08-02T12:00:00').toISOString(),
      isPlaying: false,
    });
  });
});
