'use client';

type RangeSliderProps = { label: string; min: number; max: number; step?: number; value: number; onChange: (value: number) => void; valueText: string };

export function RangeSlider({ label, min, max, step = 1, value, onChange, valueText }: RangeSliderProps) {
  return <label className="grid gap-1 text-xs text-[var(--color-text-muted)]"><span className="flex justify-between"><span>{label}</span><output className="font-telemetry text-[var(--color-text)]">{valueText}</output></span><input aria-label={label} type="range" min={min} max={max} step={step} value={value} onChange={(event) => onChange(Number(event.target.value))} /></label>;
}
