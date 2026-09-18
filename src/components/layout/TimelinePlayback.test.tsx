import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useTimelineStore } from '@/stores/timelineStore';
import { TimelinePlayback } from './TimelinePlayback';

const localSituationState = vi.hoisted(() => ({
  value: {
    status: 'ready' as const,
    snapshot: {
      sourceAvailability: { events: true, channels: true, objects: true, access_events: false, maintenance_history: false, ml_predictions: false, work_permits: false },
      channels: [],
      objects: [],
      events: [{ eventId: 'event-1', channelId: 'channel-1', recordedAt: '2026-08-02T12:00:00', isAlarm: true, sensorValue: 'value' }],
    },
  },
}));

vi.mock('@/data/LocalSituationProvider', () => ({
  useLocalSituation: () => localSituationState.value,
}));

describe('TimelinePlayback', () => {
  beforeEach(() => {
    useTimelineStore.getState().reset();
  });

  it('показывает управление только после загрузки наблюдаемого события', async () => {
    render(<TimelinePlayback />);

    expect(screen.getByLabelText('Воспроизведение временной шкалы')).toHaveClass('glass-surface-subtle');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Воспроизвести' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Воспроизвести' }));
    expect(useTimelineStore.getState().isPlaying).toBe(true);
    expect(screen.getByRole('button', { name: /Событие с отметкой о сработке/i })).toBeInTheDocument();
  });
});
