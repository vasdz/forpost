'use client';

import { PredictionCapabilityPage } from '@/components/features/PredictionCapability';

export default function InfrastructureWearPage() {
  return <PredictionCapabilityPage type="infrastructure_wear" title="Износ инфраструктуры" description="Приоритизация обслуживания с отделением подтверждённой модели от сценарной оценки." unavailableDescription="Модель или сценарный экспорт износа не найден; оценка не формируется." />;
}
