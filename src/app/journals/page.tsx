'use client';

import { useState } from 'react';
import { Download, Search } from 'lucide-react';

import { LocalSituationGate } from '@/components/features/LocalSituationState';
import { PageHeader } from '@/components/features/PageHeader';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Modal } from '@/components/ui/Modal';
import { Select } from '@/components/ui/Select';
import { Table, type TableColumn } from '@/components/ui/Table';
import type { LocalSituationEvent } from '@/data/localSituationContract';
import { selectObservedEventsAtTimeline } from '@/data/observedTimeline';
import { downloadCsv, toCsv } from '@/lib/csv';
import { useTimelineStore } from '@/stores/timelineStore';

type EventRow = LocalSituationEvent & { id: string };

const eventColumns: TableColumn<EventRow>[] = [
  { key: 'recordedAt', label: 'Время', sortable: true, render: (row) => <time className="font-telemetry" dateTime={row.recordedAt}>{row.recordedAt.replace('T', ' ')}</time> },
  { key: 'eventId', label: 'ID события', sortable: true, render: (row) => <span className="font-telemetry">{row.eventId}</span> },
  { key: 'channelId', label: 'Канал', sortable: true, render: (row) => <span className="font-telemetry">{row.channelId}</span> },
  { key: 'isAlarm', label: 'Состояние', render: (row) => row.isAlarm === true ? <Badge tone="critical">Сработка</Badge> : row.isAlarm === false ? <Badge tone="low">Штатно</Badge> : <Badge>Не указано</Badge> },
  { key: 'sensorValue', label: 'Значение', render: (row) => row.sensorValue || 'Не указано' },
];

export default function JournalsPage() {
  const { range, position } = useTimelineStore();
  const [query, setQuery] = useState('');
  const [alarm, setAlarm] = useState('all');
  const [selected, setSelected] = useState<EventRow | null>(null);

  return <><PageHeader eyebrow="Оперативный контур" title="Журнал технологических событий" description="Современная диспетчерская форма на основе подтверждённых журнальных наблюдений. Диапазон синхронизирован с общей временной шкалой; подтверждение и решения недоступны без пользовательской идентификации." />
    <LocalSituationGate>{(snapshot) => {
      const timelineEvents = selectObservedEventsAtTimeline(snapshot.events, range, position);
      const rows = timelineEvents
        .filter((event) => {
          const matchesAlarm = alarm === 'all'
            || (alarm === 'alarm' && event.isAlarm === true)
            || (alarm === 'normal' && event.isAlarm === false)
            || (alarm === 'unknown' && event.isAlarm === null);
          const normalized = query.trim().toLocaleLowerCase('ru');
          return matchesAlarm && (normalized === '' || [event.eventId, event.channelId, event.sensorValue]
            .some((value) => value.toLocaleLowerCase('ru').includes(normalized)));
        })
        .map((event) => ({ ...event, id: event.eventId }));
      const alarmCount = timelineEvents.filter((event) => event.isAlarm === true).length;
      const unknownCount = timelineEvents.filter((event) => event.isAlarm === null).length;
      const exportRows = () => downloadCsv('forpost-technology-events.csv', toCsv(rows, [
        { key: 'recordedAt', label: 'Время' }, { key: 'eventId', label: 'ID события' },
        { key: 'channelId', label: 'Канал' }, { key: 'isAlarm', label: 'Признак сработки' },
        { key: 'sensorValue', label: 'Значение' },
      ]));

      return <div className="space-y-4"><div className="grid grid-cols-1 gap-4 md:grid-cols-3"><Card><p className="eyebrow">События в окне</p><strong className="metric-value mt-3 block">{timelineEvents.length}</strong></Card><Card><p className="eyebrow">Со сработкой</p><strong className="metric-value mt-3 block">{alarmCount}</strong></Card><Card><p className="eyebrow">Без признака</p><strong className="metric-value mt-3 block">{unknownCount}</strong></Card></div><section aria-label="Фильтры журнала" className="surface p-4"><div className="flex flex-wrap items-end gap-3"><label className="min-w-64 flex-1 text-xs text-[var(--color-text-muted)]"><span className="mb-1 block">Поиск</span><span className="relative block"><Search className="pointer-events-none absolute left-3 top-3" size={15} aria-hidden="true" /><Input type="search" aria-label="Поиск по журналу событий" className="pl-9" value={query} onChange={(event) => setQuery(event.target.value)} /></span></label><Select label="Признак сработки" value={alarm} onChange={(event) => setAlarm(event.target.value)} options={[{ value: 'all', label: 'Все состояния' }, { value: 'alarm', label: 'Есть сработка' }, { value: 'normal', label: 'Нет сработки' }, { value: 'unknown', label: 'Не указано' }]} /><Button variant="secondary" onClick={exportRows} aria-label="Экспортировать журнал в CSV"><Download size={15} aria-hidden="true" />CSV</Button></div></section><Table ariaLabel="Журнал технологических событий" columns={eventColumns} rows={rows} onRowClick={setSelected} pageSize={12} /><Modal isOpen={selected !== null} onClose={() => setSelected(null)} title="Технологическое событие">{selected && <dl className="grid grid-cols-[140px_1fr] gap-3 text-sm"><dt className="text-[var(--color-text-muted)]">ID события</dt><dd className="font-telemetry">{selected.eventId}</dd><dt className="text-[var(--color-text-muted)]">Время</dt><dd className="font-telemetry">{selected.recordedAt}</dd><dt className="text-[var(--color-text-muted)]">Канал</dt><dd className="font-telemetry">{selected.channelId}</dd><dt className="text-[var(--color-text-muted)]">Значение</dt><dd>{selected.sensorValue || 'Не указано'}</dd><dt className="text-[var(--color-text-muted)]">Решение</dt><dd>Недоступно без доверенной пользовательской сессии</dd></dl>}</Modal></div>;
    }}</LocalSituationGate>
  </>;
}
