'use client';

import dynamic from 'next/dynamic';
import type { EChartsOption } from 'echarts';
import { useEffect, useState } from 'react';
import { Skeleton } from '@/components/ui/Skeleton';
import { ChartDataTable } from './ChartDataTable';

const ReactECharts = dynamic(() => import('echarts-for-react'), { ssr: false, loading: () => <Skeleton className="h-full min-h-48 w-full" /> });

export function Chart({ option, label, description, height = 260, columns, rows }: { option: EChartsOption; label: string; description: string; height?: number; columns: string[]; rows: Array<Array<string | number>> }) {
  const [reducedMotion, setReducedMotion] = useState(true);
  useEffect(() => {
    if (!window.matchMedia) return;
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReducedMotion(media.matches);
    update(); media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  return <figure aria-label={label} className="min-w-0"><div aria-hidden="true"><ReactECharts option={{ ...option, animation: !reducedMotion, animationDuration: 200, animationDurationUpdate: 200, animationEasing: 'cubicOut', animationEasingUpdate: 'cubicOut' }} style={{ height, width: '100%' }} notMerge lazyUpdate opts={{ renderer: 'svg' }} /></div><figcaption className="sr-only">{description}</figcaption><ChartDataTable label={label} columns={columns} rows={rows} /></figure>;
}
