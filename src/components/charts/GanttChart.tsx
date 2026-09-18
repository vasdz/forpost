import { Chart } from './Chart';
import { buildGanttOption } from './chartOptions';

export function GanttChart({ items }: { items: Array<{ name: string; start: string; end: string; status: 'planned' | 'completed'; performer?: string }> }) {
  return <Chart label="График плановых ремонтов" description="Периоды плановых и выполненных работ." option={buildGanttOption(items)} height={300} columns={['Объект', 'Начало', 'Окончание', 'Статус', 'Исполнитель']} rows={items.map((item) => [item.name, new Date(item.start).toLocaleString('ru-RU'), new Date(item.end).toLocaleString('ru-RU'), item.status === 'planned' ? 'Запланирован' : 'Выполнен', item.performer ?? 'Не назначен'])} />;
}
