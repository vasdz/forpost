'use client';

import { useMemo, useState } from 'react';
import { Download, Search } from 'lucide-react';

import { LocalSituationGate } from '@/components/features/LocalSituationState';
import { PageHeader } from '@/components/features/PageHeader';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { Modal } from '@/components/ui/Modal';
import { Select } from '@/components/ui/Select';
import { Table, type TableColumn } from '@/components/ui/Table';
import { Tabs } from '@/components/ui/Tabs';
import type { LocalSituationChannel, LocalSituationObject } from '@/data/localSituationContract';
import { downloadCsv, toCsv } from '@/lib/csv';

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

function includesQuery(values: readonly unknown[], query: string): boolean {
  const normalized = query.trim().toLocaleLowerCase('ru');
  return normalized === '' || values.some((value) => String(value ?? '').toLocaleLowerCase('ru').includes(normalized));
}

function DetailList({ items }: { items: Array<[string, string | null]> }) {
  return <dl className="grid grid-cols-[minmax(140px,0.35fr)_1fr] gap-x-6 gap-y-3 text-sm">{items.map(([label, value]) => <div key={label} className="contents"><dt className="text-[var(--color-text-muted)]">{label}</dt><dd className="font-telemetry break-all">{value || 'Не указано'}</dd></div>)}</dl>;
}

function ObjectsRegistry({ objects }: { objects: readonly LocalSituationObject[] }) {
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState('');
  const [selected, setSelected] = useState<ObjectRow | null>(null);
  const kinds = useMemo(() => [...new Set(objects.map((item) => item.objectKind).filter(Boolean))].sort(), [objects]);
  const rows = useMemo(() => objects
    .filter((item) => (kind === '' || item.objectKind === kind) && includesQuery(Object.values(item), query))
    .map((item) => ({ ...item, id: item.objectId })), [kind, objects, query]);
  const exportRows = () => downloadCsv('forpost-objects.csv', toCsv(rows, [
    { key: 'objectId', label: 'ID объекта' }, { key: 'dispatcherName', label: 'Наименование' },
    { key: 'objectKind', label: 'Вид объекта' }, { key: 'hierarchyLevel', label: 'Уровень' },
    { key: 'parentId', label: 'Родительский ID' },
  ]));

  return <section aria-labelledby="objects-title"><h2 id="objects-title" className="font-heading text-xl font-semibold">Объекты локального снимка</h2><p className="mt-1 text-xs text-[var(--color-text-muted)]">Показывается доступная иерархия объектов; полноценный реестр оборудования пока не подключён.</p><div className="my-4 flex flex-wrap items-end gap-3"><label className="min-w-64 flex-1 text-xs text-[var(--color-text-muted)]"><span className="mb-1 block">Поиск</span><span className="relative block"><Search className="pointer-events-none absolute left-3 top-3" size={15} aria-hidden="true" /><Input type="search" aria-label="Поиск по реестру оборудования" className="pl-9" value={query} onChange={(event) => setQuery(event.target.value)} /></span></label><Select label="Вид объекта" value={kind} onChange={(event) => setKind(event.target.value)} options={[{ value: '', label: 'Все виды' }, ...kinds.map((value) => ({ value, label: value }))]} /><Button variant="secondary" onClick={exportRows} aria-label="Экспортировать оборудование в CSV"><Download size={15} aria-hidden="true" />CSV</Button></div><Table ariaLabel="Объекты" columns={objectColumns} rows={rows} onRowClick={setSelected} /><Modal isOpen={selected !== null} onClose={() => setSelected(null)} title="Карточка объекта">{selected && <DetailList items={[[ 'ID объекта', selected.objectId ], [ 'Наименование', selected.dispatcherName ], [ 'Вид объекта', selected.objectKind ], [ 'Уровень иерархии', selected.hierarchyLevel ], [ 'Родительский ID', selected.parentId ]]} />}</Modal></section>;
}

function SensorsRegistry({ channels }: { channels: readonly LocalSituationChannel[] }) {
  const [query, setQuery] = useState('');
  const [sensorType, setSensorType] = useState('');
  const [selected, setSelected] = useState<ChannelRow | null>(null);
  const types = useMemo(() => [...new Set(channels.map((item) => item.sensorType).filter(Boolean))].sort(), [channels]);
  const rows = useMemo(() => channels
    .filter((item) => (sensorType === '' || item.sensorType === sensorType) && includesQuery(Object.values(item), query))
    .map((item) => ({ ...item, id: item.channelId })), [channels, query, sensorType]);
  const exportRows = () => downloadCsv('forpost-sensors.csv', toCsv(rows, [
    { key: 'channelId', label: 'ID канала' }, { key: 'sensorName', label: 'Наименование' },
    { key: 'sensorType', label: 'Тип датчика' }, { key: 'engineeringSystemType', label: 'Система' },
    { key: 'engineeringSystemTag', label: 'Тег' },
  ]));

  return <section aria-labelledby="sensors-title"><h2 id="sensors-title" className="font-heading text-xl font-semibold">Каналы и датчики СМВУ</h2><div className="my-4 flex flex-wrap items-end gap-3"><label className="min-w-64 flex-1 text-xs text-[var(--color-text-muted)]"><span className="mb-1 block">Поиск</span><span className="relative block"><Search className="pointer-events-none absolute left-3 top-3" size={15} aria-hidden="true" /><Input type="search" aria-label="Поиск по реестру датчиков" className="pl-9" value={query} onChange={(event) => setQuery(event.target.value)} /></span></label><Select label="Тип датчика" value={sensorType} onChange={(event) => setSensorType(event.target.value)} options={[{ value: '', label: 'Все типы' }, ...types.map((value) => ({ value, label: value }))]} /><Button variant="secondary" onClick={exportRows} aria-label="Экспортировать датчики в CSV"><Download size={15} aria-hidden="true" />CSV</Button></div><Table ariaLabel="Каналы СМВУ" columns={channelColumns} rows={rows} onRowClick={setSelected} /><Modal isOpen={selected !== null} onClose={() => setSelected(null)} title="Карточка датчика">{selected && <DetailList items={[[ 'ID канала', selected.channelId ], [ 'Наименование', selected.sensorName ], [ 'Тип датчика', selected.sensorType ], [ 'Инженерная система', selected.engineeringSystemType ], [ 'Тег системы', selected.engineeringSystemTag ]]} />}</Modal></section>;
}

function UnavailableRegistry({ title, description }: { title: string; description: string }) {
  return <EmptyState title={title} description={description} />;
}

export default function RegistriesPage() {
  return <><PageHeader eyebrow="Локальный контур" title="Реестры наблюдаемого снимка" description="Поиск, проверка и экспорт доступных обезличенных объектов и каналов. Неподключённые источники явно отмечены и не подменяются демонстрационными данными." />
    <LocalSituationGate>{(snapshot) => <Tabs tabs={[
      { id: 'equipment', label: 'Оборудование', content: <ObjectsRegistry objects={snapshot.objects} /> },
      { id: 'sensors', label: 'Датчики', content: <SensorsRegistry channels={snapshot.channels} /> },
      { id: 'ods', label: 'Журналы ОДС', content: <UnavailableRegistry title="Журналы ОДС недоступны" description="Источник журналов ОДС не подтверждён в текущем локальном контракте." /> },
      { id: 'arm', label: 'АРМ-Контроль', content: <UnavailableRegistry title="АРМ-Контроль недоступен" description="Интеграция допусков и заявок АРМ-Контроль не подключена." /> },
    ]} />}</LocalSituationGate>
  </>;
}
