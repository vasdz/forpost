'use client';

import { CapabilityUnavailablePage } from '@/components/features/CapabilityUnavailablePage';

export default function InfrastructureWearPage() {
  return <CapabilityUnavailablePage eyebrow="Прогнозирование" title="Износ инфраструктуры недоступен" description="Для оценки износа необходимы реестр оборудования, даты ввода и история ремонтов." unavailableDescription="Реестр оборудования, история ремонтов и модель износа не подключены; рейтинг, план работ и паспорт объекта не формируются." />;
}
