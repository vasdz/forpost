'use client';

import { LocalSituationGate } from '@/components/features/LocalSituationState';
import { ObservedEventTable } from '@/components/features/ObservedEventTable';
import { ObservedEventCharts } from '@/components/features/ObservedEventCharts';
import { PageHeader } from '@/components/features/PageHeader';
import { Card } from '@/components/ui/Card';
import { Table, type TableColumn } from '@/components/ui/Table';
import type { LocalSituationChannel, LocalSituationObject } from '@/data/localSituationContract';
import { selectObservedEventsAtTimeline } from '@/data/observedTimeline';
import { useTimelineStore } from '@/stores/timelineStore';

type ChannelRow = LocalSituationChannel & { id: string };
type ObjectRow = LocalSituationObject & { id: string };

const channelColumns: TableColumn<ChannelRow>[] = [
  { key: 'channelId', label: 'ID канала', sortable: true, render: (row) => <span className="font-telemetry">{row.channelId}</span> },
  { key: 'sensorName', label: 'Наименование датчика', sortable: true },
  { key: 'sensorType', label: 'Тип датчика', sortable: true },
  { key: 'engineeringSystemType', label: 'Система', sortable: true },
];

const objectColumns: TableColumn<ObjectRow>[] = [
  { key: 'objectId', label: 'ID объекта', sortable: true, render: (row) => <span className="font-telemetry">{row.objectId}</span> },
  { key: 'dispatcherName', label: 'Наименование', sortable: true },
  { key: 'objectKind', label: 'Вид объекта', sortable: true },
  { key: 'hierarchyLevel', label: 'Уровень иерархии', sortable: true },
];

function ObservationMetric({ label, value, note }: { label: string; value: number; note: string }) {
  return <Card className="col-span-12 min-h-40 sm:col-span-6 xl:col-span-3"><p className="eyebrow">{label}</p><strong className="metric-value mt-4 block">{value}</strong><p className="mt-3 text-xs text-[var(--color-text-muted)]">{note}</p></Card>;
}

export default function OverviewPage() {
  const { range, position } = useTimelineStore();
  return <><PageHeader eyebrow="Локальный контур" title="Наблюдаемая оперативная обстановка" description="Сводка ограниченного локального обезличенного снимка: журнальные события, каналы и объекты. Прогнозы, риски и рекомендации здесь не формируются." />
    <LocalSituationGate>{(snapshot) => {
      const visibleEvents = selectObservedEventsAtTimeline(snapshot.events, range, position);
      const alarmCount = visibleEvents.filter((event) => event.isAlarm === true).length;
      return <div className="page-grid">
        <ObservationMetric label="Наблюдаемые события" value={visibleEvents.length} note="В выбранном окне временной шкалы" />
        <ObservationMetric label="Каналы" value={snapshot.channels.length} note="Каналы из локального снимка" />
        <ObservationMetric label="Объекты" value={snapshot.objects.length} note="Объекты из локального снимка" />
        <ObservationMetric label="Отметки о сработке" value={alarmCount} note="Это журналная отметка, не оценка риска" />
        <ObservedEventCharts events={visibleEvents} />
        <section className="col-span-12"><h2 className="mb-3 font-heading text-xl font-semibold">Журнал наблюдаемых событий</h2><ObservedEventTable events={visibleEvents} ariaLabel="Журнал наблюдаемых событий" /></section>
        <section className="col-span-12 xl:col-span-7"><h2 className="mb-3 font-heading text-xl font-semibold">Каналы в снимке</h2><Table ariaLabel="Каналы в снимке" columns={channelColumns} rows={snapshot.channels.map((channel) => ({ ...channel, id: channel.channelId }))} pageSize={5} /></section>
        <section className="col-span-12 xl:col-span-5"><h2 className="mb-3 font-heading text-xl font-semibold">Объекты в снимке</h2><Table ariaLabel="Объекты в снимке" columns={objectColumns} rows={snapshot.objects.map((object) => ({ ...object, id: object.objectId }))} pageSize={5} /></section>
      </div>;
    }}</LocalSituationGate>
  </>;
}
