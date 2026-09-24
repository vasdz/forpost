import { NotificationCenter } from '@/components/features/NotificationCenter';
import { PageHeader } from '@/components/features/PageHeader';

export default function NotificationsPage() {
  return <>
    <PageHeader eyebrow="Оперативный контур" title="Центр уведомлений" description="Сквозной путь диспетчера: проверенный прогноз, обоснованное решение и связанный локальный черновик заявки." />
    <NotificationCenter />
  </>;
}
