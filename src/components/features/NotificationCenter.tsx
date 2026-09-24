'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { AlertTriangle, BellRing, CheckCircle2 } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Modal } from '@/components/ui/Modal';
import { Select } from '@/components/ui/Select';
import { useLocalSituation } from '@/data/LocalSituationProvider';
import type { LocalSituationEvent } from '@/data/localSituationContract';
import {
  createPredictionServiceDraft,
  getDemoSession,
  recordPredictionDecision,
  startDemoSession,
  type PredictionDecision,
} from '@/data/operationsClient';
import { buildOperationalNotifications, type OperationalNotification } from '@/data/operationalNotifications';
import { fetchPredictionFeed, type PredictionFeed } from '@/data/predictionsClient';

const priorityLabels: Record<OperationalNotification['priority'], string> = {
  critical: 'Критический', high: 'Высокий', medium: 'Средний', low: 'Низкий',
};

const decisionOptions = [
  { value: 'confirmed', label: 'Подтвердить риск' },
  { value: 'escalated', label: 'Эскалировать' },
  { value: 'rejected', label: 'Отклонить прогноз' },
];

export function NotificationCenter() {
  const localSituation = useLocalSituation();
  const [feed, setFeed] = useState<PredictionFeed | null>(null);
  const [selected, setSelected] = useState<OperationalNotification | null>(null);
  const [csrfToken, setCsrfToken] = useState<string>();
  const [decision, setDecision] = useState<PredictionDecision>('confirmed');
  const [reason, setReason] = useState('');
  const [decisionStored, setDecisionStored] = useState(false);
  const [draftStored, setDraftStored] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string>();
  const [error, setError] = useState<string>();

  useEffect(() => {
    let active = true;
    void Promise.all([fetchPredictionFeed(), getDemoSession().catch(() => null)]).then(([predictionFeed, session]) => {
      if (!active) return;
      setFeed(predictionFeed);
      setCsrfToken(session?.csrfToken);
    });
    return () => { active = false; };
  }, []);

  const notifications = feed?.status === 'ready' ? buildOperationalNotifications(feed.predictions) : [];
  const telemetry = selected === null || localSituation.status !== 'ready'
    ? []
    : localSituation.snapshot.events
      .filter((event) => event.channelId === selected.entityId)
      .toSorted((left, right) => Date.parse(right.recordedAt) - Date.parse(left.recordedAt))
      .slice(0, 5);

  function openNotification(notification: OperationalNotification) {
    setSelected(notification);
    setDecision('confirmed');
    setReason('');
    setDecisionStored(false);
    setDraftStored(false);
    setMessage(undefined);
    setError(undefined);
  }

  async function login() {
    setSubmitting(true); setError(undefined); setMessage(undefined);
    try {
      const session = await startDemoSession('central-dispatcher');
      setCsrfToken(session.csrfToken);
      setMessage('Demo-сессия диспетчера ОДС активна 5 минут.');
    } catch (cause) {
      setError(safeError(cause, 'Не удалось открыть demo-сессию'));
    } finally {
      setSubmitting(false);
    }
  }

  async function saveDecision() {
    if (selected === null || csrfToken === undefined) return;
    setSubmitting(true); setError(undefined); setMessage(undefined);
    try {
      await recordPredictionDecision(selected.id, { decision, reason: reason.trim() }, csrfToken);
      setDecisionStored(true);
      setMessage(decision === 'rejected'
        ? 'Отклонение сохранено в журнале аудита. Черновик заявки для отклонённого прогноза не создаётся.'
        : 'Решение сохранено в журнале аудита. Теперь можно создать связанный черновик заявки.');
    } catch (cause) {
      setError(safeError(cause, 'Решение по прогнозу не сохранено'));
    } finally {
      setSubmitting(false);
    }
  }

  async function saveDraft() {
    if (selected === null || csrfToken === undefined || !decisionStored) return;
    setSubmitting(true); setError(undefined); setMessage(undefined);
    try {
      await createPredictionServiceDraft(selected.id, csrfToken);
      setDraftStored(true);
      setMessage('Черновик создан локально и связан с прогнозом. Во внешнюю help-desk он не отправлен.');
    } catch (cause) {
      setError(safeError(cause, 'Черновик заявки не создан'));
    } finally {
      setSubmitting(false);
    }
  }

  if (feed === null) return <Card aria-live="polite"><p role="status">Проверка прогнозов и уведомлений…</p></Card>;
  if (feed.status === 'unavailable') return <Card aria-live="polite"><h2 className="font-heading text-lg font-semibold">Уведомления недоступны</h2><p className="mt-2 text-sm text-[var(--color-text-muted)]">Нет проверенного prediction export или API не прошёл контроль контракта.</p></Card>;
  if (notifications.length === 0) return <Card aria-live="polite"><h2 className="font-heading text-lg font-semibold">Активных уведомлений нет</h2><p className="mt-2 text-sm text-[var(--color-text-muted)]">Модель доступна, но рабочий порог не выделил объектов для проверки.</p></Card>;

  return <>
    <ul className="grid gap-3" aria-label="Активные прогнозные уведомления">
      {notifications.map((notification) => <li key={notification.id}><button type="button" onClick={() => openNotification(notification)} className="surface grid w-full gap-4 p-5 text-left transition-colors hover:bg-[var(--color-panel-2)] md:grid-cols-[auto_1fr_auto] md:items-center">
        <span className="grid size-10 place-items-center rounded-full border border-[var(--color-border)] bg-[var(--color-panel-2)]"><BellRing size={18} aria-hidden="true" /></span>
        <span><span className="flex flex-wrap items-center gap-2"><strong className="font-heading text-base">Канал {notification.entityId}</strong><Badge tone={notification.priority}>{priorityLabels[notification.priority]}</Badge><Badge>{notification.evidenceTier === 'proxy' ? 'Прокси-модель' : 'Подтверждённая модель'}</Badge></span><span className="mt-1 block text-sm text-[var(--color-text-muted)]">{notification.recommendedAction}</span><span className="mt-2 block font-telemetry text-xs text-[var(--color-text-dim)]">{formatDate(notification.predictedAt)} · горизонт {notification.horizonHours} ч · {notification.modelVersion}</span></span>
        <span className="font-telemetry text-2xl font-semibold">{formatPercent(notification.probability)}</span>
      </button></li>)}
    </ul>
    <Modal isOpen={selected !== null} onClose={() => setSelected(null)} title={selected === null ? 'Прогноз' : `Прогноз для ${selected.entityId}`}>
      {selected && <div className="space-y-5">
        <section className="grid gap-4 sm:grid-cols-3" aria-label="Параметры прогноза"><Metric label="Вероятность" value={formatPercent(selected.probability)} /><Metric label="Горизонт" value={`${selected.horizonHours} ч`} /><Metric label="Версия" value={selected.modelVersion} /></section>
        <section><h3 className="font-heading text-base font-semibold">Факторы и ограничения</h3><ul className="mt-3 space-y-2 text-sm">{selected.factors.map((factor) => <li key={factor.factor} className="surface-subtle p-3"><strong>{factor.factor}</strong><p className="mt-1 text-[var(--color-text-muted)]">{factor.description}</p></li>)}</ul><ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-[var(--color-text-muted)]">{selected.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul></section>
        <TelemetryEvidence events={telemetry} status={localSituation.status} />
        <section className="border-l-2 border-l-[var(--color-data)] bg-[var(--color-panel-2)] p-4"><h3 className="font-heading text-base font-semibold">Рекомендованное действие</h3><p className="mt-2 text-sm">{selected.recommendedAction}</p></section>
        {csrfToken === undefined ? <section><p className="mb-3 text-sm text-[var(--color-text-muted)]">Для фиксации решения требуется короткоживущая локальная demo-сессия.</p><Button onClick={() => void login()} disabled={submitting}>Войти как диспетчер ОДС</Button></section> : <section className="space-y-4 border-t border-[var(--color-border)] pt-5" aria-labelledby="prediction-decision-title"><h3 id="prediction-decision-title" className="font-heading text-base font-semibold">Решение диспетчера</h3><Select label="Решение диспетчера" options={decisionOptions} value={decision} disabled={decisionStored} onChange={(event) => setDecision(event.target.value as PredictionDecision)} /><label className="grid gap-1 text-xs text-[var(--color-text-muted)]">Обоснование решения<textarea aria-label="Обоснование решения" className="control-surface min-h-24 rounded-[4px] px-3.5 py-2 text-sm text-[var(--color-text)]" value={reason} maxLength={1000} disabled={decisionStored} onChange={(event) => setReason(event.target.value)} /></label><div className="flex flex-wrap gap-2">{!decisionStored && <Button onClick={() => void saveDecision()} disabled={submitting || reason.trim().length < 3}>Сохранить решение</Button>}{decisionStored && decision !== 'rejected' && !draftStored && <Button onClick={() => void saveDraft()} disabled={submitting}>Создать черновик заявки</Button>}{draftStored && <Link href="/applications" className="inline-flex h-10 items-center rounded-[4px] bg-[var(--color-data)] px-4 text-sm font-semibold text-[#071014]">Открыть заявки</Link>}</div></section>}
        {error && <p role="alert" className="flex gap-2 border-l-2 border-l-[var(--color-danger)] p-3 text-sm"><AlertTriangle size={16} aria-hidden="true" />{error}</p>}
        {message && <p role="status" className="flex gap-2 border-l-2 border-l-[var(--color-success)] p-3 text-sm"><CheckCircle2 size={16} aria-hidden="true" />{message}</p>}
      </div>}
    </Modal>
  </>;
}
function Metric({ label, value }: { label: string; value: string }) {
  return <div className="surface-subtle p-3"><p className="text-xs text-[var(--color-text-muted)]">{label}</p><p className="mt-1 font-telemetry text-lg">{value}</p></div>;
}

function TelemetryEvidence({ events, status }: { events: LocalSituationEvent[]; status: 'loading' | 'ready' | 'unavailable' }) {
  return <section aria-labelledby="prediction-telemetry-title"><h3 id="prediction-telemetry-title" className="font-heading text-base font-semibold">Наблюдаемая телеметрия</h3>{status === 'loading' && <p className="mt-2 text-sm text-[var(--color-text-muted)]">Телеметрия загружается…</p>}{status === 'unavailable' && <p className="mt-2 text-sm text-[var(--color-text-muted)]">Локальная телеметрия недоступна — решение следует принимать только после ручной проверки.</p>}{status === 'ready' && events.length === 0 && <p className="mt-2 text-sm text-[var(--color-text-muted)]">В текущем снимке нет наблюдений по этому каналу.</p>}{events.length > 0 && <ul className="mt-3 divide-y divide-[var(--color-border)] border-y border-[var(--color-border)]">{events.map((event) => <li key={event.canonicalId} className="grid gap-1 py-3 text-sm sm:grid-cols-[1fr_auto]"><span><strong>{event.sensorValue}</strong><span className="ml-2 text-xs text-[var(--color-text-muted)]">{event.isAlarm === true ? 'тревога' : event.isAlarm === false ? 'штатное событие' : 'статус не определён'}</span></span><time className="font-telemetry text-xs text-[var(--color-text-dim)]" dateTime={event.recordedAt}>{formatDate(event.recordedAt)}</time></li>)}</ul>}</section>;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Europe/Moscow' }).format(new Date(value));
}

function formatPercent(value: number): string {
  return value.toLocaleString('ru-RU', { style: 'percent', maximumFractionDigits: 0 });
}

function safeError(cause: unknown, fallback: string): string {
  return cause instanceof Error ? cause.message : fallback;
}
