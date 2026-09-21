'use client';

import { LocalSituationGate } from '@/components/features/LocalSituationState';
import { ObservedEventTable } from '@/components/features/ObservedEventTable';
import { PageHeader } from '@/components/features/PageHeader';
import { PredictionPanel } from '@/components/features/PredictionCapability';
import { Table, type TableColumn } from '@/components/ui/Table';
import type { LocalSituationChannel } from '@/data/localSituationContract';

type ChannelRow = LocalSituationChannel & { id: string };

const channelColumns: TableColumn<ChannelRow>[] = [
  { key: 'channelId', label: 'ID канала', sortable: true, render: (row) => <span className="font-telemetry">{row.channelId}</span> },
  { key: 'sensorName', label: 'Наименование датчика', sortable: true },
  { key: 'sensorType', label: 'Тип датчика', sortable: true },
  { key: 'engineeringSystemType', label: 'Инженерная система', sortable: true },
  { key: 'engineeringSystemTag', label: 'Тег системы', sortable: true },
];

export default function SensorFailurePage() {
  return <><PageHeader eyebrow="Наблюдения СМВУ" title="Наблюдения по каналам датчиков" description="Фактические записи локального снимка дополнены проверенным ML-экспортом, когда модель проходит контроль качества." />
    <PredictionPanel type="sensor_failure" unavailableDescription="Валидированный экспорт модели отказа пока отсутствует." />
    <LocalSituationGate>{(snapshot) => <div className="mt-6 space-y-6"><section><h2 className="mb-3 font-heading text-xl font-semibold">Каналы датчиков</h2><Table ariaLabel="Каналы датчиков" columns={channelColumns} rows={snapshot.channels.map((channel) => ({ ...channel, id: channel.channelId }))} pageSize={10} /></section><section><h2 className="mb-3 font-heading text-xl font-semibold">Наблюдения датчиков</h2><ObservedEventTable events={snapshot.events} ariaLabel="Наблюдения датчиков" /></section></div>}</LocalSituationGate>
  </>;
}
