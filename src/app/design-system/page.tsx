'use client';

import { CapabilityUnavailablePage } from '@/components/features/CapabilityUnavailablePage';

export default function DesignSystemPage() {
  return <CapabilityUnavailablePage eyebrow="Системный раздел" title="Настройки недоступны" description="Настройки операционного контура появятся после подключения защищённого профиля пользователя." unavailableDescription="Профиль пользователя, права доступа и API настроек не подключены; параметры и статусы не имитируются." />;
}
