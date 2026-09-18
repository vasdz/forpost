import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { LocalSituationProvider, useLocalSituation } from './LocalSituationProvider';
import { fetchLocalSituation } from './localSituationClient';

vi.mock('./localSituationClient', async (importOriginal) => ({
  ...await importOriginal<typeof import('./localSituationClient')>(),
  fetchLocalSituation: vi.fn(),
}));

const observedSnapshot = {
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
    latestObservedAt: null,
    eventCount: 0,
    skippedTimestampCount: 0,
    technicalAnomalyCount: 0,
    unmappedChannelCount: 0,
    objectLinkAvailable: false,
    freshness: 'historical' as const,
  },
  channels: [],
  objects: [],
  events: [],
};

function StatusProbe() {
  const state = useLocalSituation();
  return <output>{state.status}</output>;
}

describe('LocalSituationProvider', () => {
  beforeEach(() => {
    vi.mocked(fetchLocalSituation).mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it('сохраняет состояние загрузки до получения проверенного снимка', async () => {
    let resolveLoad: ((value: Awaited<ReturnType<typeof fetchLocalSituation>>) => void) | undefined;
    vi.mocked(fetchLocalSituation).mockReturnValue(new Promise((resolve) => {
      resolveLoad = resolve;
    }));

    render(<LocalSituationProvider><StatusProbe /></LocalSituationProvider>);
    expect(screen.getByText('loading')).toBeInTheDocument();

    resolveLoad?.({ status: 'ready', snapshot: observedSnapshot });

    await waitFor(() => expect(screen.getByText('ready')).toBeInTheDocument());
  });

  it('передаёт недоступность без резервного снимка', async () => {
    vi.mocked(fetchLocalSituation).mockResolvedValue({
      status: 'unavailable',
      message: 'Локальный снимок данных недоступен.',
    });

    render(<LocalSituationProvider><StatusProbe /></LocalSituationProvider>);

    await waitFor(() => expect(screen.getByText('unavailable')).toBeInTheDocument());
  });

  it('повторно запрашивает снимок через 60 секунд', async () => {
    vi.useFakeTimers();
    vi.mocked(fetchLocalSituation).mockResolvedValue({ status: 'ready', snapshot: observedSnapshot });

    render(<LocalSituationProvider><StatusProbe /></LocalSituationProvider>);
    await act(async () => { await Promise.resolve(); });
    expect(fetchLocalSituation).toHaveBeenCalledTimes(1);

    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });

    expect(fetchLocalSituation).toHaveBeenCalledTimes(2);
    expect(screen.getByText('ready')).toBeInTheDocument();
  });

  it('сохраняет последний рабочий снимок при ошибке обновления', async () => {
    vi.useFakeTimers();
    vi.mocked(fetchLocalSituation)
      .mockResolvedValueOnce({ status: 'ready', snapshot: observedSnapshot })
      .mockResolvedValueOnce({
        status: 'unavailable',
        message: 'Локальный снимок данных недоступен.',
      });

    render(<LocalSituationProvider><StatusProbe /></LocalSituationProvider>);
    await act(async () => { await Promise.resolve(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });

    expect(screen.getByText('ready')).toBeInTheDocument();
  });

  it('не запускает параллельное обновление', async () => {
    vi.useFakeTimers();
    let resolveRefresh: ((value: Awaited<ReturnType<typeof fetchLocalSituation>>) => void) | undefined;
    vi.mocked(fetchLocalSituation)
      .mockResolvedValueOnce({ status: 'ready', snapshot: observedSnapshot })
      .mockReturnValueOnce(new Promise((resolve) => { resolveRefresh = resolve; }));

    render(<LocalSituationProvider><StatusProbe /></LocalSituationProvider>);
    await act(async () => { await Promise.resolve(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(120_000); });

    expect(fetchLocalSituation).toHaveBeenCalledTimes(2);
    resolveRefresh?.({ status: 'ready', snapshot: observedSnapshot });
  });
});
