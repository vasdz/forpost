import { Chart } from './Chart';
import { buildDonutOption } from './chartOptions';

export function DonutChart({ items, label }: { items: Array<{ name: string; value: number; color: string }>; label: string }) {
  const total = items.reduce((sum, item) => sum + item.value, 0);
  return <Chart label={label} description="Распределение статусов в кольцевой диаграмме." option={buildDonutOption(items)} columns={['Статус', 'Количество', 'Доля']} rows={items.map((item) => [item.name, item.value, `${total ? Math.round(item.value / total * 100) : 0}%`])} />;
}
