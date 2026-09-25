'use client';

import { useEffect, useMemo } from 'react';
import { format } from 'date-fns';
import { ru } from 'date-fns/locale';
import { Pause, Play, SkipBack, SkipForward } from 'lucide-react';

import { Button } from '@/components/ui/Button';
import { RangeSlider } from '@/components/ui/RangeSlider';
import { useLocalSituation } from '@/data/LocalSituationProvider';
import { getTimelineBounds, type PlaybackSpeed, type TimelineRange, useTimelineStore } from '@/stores/timelineStore';

const ranges: Array<{ id: TimelineRange; label: string }> = [{ id: 'day', label: 'День' }, { id: 'week', label: 'Неделя' }, { id: 'month', label: 'Месяц' }];
const speeds: PlaybackSpeed[] = [1, 5, 10, 100];

export function TimelinePlayback() {
  const localSituation = useLocalSituation();
  const { range, position, isPlaying, speed, observedTimestamps, setObservedTimestamps, setRange, setPosition, setSpeed, play, pause, tick } = useTimelineStore();
  const timestamps = useMemo(
    () => localSituation.status === 'ready' ? localSituation.snapshot.events.map((event) => event.recordedAt) : [],
    [localSituation],
  );

  useEffect(() => {
    setObservedTimestamps(timestamps);
  }, [setObservedTimestamps, timestamps]);

  const bounds = useMemo(() => getTimelineBounds(range, observedTimestamps), [range, observedTimestamps]);
  const current = position === null ? null : new Date(position);
  const progress = bounds === null || current === null || bounds.start.getTime() === bounds.end.getTime()
    ? 0
    : Math.round(((current.getTime() - bounds.start.getTime()) / (bounds.end.getTime() - bounds.start.getTime())) * 1000);
  const markers = localSituation.status === 'ready' && bounds !== null
    ? localSituation.snapshot.events.filter((event) => event.isAlarm === true && new Date(event.recordedAt).getTime() >= bounds.start.getTime() && new Date(event.recordedAt).getTime() <= bounds.end.getTime())
    : [];

  useEffect(() => {
    if (!isPlaying) {
      return;
    }
    const interval = window.setInterval(() => tick(1_000), 1_000);
    return () => window.clearInterval(interval);
  }, [isPlaying, tick]);

  if (bounds === null || current === null) {
    return <footer aria-label="Воспроизведение временной шкалы" className="surface-subtle fixed bottom-0 left-[var(--active-sidebar-width)] right-0 z-30 flex h-[var(--timeline-height)] items-center rounded-none border-x-0 border-b-0 px-4 text-xs text-[var(--color-text-muted)] md:px-6">Временная шкала появится после загрузки наблюдаемых событий.</footer>;
  }

  const move = (minutes: number) => setPosition(new Date(current.getTime() + minutes * 60_000));
  return <footer aria-label="Воспроизведение временной шкалы" className="surface-subtle fixed bottom-0 left-[var(--active-sidebar-width)] right-0 z-30 flex min-h-[var(--timeline-height)] flex-wrap items-end gap-x-4 gap-y-2 overflow-x-auto rounded-none border-x-0 border-b-0 px-4 py-2 md:px-6">
    <div className="flex items-center gap-1" role="group" aria-label="Диапазон времени">{ranges.map((option) => <Button key={option.id} size="sm" variant={range === option.id ? 'primary' : 'ghost'} onClick={() => setRange(option.id)}>{option.label}</Button>)}</div>
    <div className="flex items-center gap-1"><Button size="sm" variant="ghost" onClick={() => move(-30)} aria-label="На 30 минут назад"><SkipBack size={17} aria-hidden="true" /></Button><Button size="sm" variant="primary" onClick={isPlaying ? pause : play} aria-label={isPlaying ? 'Пауза' : 'Воспроизвести'}>{isPlaying ? <Pause size={17} aria-hidden="true" /> : <Play size={17} aria-hidden="true" />}</Button><Button size="sm" variant="ghost" onClick={() => move(30)} aria-label="На 30 минут вперёд"><SkipForward size={17} aria-hidden="true" /></Button></div>
    <div className="min-w-[280px] flex-1"><RangeSlider label="Положение временной шкалы" min={0} max={1000} value={Math.min(1000, Math.max(0, progress))} onChange={(value) => setPosition(new Date(bounds.start.getTime() + (bounds.end.getTime() - bounds.start.getTime()) * (value / 1000)))} valueText={format(current, 'd MMM, HH:mm', { locale: ru })} /><div className="relative mx-1 h-3" aria-label="Маркеры событий с отметкой о сработке">{markers.map((marker) => { const markerProgress = bounds.start.getTime() === bounds.end.getTime() ? 0 : ((new Date(marker.recordedAt).getTime() - bounds.start.getTime()) / (bounds.end.getTime() - bounds.start.getTime())) * 100; return <button type="button" onClick={() => setPosition(marker.recordedAt)} aria-label={`Событие с отметкой о сработке: ${format(new Date(marker.recordedAt), 'd MMM, HH:mm', { locale: ru })}`} key={marker.eventId} title={`Событие с отметкой о сработке: ${format(new Date(marker.recordedAt), 'd MMM, HH:mm', { locale: ru })}`} className="absolute top-0 h-2 w-1 bg-[var(--color-danger)]" style={{ left: `${markerProgress}%` }} />; })}</div></div>
    <div className="flex items-center gap-1" role="group" aria-label="Скорость воспроизведения">{speeds.map((value) => <Button key={value} size="sm" variant={speed === value ? 'secondary' : 'ghost'} onClick={() => setSpeed(value)}>{value}x</Button>)}</div>
  </footer>;
}
