'use client';

import { CapabilityUnavailablePage } from '@/components/features/CapabilityUnavailablePage';

export default function ApplicationsPage() {
  return <CapabilityUnavailablePage eyebrow="Оперативные действия" title="Заявки недоступны" description="Работа с заявками будет доступна после подключения защищённого write API и реестра исполнителей." unavailableDescription="Источник заявок и write API отсутствуют; новые заявки, статусы и назначения не формируются." />;
}
