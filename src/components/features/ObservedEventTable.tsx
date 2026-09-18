'use client';

import type { LocalSituationEvent } from '@/data/localSituationContract';
import { Table, type TableColumn } from '@/components/ui/Table';

type ObservedEventRow = LocalSituationEvent & { id: string };

const columns: TableColumn<ObservedEventRow>[] = [
  { key: 'eventId', label: 'ID события', sortable: true, render: (row) => <span className="font-telemetry">{row.eventId}</span> },
  { key: 'recordedAt', label: 'Время наблюдения', sortable: true, render: (row) => <time className="font-telemetry" dateTime={row.recordedAt}>{row.recordedAt.replace('T', ' ')}</time> },
  { key: 'channelId', label: 'Канал', sortable: true, render: (row) => <span className="font-telemetry">{row.channelId}</span> },
  { key: 'isAlarm', label: 'Отметка о сработке', render: (row) => row.isAlarm === true ? 'Есть отметка' : row.isAlarm === false ? 'Нет отметки' : 'Не указана' },
  { key: 'sensorValue', label: 'Значение из журнала', render: (row) => row.sensorValue || 'Не указано' },
];

export function ObservedEventTable({ events, ariaLabel }: { events: readonly LocalSituationEvent[]; ariaLabel: string }) {
  const rows = [...events]
    .sort((left, right) => right.recordedAt.localeCompare(left.recordedAt))
    .map((event) => ({ ...event, id: event.eventId }));

  return <Table ariaLabel={ariaLabel} columns={columns} rows={rows} pageSize={10} />;
}
