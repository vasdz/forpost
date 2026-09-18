'use client';

import { CapabilityUnavailablePage } from '@/components/features/CapabilityUnavailablePage';

export default function UnauthorizedAccessPage() {
  return <CapabilityUnavailablePage eyebrow="Прогнозирование" title="Несанкционированный доступ недоступен" description="Для этого направления требуются журналы СКУД, допуски и правила расследований." unavailableDescription="Журналы СКУД, сведения о допусках и модель выявления аномалий отсутствуют; расследования и рекомендации не формируются." />;
}
