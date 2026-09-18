import { Chart } from './Chart';
import { buildHeatMapOption } from './chartOptions';

function getAxisLabel(labels: readonly string[], index: number): string {
  if (!Number.isInteger(index) || index < 0 || index >= labels.length) {
    return '—';
  }
  return labels.at(index) ?? '—';
}

export function HeatMap({ data, days, hours, label = 'Тепловая матрица' }: { data: Array<[number, number, number]>; days: string[]; hours: string[]; label?: string }) {
  return <Chart label={label} description="Интенсивность событий по двум измерениям; значение указано в таблице." option={buildHeatMapOption(data, days, hours)} columns={['Период / тип', 'Час', 'Количество']} rows={data.map(([hour, day, value]) => [getAxisLabel(days, day), getAxisLabel(hours, hour), value])} />;
}
