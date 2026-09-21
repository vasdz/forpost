'use client';

import { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { fetchPredictionFeed, type EvidenceTier, type Prediction, type PredictionFeed, type PredictionType } from '@/data/predictionsClient';
import { PageHeader } from './PageHeader';

const evidenceLabels: Record<EvidenceTier, string> = {
  validated: 'Подтверждённая модель',
  proxy: 'Прокси-модель',
  anomaly: 'Аномалия',
  scenario: 'Сценарий',
};
const provenanceLabels: Record<Prediction['provenance'], string> = {
  observed: 'Наблюдение источника',
  derived: 'Расчёт из источника',
  simulated: 'Симуляция',
};
const priorityLabels: Record<Prediction['priority'], string> = {
  low: 'Низкий приоритет', medium: 'Средний приоритет', high: 'Высокий приоритет', critical: 'Критический приоритет',
};
const statusLabels: Record<Prediction['status'], string> = {
  new: 'Новый', acknowledged: 'Принят', confirmed: 'Подтверждён', rejected: 'Отклонён', escalated: 'Эскалирован', resolved: 'Закрыт',
};

export function PredictionCapabilityPage({
  type, title, description, unavailableDescription,
}: {
  type: PredictionType;
  title: string;
  description: string;
  unavailableDescription: string;
}) {
  return <>
    <PageHeader eyebrow="Предиктивная аналитика" title={title} description={description} />
    <PredictionPanel type={type} unavailableDescription={unavailableDescription} />
  </>;
}

export function PredictionPanel({ type, unavailableDescription }: {
  type: PredictionType;
  unavailableDescription: string;
}) {
  const [feed, setFeed] = useState<PredictionFeed | null>(null);
  useEffect(() => {
    let active = true;
    void fetchPredictionFeed().then((result) => { if (active) setFeed(result); });
    return () => { active = false; };
  }, [type]);

  if (feed === null) return <Card aria-live="polite">Проверка доступности модели…</Card>;
  if (feed.status === 'unavailable' || !feed.availableTypes.includes(type)) return <Card aria-live="polite"><h2 className="font-heading text-lg font-semibold">Прогнозы недоступны</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-muted)]">{unavailableDescription}</p></Card>;
  const items = feed.predictions.filter((prediction) => prediction.predictionType === type
    && (prediction.evidenceTier === 'validated' || prediction.evidenceTier === 'proxy'));
  if (items.length === 0) return <Card aria-live="polite"><h2 className="font-heading text-lg font-semibold">Активных прогнозов нет</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-muted)]">Модель доступна, но текущий рабочий порог не выделил объектов для проверки.</p></Card>;

  return <div className="space-y-4">{items.map((prediction) => <PredictionCard key={prediction.id} prediction={prediction} />)}</div>;
}

function PredictionCard({ prediction }: { prediction: Prediction }) {
  const displayValue = prediction.probability !== null
    ? `${Math.round(prediction.probability * 100)}%`
    : prediction.anomalyScore !== null
      ? `Индекс аномалии ${prediction.anomalyScore.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} из 1`
      : 'Без числовой оценки';
  const predictedAt = new Intl.DateTimeFormat('ru-RU', {
    dateStyle: 'short', timeStyle: 'short', timeZone: 'Europe/Moscow',
  }).format(new Date(prediction.predictedAt));
  return <Card aria-label={`Прогноз для ${prediction.entityId}`}>
    <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[var(--color-border)] pb-5">
      <div className="min-w-0">
        <div className="flex flex-wrap gap-2">
          <Badge>{evidenceLabels[prediction.evidenceTier]}</Badge>
          <Badge>{provenanceLabels[prediction.provenance]}</Badge>
          <Badge tone={prediction.qualityStatus === 'passed' ? 'low' : 'medium'}>{prediction.qualityStatus === 'passed' ? 'Контроль качества пройден' : 'Качество ограничено'}</Badge>
          <Badge tone={prediction.priority}>{priorityLabels[prediction.priority]}</Badge>
          <Badge>{statusLabels[prediction.status]}</Badge>
        </div>
        <h2 className="mt-3 break-all font-heading text-xl font-semibold">{prediction.entityId}</h2>
        <p className="mt-1 font-telemetry text-xs text-[var(--color-text-muted)]">{prediction.modelVersion} · рассчитано {predictedAt} · горизонт {prediction.horizonHours} ч</p>
      </div>
      <div className="text-right">
        <p className="font-telemetry text-3xl font-semibold">{displayValue}</p>
        <p className="mt-1 text-xs text-[var(--color-text-muted)]">{prediction.confidence ? `Интервал ${Math.round(prediction.confidence.lower * 100)}–${Math.round(prediction.confidence.upper * 100)}%` : 'Индивидуальный интервал не оценён'}</p>
      </div>
    </div>
    {prediction.modelMetrics && <dl className="grid grid-cols-2 gap-px border-b border-[var(--color-border)] bg-[var(--color-border)] py-px md:grid-cols-5">
      {[
        ['Точность', prediction.modelMetrics.precision],
        ['Полнота', prediction.modelMetrics.recall],
        ['F1', prediction.modelMetrics.f1],
        ['PR-AUC', prediction.modelMetrics.prAuc],
        ['Ошибка Брайера', prediction.modelMetrics.brierScore],
      ].map(([label, value]) => <div key={String(label)} className="bg-[var(--color-panel)] px-3 py-4"><dt className="text-[10px] uppercase tracking-[0.12em] text-[var(--color-text-muted)]">{label}</dt><dd className="mt-1 font-telemetry text-lg">{Number(value).toLocaleString('ru-RU', { maximumFractionDigits: 2 })}</dd></div>)}
    </dl>}
    <div className="grid gap-6 pt-5 lg:grid-cols-2">
      <section><h3 className="text-xs font-semibold uppercase tracking-[0.12em]">Глобальные факторы модели</h3><ul className="mt-3 space-y-3">{prediction.factors.map((factor) => <li key={factor.factor}><div className="flex justify-between gap-4 text-sm"><span>{factor.factor}</span><span className="font-telemetry">{Math.round(Math.abs(factor.weight) * 100)}%</span></div><div className="mt-1 h-1 bg-[var(--color-panel-2)]"><div className="h-full bg-[var(--color-data)]" style={{ width: `${Math.min(100, Math.abs(factor.weight) * 100)}%` }} /></div><p className="mt-1 text-xs text-[var(--color-text-muted)]">{factor.description}</p></li>)}</ul></section>
      <section><h3 className="text-xs font-semibold uppercase tracking-[0.12em]">Действие и ограничения</h3><p className="mt-3 text-sm font-medium">{prediction.qualityStatus === 'passed' ? prediction.recommendedAction : 'Рекомендация не сформирована: контроль качества ограничен.'}</p><ul className="mt-3 list-disc space-y-1 pl-5 text-xs leading-5 text-[var(--color-text-muted)]">{prediction.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul></section>
    </div>
  </Card>;
}
