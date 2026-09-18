import { Chart } from './Chart';
import { buildTimeSeriesOption, type TimelinePoint } from './chartOptions';

export function TimeSeriesChart({ history, forecast, now, unit, height }: { history: TimelinePoint[]; forecast: TimelinePoint[]; now: string; unit: string; height?: number }) {
  return <Chart label="График истории и прогноза" description="Сплошная линия показывает историю, пунктирная — прогноз, полоса — доверительный интервал." option={buildTimeSeriesOption({ history, forecast, now, unit })} height={height} columns={['Время', 'Ряд', 'Значение', 'Доверительный интервал']} rows={[...history.map((point) => [new Date(point.at).toLocaleString('ru-RU'), 'История', `${point.value} ${unit}`, '—']), ...forecast.map((point) => [new Date(point.at).toLocaleString('ru-RU'), 'Прогноз', `${point.value} ${unit}`, point.lower === undefined || point.upper === undefined ? '—' : `${point.lower}–${point.upper} ${unit}`])]} />;
}
