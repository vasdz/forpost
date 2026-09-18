'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { Download, Search } from 'lucide-react';

import { LocalSituationGate } from '@/components/features/LocalSituationState';
import { PageHeader } from '@/components/features/PageHeader';
import { SourceBadge } from '@/components/features/SourceBadge';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Modal } from '@/components/ui/Modal';
import { Select } from '@/components/ui/Select';
import { Table, type TableColumn } from '@/components/ui/Table';
import type { LocalSituationEvent } from '@/data/localSituationContract';
import {
  createServiceDraft,
  fetchIncidentDecisions,
  getDemoSession,
  recordIncidentDecision,
  startDemoSession,
  type IncidentDecision,
  type IncidentStatus,
} from '@/data/operationsClient';
import { selectObservedEventsAtTimeline } from '@/data/observedTimeline';
import { downloadCsv, toCsv } from '@/lib/csv';
import { useTimelineStore } from '@/stores/timelineStore';

type EventRow = LocalSituationEvent & { id: string; targetId: string };

const statusLabels: Record<IncidentStatus, string> = {
  new: 'Новая',
  in_review: 'На проверке',
  crew_dispatch: 'Бригада направлена',
  false_alarm: 'Ложная тревога',
  confirmed_incident: 'Инцидент подтверждён',
  closed: 'Закрыта',
};

const eventColumns: TableColumn<EventRow>[] = [
  { key: 'recordedAt', label: 'Время', sortable: true, render: (row) => <time className="font-telemetry" dateTime={row.recordedAt}>{row.recordedAt.replace('T', ' ')}</time> },
  { key: 'eventId', label: 'ID события', sortable: true, render: (row) => <span className="font-telemetry">{row.eventId}</span> },
  { key: 'channelId', label: 'Канал', sortable: true, render: (row) => <span className="font-telemetry">{row.channelId}</span> },
  { key: 'isAlarm', label: 'Состояние', render: (row) => row.isAlarm === true ? <Badge tone="critical">Сработка</Badge> : row.isAlarm === false ? <Badge tone="low">Штатно</Badge> : <Badge>Не указано</Badge> },
  { key: 'sensorValue', label: 'Значение', render: (row) => row.sensorValue || 'Не указано' },
  { key: 'provenance', label: 'Источник', render: (row) => <SourceBadge provenance={row.provenance} /> },
];

export default function JournalsPage() {
  const { range, position } = useTimelineStore();
  const [query, setQuery] = useState('');
  const [alarm, setAlarm] = useState('all');
  const [selected, setSelected] = useState<EventRow | null>(null);
  const [decisions, setDecisions] = useState<IncidentDecision[]>([]);
  const [csrfToken, setCsrfToken] = useState<string>();
  const [decisionStatus, setDecisionStatus] = useState<IncidentStatus>('in_review');
  const [reason, setReason] = useState('');
  const [actionError, setActionError] = useState<string>();
  const [actionMessage, setActionMessage] = useState<string>();
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let active = true;
    getDemoSession()
      .then((session) => { if (active) setCsrfToken(session?.csrfToken); })
      .catch(() => { if (active) setCsrfToken(undefined); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    if (selected?.isAlarm !== true) {
      setDecisions([]);
      return () => { active = false; };
    }
    fetchIncidentDecisions(selected.canonicalId)
      .then((result) => { if (active) setDecisions(result); })
      .catch(() => { if (active) setDecisions([]); });
    return () => { active = false; };
  }, [selected]);

  async function login() {
    setSubmitting(true);
    setActionError(undefined);
    try {
      const session = await startDemoSession('central-dispatcher');
      setCsrfToken(session.csrfToken);
      setActionMessage('Demo-сессия диспетчера ОДС активна 5 минут.');
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Не удалось открыть demo-сессию');
    } finally {
      setSubmitting(false);
    }
  }

  async function submitDecision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (selected === null || csrfToken === undefined) return;
    setSubmitting(true);
    setActionError(undefined);
    setActionMessage(undefined);
    try {
      const stored = await recordIncidentDecision(
        selected.canonicalId,
        { status: decisionStatus, reason: reason.trim() },
        csrfToken,
        crypto.randomUUID(),
      );
      setDecisions((current) => [...current, stored]);
      setReason('');
      setActionMessage('Решение сохранено в неизменяемой истории.');
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Решение не сохранено');
    } finally {
      setSubmitting(false);
    }
  }

  async function createDraft() {
    if (selected === null || csrfToken === undefined) return;
    setSubmitting(true);
    setActionError(undefined);
    setActionMessage(undefined);
    const dueAt = new Date(Date.now() + 24 * 60 * 60 * 1_000).toISOString();
    try {
      await createServiceDraft({
        incidentId: selected.canonicalId,
        targetId: selected.targetId,
        category: 'sensor_check',
        priority: 'high',
        recommendedAction: 'Проверить канал, датчик и линию связи на объекте',
        dueAt,
      }, csrfToken);
      setActionMessage('Локальный черновик создан. Во внешнюю help-desk он не отправлен.');
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Черновик не создан');
    } finally {
      setSubmitting(false);
    }
  }

  return <>
    <PageHeader eyebrow="Оперативный контур" title="Журнал технологических событий" description="Диспетчерская форма на основе подтверждённых журнальных наблюдений. Решения не удаляют исходное событие и сохраняются отдельной историей." />
    <LocalSituationGate>{(snapshot) => {
      const timelineEvents = selectObservedEventsAtTimeline(snapshot.events, range, position);
      const channelTargets = new Map(snapshot.channels.map((channel) => [channel.channelId, channel.objectId ?? channel.channelId]));
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
        .map((event) => ({ ...event, id: event.canonicalId, targetId: channelTargets.get(event.channelId) ?? event.channelId }));
      const alarmCount = timelineEvents.filter((event) => event.isAlarm === true).length;
      const unknownCount = timelineEvents.filter((event) => event.isAlarm === null).length;
      const exportRows = () => downloadCsv('forpost-technology-events.csv', toCsv(rows, [
        { key: 'recordedAt', label: 'Время' }, { key: 'canonicalId', label: 'Канонический ID' },
        { key: 'eventId', label: 'ID источника' }, { key: 'channelId', label: 'Канал' },
        { key: 'isAlarm', label: 'Признак сработки' }, { key: 'sensorValue', label: 'Значение' },
        { key: 'qualityCode', label: 'Качество' }, { key: 'provenance', label: 'Происхождение' },
      ]));

      return <div className="space-y-4">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3"><Card><p className="eyebrow">События в окне</p><strong className="metric-value mt-3 block">{timelineEvents.length}</strong></Card><Card><p className="eyebrow">Со сработкой</p><strong className="metric-value mt-3 block">{alarmCount}</strong></Card><Card><p className="eyebrow">Без признака</p><strong className="metric-value mt-3 block">{unknownCount}</strong></Card></div>
        <section aria-label="Фильтры журнала" className="surface p-4"><div className="flex flex-wrap items-end gap-3"><label className="min-w-64 flex-1 text-xs text-[var(--color-text-muted)]"><span className="mb-1 block">Поиск</span><span className="relative block"><Search className="pointer-events-none absolute left-3 top-3" size={15} aria-hidden="true" /><Input type="search" aria-label="Поиск по журналу событий" className="pl-9" value={query} onChange={(event) => setQuery(event.target.value)} /></span></label><Select label="Признак сработки" value={alarm} onChange={(event) => setAlarm(event.target.value)} options={[{ value: 'all', label: 'Все состояния' }, { value: 'alarm', label: 'Есть сработка' }, { value: 'normal', label: 'Нет сработки' }, { value: 'unknown', label: 'Не указано' }]} /><Button variant="secondary" onClick={exportRows} aria-label="Экспортировать журнал в CSV"><Download size={15} aria-hidden="true" />CSV</Button></div></section>
        <Table ariaLabel="Журнал технологических событий" columns={eventColumns} rows={rows} onRowClick={(row) => { setSelected(row); setActionError(undefined); setActionMessage(undefined); }} pageSize={12} />
      </div>;
    }}</LocalSituationGate>
    <Modal isOpen={selected !== null} onClose={() => setSelected(null)} title={selected?.isAlarm === true ? 'Карточка инцидента' : 'Технологическое событие'}>
      {selected && <div className="space-y-5">
        <div className="flex flex-wrap gap-2"><SourceBadge provenance={selected.provenance} />{selected.qualityCode !== 'valid' && <Badge tone="high">Качество: {selected.qualityCode}</Badge>}</div>
        <dl className="grid grid-cols-[140px_1fr] gap-3 text-sm"><dt className="text-[var(--color-text-muted)]">ID источника</dt><dd className="font-telemetry">{selected.eventId}</dd><dt className="text-[var(--color-text-muted)]">Канонический ID</dt><dd className="break-all font-telemetry text-xs">{selected.canonicalId}</dd><dt className="text-[var(--color-text-muted)]">Время</dt><dd className="font-telemetry">{selected.recordedAt}</dd><dt className="text-[var(--color-text-muted)]">Канал</dt><dd className="font-telemetry">{selected.channelId}</dd><dt className="text-[var(--color-text-muted)]">Значение</dt><dd>{selected.sensorValue || 'Не указано'}</dd></dl>
        {selected.isAlarm === true && <section aria-labelledby="incident-actions-title" className="border-t border-[var(--color-border)] pt-5"><h3 id="incident-actions-title" className="font-heading text-base font-semibold">Решение диспетчера</h3>{csrfToken === undefined ? <div className="mt-3"><p className="mb-3 text-sm text-[var(--color-text-muted)]">Запись доступна только после короткоживущей локальной demo-сессии.</p><Button onClick={login} disabled={submitting}>Войти как диспетчер ОДС</Button></div> : <form className="mt-4 space-y-4" onSubmit={submitDecision}><Select label="Статус" value={decisionStatus} onChange={(event) => setDecisionStatus(event.target.value as IncidentStatus)} options={Object.entries(statusLabels).map(([value, label]) => ({ value, label }))} /><label className="grid gap-1 text-xs text-[var(--color-text-muted)]">Причина решения<textarea aria-label="Причина решения" className="control-surface min-h-24 rounded-[4px] px-3.5 py-2 text-sm text-[var(--color-text)]" value={reason} maxLength={1000} onChange={(event) => setReason(event.target.value)} /></label><div className="flex flex-wrap gap-2"><Button type="submit" disabled={submitting || reason.trim().length < 5}>Сохранить решение</Button><Button variant="secondary" onClick={createDraft} disabled={submitting}>Создать локальный черновик</Button></div></form>}</section>}
        {actionError && <p role="alert" className="border-l-2 border-l-[var(--color-danger)] p-3 text-sm">{actionError}</p>}{actionMessage && <p role="status" className="border-l-2 border-l-[var(--color-success)] p-3 text-sm">{actionMessage}</p>}
        {selected.isAlarm === true && <section aria-labelledby="decision-history-title"><h3 id="decision-history-title" className="mb-2 font-heading text-base font-semibold">История решений</h3>{decisions.length === 0 ? <p className="text-sm text-[var(--color-text-muted)]">Решения пока не зафиксированы.</p> : <ol className="space-y-2">{decisions.map((decision) => <li key={decision.decisionId} className="surface-subtle p-3 text-sm"><div className="mb-1 flex flex-wrap items-center gap-2"><Badge tone="medium">{statusLabels[decision.status]}</Badge><SourceBadge provenance={decision.provenance} /><time className="font-telemetry text-xs" dateTime={decision.createdAt}>{new Date(decision.createdAt).toLocaleString('ru-RU')}</time></div><p>{decision.reason}</p></li>)}</ol>}</section>}
      </div>}
    </Modal>
  </>;
}
