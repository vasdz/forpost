'use client';

import { CapabilityUnavailablePage } from '@/components/features/CapabilityUnavailablePage';

export default function JournalsPage() {
  return <CapabilityUnavailablePage eyebrow="Оперативный контур" title="Журнал решений недоступен" description="Журнал требует подтверждённого write API, идентификации пользователя и неизменяемого хранилища." unavailableDescription="Write API, идентификация пользователя и журнал аудита не подключены; диспетчерские решения не создаются и не имитируются." />;
}
