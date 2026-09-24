import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { LocalSituationEvent } from '@/data/localSituationContract';
import { ObservedEventCharts } from './ObservedEventCharts';

vi.mock('echarts-for-react', () => ({ default: () => null }));

const events: LocalSituationEvent[] = [
  { canonicalId: '1'.repeat(64), eventId: '1', channelId: 'a', recordedAt: '2026-08-01T10:01:00', isAlarm: true, sensorValue: '1', qualityCode: 'valid', analysisEligible: true, provenance: 'observed' },
  { canonicalId: '2'.repeat(64), eventId: '2', channelId: 'a', recordedAt: '2026-08-01T12:01:00', isAlarm: false, sensorValue: '2', qualityCode: 'valid', analysisEligible: true, provenance: 'observed' },
];

describe('ObservedEventCharts', () => {
  it('раскрывает границы, выборку, актуальность и семантику времени', () => {
    render(<ObservedEventCharts
      events={events}
      window={{ startAt: '2026-08-01T10:00:00', endAt: '2026-08-01T12:59:59' }}
      freshness="historical"
    />);

    expect(screen.getByText(/01\.08\.2026 10:00–01\.08\.2026 12:59/)).toBeInTheDocument();
    expect(screen.getByText(/2 записи/)).toBeInTheDocument();
    expect(screen.getByText(/исторический снимок/)).toBeInTheDocument();
    expect(screen.getByText(/часовой пояс в источнике не указан/)).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '2026-08-01 11:00:00' })).toBeInTheDocument();
  });
});
