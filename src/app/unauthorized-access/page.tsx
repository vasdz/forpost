'use client';

import { PredictionCapabilityPage } from '@/components/features/PredictionCapability';

export default function UnauthorizedAccessPage() {
  return <PredictionCapabilityPage type="unauthorized_access" title="Несанкционированный доступ" description="Анализ аномальных паттернов доступа и связанных допусков." unavailableDescription="Валидированная модель не найдена; журналы СКУД и допуски отсутствуют, результат не формируется." />;
}
