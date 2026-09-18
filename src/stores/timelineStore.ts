'use client';

import { create } from 'zustand';

export type TimelineRange = 'day' | 'week' | 'month';
export type PlaybackSpeed = 1 | 5 | 10 | 100;

export type TimelineBounds = { start: Date; end: Date } | null;

type TimelineState = {
  range: TimelineRange;
  position: string | null;
  isPlaying: boolean;
  speed: PlaybackSpeed;
  observedTimestamps: string[];
  setObservedTimestamps: (timestamps: readonly string[]) => void;
  setRange: (range: TimelineRange) => void;
  setPosition: (position: Date | string) => void;
  setSpeed: (speed: PlaybackSpeed) => void;
  play: () => void;
  pause: () => void;
  tick: (elapsedMilliseconds: number) => void;
  reset: () => void;
};

const rangeHours: Record<TimelineRange, number> = { day: 24, week: 24 * 7, month: 24 * 30 };

function getRangeHours(range: TimelineRange): number {
  switch (range) {
    case 'week':
      return rangeHours.week;
    case 'month':
      return rangeHours.month;
    default:
      return rangeHours.day;
  }
}

function sortedTimestampTimes(timestamps: readonly string[]): number[] {
  return [...new Set(timestamps.map((timestamp) => new Date(timestamp).getTime()).filter(Number.isFinite))].sort((left, right) => left - right);
}

export function getTimelineBounds(range: TimelineRange, timestamps: readonly string[]): TimelineBounds {
  const times = sortedTimestampTimes(timestamps);
  if (times.length === 0) {
    return null;
  }

  const latest = times.at(-1)!;
  const earliest = times[0];
  const requestedStart = latest - getRangeHours(range) * 3_600_000;
  return {
    start: new Date(Math.max(earliest, requestedStart)),
    end: new Date(latest),
  };
}

function clampPosition(position: Date, range: TimelineRange, timestamps: readonly string[]): Date | null {
  const bounds = getTimelineBounds(range, timestamps);
  if (bounds === null || !Number.isFinite(position.getTime())) {
    return null;
  }
  return new Date(Math.min(Math.max(position.getTime(), bounds.start.getTime()), bounds.end.getTime()));
}

const initialState = {
  range: 'day' as TimelineRange,
  position: null,
  isPlaying: false,
  speed: 1 as PlaybackSpeed,
  observedTimestamps: [] as string[],
};

export const useTimelineStore = create<TimelineState>((set) => ({
  ...initialState,
  setObservedTimestamps: (timestamps) => set((state) => {
    const observedTimestamps = timestamps.filter((timestamp) => Number.isFinite(new Date(timestamp).getTime()));
    const bounds = getTimelineBounds(state.range, observedTimestamps);
    return {
      observedTimestamps,
      position: bounds === null
        ? null
        : clampPosition(new Date(state.position ?? bounds.end), state.range, observedTimestamps)?.toISOString() ?? bounds.end.toISOString(),
      isPlaying: bounds === null ? false : state.isPlaying,
    };
  }),
  setRange: (range) => set((state) => {
    const bounds = getTimelineBounds(range, state.observedTimestamps);
    return {
      range,
      position: bounds === null
        ? null
        : clampPosition(new Date(state.position ?? bounds.end), range, state.observedTimestamps)?.toISOString() ?? bounds.end.toISOString(),
      isPlaying: bounds === null ? false : state.isPlaying,
    };
  }),
  setPosition: (position) => set((state) => {
    const clamped = clampPosition(new Date(position), state.range, state.observedTimestamps);
    return clamped === null ? state : { position: clamped.toISOString() };
  }),
  setSpeed: (speed) => set({ speed }),
  play: () => set((state) => getTimelineBounds(state.range, state.observedTimestamps) === null ? { isPlaying: false } : { isPlaying: true }),
  pause: () => set({ isPlaying: false }),
  tick: (elapsedMilliseconds) => set((state) => {
    if (!state.isPlaying || state.position === null) {
      return state;
    }
    const bounds = getTimelineBounds(state.range, state.observedTimestamps);
    if (bounds === null) {
      return { isPlaying: false, position: null };
    }
    const next = new Date(new Date(state.position).getTime() + elapsedMilliseconds * state.speed * 60);
    if (next >= bounds.end) {
      return { position: bounds.end.toISOString(), isPlaying: false };
    }
    return { position: next.toISOString() };
  }),
  reset: () => set(initialState),
}));
