import { Chart } from './Chart';
import { buildSparklineOption } from './chartOptions';

export function Sparkline({ points, color, label }: { points: number[]; color?: string; label: string }) {
  return <Chart label={label} description="Компактная динамика показателя." option={buildSparklineOption(points, color)} height={36} columns={['Отсчёт', 'Значение']} rows={points.map((point, index) => [index + 1, point])} />;
}
