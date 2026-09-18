'use client';

import { Chart } from '@/components/charts/Chart';
import { DonutChart } from '@/components/charts/DonutChart';
import { Card } from '@/components/ui/Card';
import { buildObservedActivityOption } from '@/components/charts/chartOptions';
import { aggregateObservedEvents } from '@/data/observedAnalytics';
import type { LocalSituationEvent } from '@/data/localSituationContract';

export function ObservedEventCharts({ events }: { events: readonly LocalSituationEvent[] }) {
  const { buckets, statuses } = aggregateObservedEvents(events);
  const visibleBuckets = buckets.slice(-24);

  return <>
    <Card className="col-span-12 xl:col-span-8">
      <h2 className="mb-1 font-heading text-xl font-semibold">Динамика наблюдаемых событий</h2>
      <p className="mb-4 text-xs text-[var(--color-text-muted)]">Почасовые количества из выбранного окна; это факты журнала, не прогноз риска.</p>
      <Chart
        label="Почасовая динамика наблюдаемых событий"
        description="Количество всех событий и событий с отметкой о сработке по часам."
        option={buildObservedActivityOption(visibleBuckets)}
        height={280}
        columns={['Час', 'Все события', 'Со сработкой']}
        rows={visibleBuckets.map((bucket) => [bucket.at.replace('T', ' '), bucket.events, bucket.alarms])}
      />
    </Card>
    <Card className="col-span-12 xl:col-span-4">
      <h2 className="mb-1 font-heading text-xl font-semibold">Структура отметок</h2>
      <p className="mb-4 text-xs text-[var(--color-text-muted)]">Состояния поля сработки в выбранном окне.</p>
      <DonutChart label="Структура отметок о сработке" items={statuses} />
    </Card>
  </>;
}
