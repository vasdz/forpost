'use client';

import { LocalSituationGate } from '@/components/features/LocalSituationState';
import { ObservedEventTable } from '@/components/features/ObservedEventTable';
import { PageHeader } from '@/components/features/PageHeader';
import { Table, type TableColumn } from '@/components/ui/Table';
import type { LocalSituationChannel, LocalSituationObject } from '@/data/localSituationContract';

type ChannelRow = LocalSituationChannel & { id: string };
type ObjectRow = LocalSituationObject & { id: string };

const channelColumns: TableColumn<ChannelRow>[] = [
  { key: 'channelId', label: 'ID канала', sortable: true, render: (row) => <span className="font-telemetry">{row.channelId}</span> },
  { key: 'sensorName', label: 'Наименование', sortable: true },
  { key: 'sensorType', label: 'Тип датчика', sortable: true },
  { key: 'engineeringSystemType', label: 'Система', sortable: true },
  { key: 'engineeringSystemTag', label: 'Тег', sortable: true },
];

const objectColumns: TableColumn<ObjectRow>[] = [
  { key: 'objectId', label: 'ID объекта', sortable: true, render: (row) => <span className="font-telemetry">{row.objectId}</span> },
  { key: 'dispatcherName', label: 'Наименование', sortable: true },
  { key: 'objectKind', label: 'Вид объекта', sortable: true },
  { key: 'hierarchyLevel', label: 'Уровень', sortable: true },
  { key: 'parentId', label: 'Родительский ID', render: (row) => row.parentId ?? 'Не указан' },
];

export default function RegistriesPage() {
  return <><PageHeader eyebrow="Локальный контур" title="Реестры наблюдаемого снимка" description="В этом разделе показаны только каналы, объекты и журнальные события из локального снимка. Реестры ОДС, АРМ-Контроль и оборудование не подключены." />
    <LocalSituationGate>{(snapshot) => <div className="space-y-6"><section><h2 className="mb-3 font-heading text-xl font-semibold">Каналы СМВУ</h2><Table ariaLabel="Каналы СМВУ" columns={channelColumns} rows={snapshot.channels.map((channel) => ({ ...channel, id: channel.channelId }))} /></section><section><h2 className="mb-3 font-heading text-xl font-semibold">Объекты</h2><Table ariaLabel="Объекты" columns={objectColumns} rows={snapshot.objects.map((object) => ({ ...object, id: object.objectId }))} /></section><section><h2 className="mb-3 font-heading text-xl font-semibold">Журнальные события</h2><ObservedEventTable events={snapshot.events} ariaLabel="Журнальные события" /></section></div>}</LocalSituationGate>
  </>;
}
