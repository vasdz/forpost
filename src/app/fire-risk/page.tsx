'use client';

import { CapabilityUnavailablePage } from '@/components/features/CapabilityUnavailablePage';

export default function FireRiskPage() {
  return <CapabilityUnavailablePage eyebrow="Прогнозирование" title="Пожарный риск недоступен" description="Для расчёта нужны подтверждённые данные температуры, дыма и допусков на работы." unavailableDescription="Источник температурных и дымовых измерений, АРМ-Контроль и модель пожарного риска не подключены; оценка риска не формируется." />;
}
