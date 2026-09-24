'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { ModelQualityComparisonChart } from '@/components/charts/ModelQualityComparisonChart';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Select } from '@/components/ui/Select';
import { fetchModelEvaluation, type ConfidenceInterval, type ModelEvaluation, type ModelEvaluationFeed, type ModelMetrics, type OperatingProfile, type OperatingProfiles, type QualityThresholds, type SplitSizes, type ValidationConfidenceIntervals } from '@/data/modelEvaluationClient';
import { startDemoSession } from '@/data/operationsClient';

const reasonLabels = {
  configuration_invalid: 'Конфигурация недействительна',
  source_unavailable: 'Источник данных недоступен',
  dataset_unavailable: 'Набор данных недоступен',
  training_unavailable: 'Обучение недоступно',
  validation_rejected: 'Валидация отклонена',
  test_rejected: 'Тестирование отклонено',
  inference_unavailable: 'Инференс недоступен',
  release_unavailable: 'Релиз недоступен',
} as const;

const metricRows: ReadonlyArray<{ key: keyof ModelMetrics; label: string; value: (metrics: ModelMetrics | null) => number | null }> = [
  { key: 'precision', label: 'Точность', value: (metrics) => metrics?.precision ?? null }, { key: 'recall', label: 'Полнота', value: (metrics) => metrics?.recall ?? null },
  { key: 'f1', label: 'F1-мера', value: (metrics) => metrics?.f1 ?? null }, { key: 'prAuc', label: 'PR-AUC', value: (metrics) => metrics?.prAuc ?? null },
  { key: 'rocAuc', label: 'ROC-AUC', value: (metrics) => metrics?.rocAuc ?? null }, { key: 'brierScore', label: 'Ошибка Брайера', value: (metrics) => metrics?.brierScore ?? null },
  { key: 'expectedCalibrationError', label: 'Ошибка калибровки', value: (metrics) => metrics?.expectedCalibrationError ?? null }, { key: 'alertRate', label: 'Доля алертов', value: (metrics) => metrics?.alertRate ?? null },
];

export function ModelQualityPanel() {
  const [feed, setFeed] = useState<ModelEvaluationFeed | null>(null);
  const [signingIn, setSigningIn] = useState(false);
  const [signInFailed, setSignInFailed] = useState(false);
  const demoDescriptionId = useId();
  const mounted = useRef(false);

  useEffect(() => {
    mounted.current = true;
    let active = true;
    void fetchModelEvaluation().then((result) => { if (active) setFeed(result); });
    return () => { active = false; mounted.current = false; };
  }, []);

  async function signIn() {
    if (signingIn) return;
    setSigningIn(true);
    setSignInFailed(false);
    try {
      await startDemoSession('central-dispatcher');
      if (!mounted.current) return;
      const result = await fetchModelEvaluation();
      if (mounted.current) setFeed(result);
    } catch {
      if (mounted.current) setSignInFailed(true);
    } finally {
      if (mounted.current) setSigningIn(false);
    }
  }

  if (feed === null) return <Card aria-live="polite"><p role="status">Загрузка отчёта об оценке модели…</p></Card>;
  if (feed.status === 'unauthenticated') return <Card>
    <h2 className="font-heading text-lg font-semibold">Для просмотра качества модели требуется вход</h2>
    <p id={demoDescriptionId} className="mt-2 text-sm leading-6 text-[var(--color-text-muted)]">Локальная демо-сессия диспетчера ОДС не является корпоративной авторизацией. Доступ действует только на настроенном демонстрационном стенде.</p>
    <Button className="mt-4" variant="secondary" aria-describedby={demoDescriptionId} disabled={signingIn} onClick={() => void signIn()}>Войти в демо-режим ОДС</Button>
    {signingIn && <p role="status" className="mt-2 text-sm">Выполняется вход и загрузка отчёта…</p>}
    {signInFailed && <p role="alert" className="mt-2 text-sm">Не удалось войти в демо-режим. Проверьте настройку локального стенда и повторите попытку.</p>}
  </Card>;
  if (feed.status === 'unavailable') return <Card aria-live="polite"><h2 className="font-heading text-lg font-semibold">Отчёт об оценке недоступен</h2><p className="mt-2 text-sm leading-6 text-[var(--color-text-muted)]">Отчёт не загружен или не прошёл проверку контракта. Прогнозы по этому сообщению не формируются.</p></Card>;

  return <EvaluationDetails evaluation={feed.evaluation} />;
}

function EvaluationDetails({ evaluation }: { evaluation: ModelEvaluation }) {
  const [profileName, setProfileName] = useState<keyof OperatingProfiles>('balanced');
  const rejected = evaluation.status === 'rejected';
  return <section aria-labelledby="model-quality-title" className="mt-6 space-y-4">
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--color-text-muted)]">Доказательства ML-оценки</p>
          <h2 id="model-quality-title" className="mt-2 font-heading text-xl font-semibold">Качество ML-модели</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--color-text-muted)]">Отчёт об оценке не является прогнозом и сам по себе не подтверждает доступность прогноза.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge tone={rejected ? 'high' : 'low'}>{rejected ? 'Релиз заблокирован' : 'Отчёт опубликован'}</Badge>
          <Badge>{evaluation.evidenceTier === 'proxy' ? 'Прокси-метка' : evaluation.evidenceTier}</Badge>
        </div>
      </div>
      <dl className="mt-5 grid gap-4 border-t border-[var(--color-border)] pt-5 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <Detail label="Версия" value={evaluation.version} telemetry />
        <Detail label="Стратегия метки" value="Прокси тишины на горизонте" />
        <Detail label="Горизонт оценки" value={evaluation.horizonHours === null ? 'Не определён' : `${evaluation.horizonHours} ч`} telemetry />
        <Detail label="Время отчёта" value={formatDate(evaluation.createdAt)} />
        <Detail label="Базовый PR-AUC валидации" value={formatNumber(evaluation.baselineValidationPrAuc)} telemetry />
        <Detail label="Схема признаков" value={evaluation.featureSchemaVersion === null ? 'Не определена' : `v${evaluation.featureSchemaVersion}`} telemetry />
        <Detail label="Rolling-folds" value={String(evaluation.rollingFolds.length)} telemetry />
      </dl>
    </Card>
    {rejected && <Card aria-live="polite" className="border-[var(--color-status-high)]"><h3 className="font-heading text-lg font-semibold">Релиз модели заблокирован</h3><p className="mt-2 text-sm leading-6 text-[var(--color-text-muted)]">Отчёт фиксирует доказательство блокировки релиза и не подтверждает доступность прогноза.</p><p className="mt-3 text-sm"><span className="text-[var(--color-text-muted)]">Причина: </span><strong>{evaluation.reasonCode === null ? 'Не указана' : reasonLabels[evaluation.reasonCode]}</strong></p></Card>}
    <div className="grid gap-4 lg:grid-cols-2">
      <ThresholdCard thresholds={evaluation.qualityThresholds} />
      <SplitSizesCard splitSizes={evaluation.splitSizes} />
    </div>
    {evaluation.validationMetrics !== null && evaluation.testMetrics !== null && evaluation.qualityThresholds !== null && <Card>
      <div className="mb-4"><h3 className="font-heading text-lg font-semibold">Проверка на отложенных данных</h3><p className="mt-1 text-sm leading-6 text-[var(--color-text-muted)]">Диаграмма отражает сравнение прогнозных классов с фактическими метками отдельно на временной валидации и финальном тесте.</p></div>
      <ModelQualityComparisonChart validation={evaluation.validationMetrics} test={evaluation.testMetrics} thresholds={evaluation.qualityThresholds} />
    </Card>}
    {evaluation.operatingProfiles !== null && <OperatingProfileCard profiles={evaluation.operatingProfiles} selected={profileName} onSelect={setProfileName} />}
    <Card>
      <div className="flex flex-wrap items-end justify-between gap-3"><div><h3 className="font-heading text-lg font-semibold">Метрики качества</h3><p className="mt-1 text-sm text-[var(--color-text-muted)]">Валидация и тест отображаются раздельно; тест отсутствует для отклонённого отчёта.</p></div><p className="font-telemetry text-sm text-[var(--color-text-muted)]">Порог: {formatNumber(evaluation.threshold)}</p></div>
      <div className="data-table-frame mt-4 overflow-auto"><table aria-label="Метрики качества модели" className="w-full min-w-[700px] border-collapse text-left text-sm"><caption className="sr-only">Метрики качества модели для валидационной и тестовой выборок</caption><thead className="bg-[var(--color-panel-2)]"><tr><th scope="col" className="border-b border-[var(--color-border)] px-4 py-3 text-xs font-semibold">Метрика</th><th scope="col" className="border-b border-[var(--color-border)] px-4 py-3 text-xs font-semibold">Валидация</th><th scope="col" className="border-b border-[var(--color-border)] px-4 py-3 text-xs font-semibold">95% интервал</th><th scope="col" className="border-b border-[var(--color-border)] px-4 py-3 text-xs font-semibold">Тест</th></tr></thead><tbody>{metricRows.map(({ key, label, value }) => <tr key={key} className="border-b border-[var(--color-border)] last:border-0"><th scope="row" className="px-4 py-3 font-medium">{label}</th><td className="px-4 py-3 font-telemetry">{formatNumber(value(evaluation.validationMetrics))}</td><td className="px-4 py-3 font-telemetry">{formatInterval(getConfidenceInterval(evaluation.validationConfidenceIntervals, key))}</td><td className="px-4 py-3 font-telemetry">{formatNumber(value(evaluation.testMetrics))}</td></tr>)}</tbody></table></div>
      <p className="mt-4 text-sm text-[var(--color-text-muted)]">Победитель валидации: <span className="font-telemetry text-[var(--color-text)]">{evaluation.championName ?? 'Не определён'}</span></p>
    </Card>
  </section>;
}

const profileOptions = [
  { value: 'highPrecision', label: 'Максимум точности' },
  { value: 'balanced', label: 'Сбалансированный' },
  { value: 'highRecall', label: 'Максимум полноты' },
];

function OperatingProfileCard({ profiles, selected, onSelect }: {
  profiles: OperatingProfiles;
  selected: keyof OperatingProfiles;
  onSelect: (profile: keyof OperatingProfiles) => void;
}) {
  const profile: OperatingProfile = getOperatingProfile(profiles, selected);
  return <Card>
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div><h3 className="font-heading text-lg font-semibold">Операционный сценарий</h3><p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--color-text-muted)]">Настраиваемое сравнение профилей, рассчитанных только на validation. Выбор не изменяет опубликованный рабочий порог и не запускает модель.</p></div>
      <Select label="Операционный профиль" options={profileOptions} value={selected} onChange={(event) => onSelect(event.target.value as keyof OperatingProfiles)} />
    </div>
    <dl className="mt-5 grid gap-4 border-t border-[var(--color-border)] pt-5 sm:grid-cols-2 lg:grid-cols-4" aria-live="polite">
      <Detail label="Порог решения" value={formatNumber(profile.threshold)} telemetry />
      <Detail label="Точность" value={formatPercent(profile.precision)} telemetry />
      <Detail label="Полнота" value={formatPercent(profile.recall)} telemetry />
      <Detail label="Ожидаемая доля алертов" value={formatPercent(profile.alertRate)} telemetry />
    </dl>
  </Card>;
}

function getOperatingProfile(profiles: OperatingProfiles, selected: keyof OperatingProfiles): OperatingProfile {
  if (selected === 'highPrecision') return profiles.highPrecision;
  if (selected === 'highRecall') return profiles.highRecall;
  return profiles.balanced;
}

function ThresholdCard({ thresholds }: { thresholds: QualityThresholds | null }) {
  const values: ReadonlyArray<[string, number | null]> = thresholds === null ? [] : [
    ['Минимальная точность', thresholds.minimumPrecision], ['Минимальная полнота', thresholds.minimumRecall],
    ['Максимальная доля алертов', thresholds.maximumAlertRate], ['Максимальная ошибка калибровки', thresholds.maximumExpectedCalibrationError],
    ['Максимальная ошибка Брайера', thresholds.maximumBrierScore], ['Минимальный прирост PR-AUC', thresholds.minimumBaselinePrAucDelta],
  ];
  return <Card><h3 className="font-heading text-lg font-semibold">Пороги качества</h3>{thresholds === null ? <p className="mt-3 text-sm text-[var(--color-text-muted)]">Пороги не были получены до остановки оценки.</p> : <dl className="mt-4 grid grid-cols-2 gap-4">{values.map(([label, value]) => <Detail key={label} label={label} value={formatNumber(value)} telemetry />)}</dl>}</Card>;
}

function SplitSizesCard({ splitSizes }: { splitSizes: SplitSizes | null }) {
  const values: ReadonlyArray<[string, number | null]> = splitSizes === null ? [] : [['Обучение', splitSizes.fit], ['Калибровка', splitSizes.calibration], ['Валидация', splitSizes.validation], ['Тест', splitSizes.test]];
  return <Card><h3 className="font-heading text-lg font-semibold">Размеры выборок</h3>{splitSizes === null ? <p className="mt-3 text-sm text-[var(--color-text-muted)]">Размеры выборок не были получены до остановки оценки.</p> : <dl className="mt-4 grid grid-cols-2 gap-4">{values.map(([label, value]) => <Detail key={label} label={label} value={String(value)} telemetry />)}</dl>}</Card>;
}

function Detail({ label, value, telemetry = false }: { label: string; value: string; telemetry?: boolean }) {
  return <div><dt className="text-xs text-[var(--color-text-muted)]">{label}</dt><dd className={telemetry ? 'mt-1 font-telemetry text-base' : 'mt-1 text-sm'}>{value}</dd></div>;
}

function formatNumber(value: number | null): string {
  return value === null ? '—' : value.toLocaleString('ru-RU', { minimumFractionDigits: 3, maximumFractionDigits: 3 });
}

function formatPercent(value: number): string {
  return value.toLocaleString('ru-RU', { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

function formatInterval(value: ConfidenceInterval | null): string {
  return value === null ? '—' : `${formatNumber(value.lower)}–${formatNumber(value.upper)}`;
}

function getConfidenceInterval(
  intervals: ValidationConfidenceIntervals | null,
  metric: keyof ModelMetrics,
): ConfidenceInterval | null {
  if (intervals === null) return null;
  switch (metric) {
    case 'precision': return intervals.precision;
    case 'recall': return intervals.recall;
    case 'f1': return intervals.f1;
    case 'prAuc': return intervals.prAuc;
    case 'rocAuc': return intervals.rocAuc;
    case 'brierScore': return intervals.brierScore;
    case 'expectedCalibrationError': return intervals.expectedCalibrationError;
    case 'alertRate': return intervals.alertRate;
  }
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Europe/Moscow' }).format(new Date(value));
}
