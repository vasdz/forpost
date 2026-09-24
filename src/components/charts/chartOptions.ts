import type { EChartsOption } from 'echarts';

const axisText = 'var(--color-text-muted)';
const splitLine = 'var(--color-border)';
const dataColor = 'var(--color-data)';
const cyanColor = 'var(--color-cyan)';
const dangerColor = 'var(--color-danger)';
const successColor = 'var(--color-success)';
const tooltip = { backgroundColor: 'var(--color-panel)', borderColor: splitLine, textStyle: { color: 'var(--color-text)' } };

export type TimelinePoint = { at: string; value: number; lower?: number; upper?: number };

export function buildModelQualityComparisonOption({
  validation,
  test,
  minimums,
}: {
  validation: { precision: number; recall: number };
  test: { precision: number; recall: number };
  minimums: { precision: number; recall: number };
}): EChartsOption {
  return {
    grid: { top: 42, right: 16, bottom: 38, left: 50 },
    tooltip: { ...tooltip, trigger: 'axis', valueFormatter: (value) => `${(Number(value) * 100).toFixed(1)}%` },
    legend: { top: 0, textStyle: { color: axisText } },
    xAxis: {
      type: 'category', data: ['Точность', 'Полнота'],
      axisLabel: { color: axisText }, axisLine: { lineStyle: { color: splitLine } },
    },
    yAxis: {
      type: 'value', min: 0, max: 1, interval: 0.25,
      axisLabel: { color: axisText, formatter: (value: number) => `${Math.round(value * 100)}%` },
      splitLine: { lineStyle: { color: splitLine } },
    },
    series: [
      { name: 'Валидация', type: 'bar', data: [validation.precision, validation.recall], itemStyle: { color: dataColor } },
      { name: 'Финальный тест', type: 'bar', data: [test.precision, test.recall], itemStyle: { color: successColor } },
      { name: 'Минимум', type: 'line', data: [minimums.precision, minimums.recall], symbol: 'diamond', symbolSize: 10, lineStyle: { color: dangerColor, type: 'dashed' }, itemStyle: { color: dangerColor } },
    ],
  };
}

export function buildObservedActivityOption(
  buckets: Array<{ at: string; events: number; alarms: number }>,
): EChartsOption {
  return {
    grid: { top: 36, right: 16, bottom: 42, left: 44 },
    tooltip: { ...tooltip, trigger: 'axis' },
    legend: { top: 0, textStyle: { color: axisText } },
    xAxis: {
      type: 'category',
      data: buckets.map((bucket) => bucket.at),
      axisLabel: {
        color: axisText,
        fontFamily: 'var(--font-jetbrains-mono)',
        formatter: (value: string) => value.slice(5, 16).replace('T', ' '),
      },
      axisLine: { lineStyle: { color: splitLine } },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: axisText, fontFamily: 'var(--font-jetbrains-mono)' },
      splitLine: { lineStyle: { color: splitLine } },
    },
    series: [
      { name: 'Все события', type: 'bar', data: buckets.map((bucket) => bucket.events), itemStyle: { color: dataColor } },
      { name: 'Со сработкой', type: 'bar', data: buckets.map((bucket) => bucket.alarms), itemStyle: { color: dangerColor } },
    ],
  };
}

export function buildTimeSeriesOption({ history, forecast, now, unit }: { history: TimelinePoint[]; forecast: TimelinePoint[]; now: string; unit: string }): EChartsOption {
  const allDates = [...new Set([...history, ...forecast].map((point) => point.at).concat(now))].sort();
  const historicalValues = new Map(history.map((point) => [point.at, point]));
  const forecastValues = new Map(forecast.map((point) => [point.at, point]));
  return {
    animationDuration: 200,
    grid: { top: 36, right: 20, bottom: 30, left: 50 },
    tooltip: { ...tooltip, trigger: 'axis', valueFormatter: (value) => `${value} ${unit}` },
    legend: { top: 0, textStyle: { color: axisText, fontFamily: 'Inter, Golos Text, sans-serif' } },
    xAxis: { type: 'category', data: allDates, axisLabel: { color: axisText, fontFamily: 'var(--font-jetbrains-mono)', formatter: (value: string) => new Date(value).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' }) }, axisLine: { lineStyle: { color: splitLine } } },
    yAxis: { type: 'value', axisLabel: { color: axisText, fontFamily: 'var(--font-jetbrains-mono)', formatter: `{value} ${unit}` }, splitLine: { lineStyle: { color: splitLine } } },
    series: [
      { name: 'История', type: 'line', smooth: false, showSymbol: false, data: allDates.map((date) => historicalValues.get(date)?.value ?? null), lineStyle: { color: dataColor, width: 2 }, itemStyle: { color: dataColor }, markLine: { symbol: 'none', lineStyle: { color: axisText, type: 'solid' }, label: { formatter: 'Сейчас' }, data: [{ xAxis: now }] } },
      { name: 'Нижняя граница', type: 'line', stack: 'confidence', symbol: 'none', data: allDates.map((date) => { const point = forecastValues.get(date); return point ? point.lower ?? point.value : null; }), lineStyle: { opacity: 0 }, areaStyle: { opacity: 0 }, emphasis: { disabled: true } },
      { name: 'Доверительный интервал', type: 'line', stack: 'confidence', symbol: 'none', data: allDates.map((date) => { const point = forecastValues.get(date); return point ? (point.upper ?? point.value) - (point.lower ?? point.value) : null; }), lineStyle: { opacity: 0 }, areaStyle: { color: 'var(--color-danger)', opacity: 0.12 }, emphasis: { disabled: true } },
      { name: 'Прогноз', type: 'line', smooth: false, showSymbol: false, data: allDates.map((date) => forecastValues.get(date)?.value ?? null), lineStyle: { color: dangerColor, type: 'dashed', width: 2 }, itemStyle: { color: dangerColor } },
    ],
  };
}

export function buildHeatMapOption(data: Array<[number, number, number]>, days: string[], hours: string[]): EChartsOption {
  return { tooltip: { ...tooltip, position: 'top' }, grid: { top: 10, bottom: 38, left: 70, right: 20 }, xAxis: { type: 'category', data: hours, axisLabel: { color: axisText, fontFamily: 'var(--font-jetbrains-mono)' }, axisLine: { lineStyle: { color: splitLine } } }, yAxis: { type: 'category', data: days, axisLabel: { color: axisText }, axisLine: { lineStyle: { color: splitLine } } }, visualMap: { min: 0, max: Math.max(1, ...data.map((item) => item[2])), calculable: false, orient: 'horizontal', left: 'center', bottom: 0, inRange: { color: ['var(--color-panel-2)', cyanColor, 'var(--color-warning)', dangerColor] }, textStyle: { color: axisText } }, series: [{ type: 'heatmap', data, label: { show: false }, emphasis: { itemStyle: { borderColor: 'var(--color-text)', borderWidth: 1 } } }] };
}

export function buildSparklineOption(points: number[], color = cyanColor): EChartsOption {
  return { animationDuration: 150, grid: { top: 2, bottom: 2, left: 1, right: 1 }, xAxis: { type: 'category', show: false, data: points.map((_, index) => index) }, yAxis: { type: 'value', show: false, scale: true }, series: [{ type: 'line', data: points, showSymbol: false, smooth: true, lineStyle: { color, width: 1.5 } }] };
}

export function buildDonutOption(items: Array<{ name: string; value: number; color: string }>): EChartsOption {
  return { tooltip: { ...tooltip, trigger: 'item', formatter: '{b}: {c} ({d}%)' }, legend: { bottom: 0, textStyle: { color: axisText } }, series: [{ type: 'pie', radius: ['58%', '76%'], avoidLabelOverlap: true, label: { show: false }, itemStyle: { borderColor: 'var(--color-bg)', borderWidth: 2 }, data: items.map((item) => ({ ...item, itemStyle: { color: item.color } })) }] };
}

export function buildGanttOption(items: Array<{ name: string; start: string; end: string; status: 'planned' | 'completed' }>): EChartsOption {
  const starts = items.map((item) => new Date(item.start).getTime());
  const durations = items.map((item) => (new Date(item.end).getTime() - new Date(item.start).getTime()) / 86_400_000);
  return { tooltip, grid: { top: 20, right: 30, bottom: 30, left: 130 }, xAxis: { type: 'value', min: (starts.length ? Math.min(...starts) / 86_400_000 : 0), axisLabel: { color: axisText, formatter: (value: number) => new Date(value * 86_400_000).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' }) }, splitLine: { lineStyle: { color: splitLine } } }, yAxis: { type: 'category', data: items.map((item) => item.name), axisLabel: { color: axisText } }, series: [{ type: 'bar', stack: 'work', silent: true, itemStyle: { color: 'transparent' }, data: starts.map((value) => value / 86_400_000) }, { type: 'bar', stack: 'work', data: durations, itemStyle: { color: cyanColor, borderRadius: 3 }, label: { show: true, position: 'inside', formatter: 'ТО' } }] };
}
