import { Sparkline } from './Sparkline';

export function LiveIndicator({ value, label, points, unit = '%', threshold }: { value: number; label: string; points: number[]; unit?: string; threshold?: number }) {
  const trend = points.length > 1 ? Math.round(points.at(-1)! - points[0]) : 0;
  const direction = trend > 0 ? 'рост' : trend < 0 ? 'снижение' : 'без изменений';
  return <div className="mt-5" aria-label={label}>
    <div className="flex items-end justify-between gap-4">
      <div>
        <p className="font-telemetry text-[36px] leading-10 tracking-[-0.06em]">{value}{unit === '%' ? '%' : ` ${unit}`}</p>
        <p className="mt-2 text-xs text-[var(--color-text-muted)]">{label} · {direction}</p>
        {threshold !== undefined && <><p className="mt-2 text-xs">Порог: {threshold} {unit}</p><p className="mt-1 text-xs">Статус: {value > threshold ? 'Порог превышен' : 'Штатно'}</p></>}
      </div>
      <span className="font-telemetry text-[11px] text-[var(--color-text-muted)]">{trend > 0 ? '+' : ''}{trend} {unit === '%' ? 'п.п.' : unit}</span>
    </div>
    <div className="mt-5 border-t border-[var(--color-border)] pt-3"><Sparkline label={`Динамика: ${label}`} points={points} color="var(--color-cyan)" /></div>
  </div>;
}
