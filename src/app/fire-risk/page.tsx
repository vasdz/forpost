'use client';

import { PredictionCapabilityPage } from '@/components/features/PredictionCapability';

export default function FireRiskPage() {
  return <PredictionCapabilityPage type="fire_risk" title="Пожарный риск" description="Совместный анализ температурных, дымовых и событийных сигналов с явным уровнем доказательности." unavailableDescription="Модель или anomaly-экспорт пожарного риска не найден; вероятность не формируется." />;
}
