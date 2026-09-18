'use client';

import { useEffect, useState } from 'react';

import { PageHeader } from '@/components/features/PageHeader';
import { SourceBadge } from '@/components/features/SourceBadge';
import { Badge } from '@/components/ui/Badge';
import { Table, type TableColumn } from '@/components/ui/Table';
import { fetchServiceDrafts, type ServiceRequestDraft } from '@/data/operationsClient';

type DraftRow = ServiceRequestDraft & { id: string };

const priorityLabels = {
  low: 'Низкий', medium: 'Средний', high: 'Высокий', critical: 'Критический',
} as const;

const columns: TableColumn<DraftRow>[] = [
  { key: 'draftId', label: 'Черновик', render: (row) => <span className="font-telemetry text-xs">{row.draftId}</span> },
  { key: 'targetId', label: 'Объект / канал', sortable: true, render: (row) => <span className="font-telemetry">{row.targetId}</span> },
  { key: 'recommendedAction', label: 'Рекомендуемое действие' },
  { key: 'priority', label: 'Приоритет', sortable: true, render: (row) => <Badge tone={row.priority === 'critical' ? 'critical' : row.priority === 'high' ? 'high' : 'medium'}>{priorityLabels[row.priority]}</Badge> },
  { key: 'dueAt', label: 'Срок', sortable: true, render: (row) => <time dateTime={row.dueAt} className="font-telemetry text-xs">{new Date(row.dueAt).toLocaleString('ru-RU')}</time> },
  { key: 'provenance', label: 'Происхождение', render: (row) => <SourceBadge provenance={row.provenance} /> },
];

export default function ApplicationsPage() {
  const [drafts, setDrafts] = useState<ServiceRequestDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();

  useEffect(() => {
    let active = true;
    fetchServiceDrafts()
      .then((result) => { if (active) setDrafts(result); })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : 'Неизвестная ошибка'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const rows: DraftRow[] = drafts.map((draft) => ({ ...draft, id: draft.draftId }));
  return <>
    <PageHeader eyebrow="Оперативные действия" title="Черновики заявок" description="Локальные черновики demo help-desk. Они сохраняются для сценария диспетчера, но не считаются отправленными во внешнюю систему." />
    <div className="mb-4 flex flex-wrap items-center gap-3 border-l-2 border-l-[var(--color-warning)] bg-[var(--color-panel)] p-4 text-sm"><SourceBadge provenance="simulated" /><span>Отправка в корпоративную help-desk не выполняется.</span></div>
    <Table ariaLabel="Локальные черновики заявок" columns={columns} rows={rows} loading={loading} error={error} pageSize={12} />
  </>;
}
