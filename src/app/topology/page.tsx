'use client';

import { useEffect, useMemo, useState } from 'react';
import { Minus, Move, Plus, RotateCcw } from 'lucide-react';
import { PageHeader } from '@/components/features/PageHeader';
import { SourceBadge } from '@/components/features/SourceBadge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Table, type TableColumn } from '@/components/ui/Table';
import { fetchTopology, type TopologyFeature, type TopologyFeatureCollection } from '@/data/operationsClient';

type TopologyRow = TopologyFeature['properties'] & { id: string };
const columns: TableColumn<TopologyRow>[] = [
  { key: 'objectId', label: 'ID объекта', sortable: true, render: (row) => <span className="font-telemetry">{row.objectId}</span> },
  { key: 'dispatcherName', label: 'Диспетчерское наименование', sortable: true },
  { key: 'objectKind', label: 'Тип', sortable: true },
  { key: 'parentId', label: 'Родитель', render: (row) => <span className="font-telemetry">{row.parentId ?? 'Корневой узел'}</span> },
  { key: 'coordinateProvenance', label: 'Координаты', render: () => <SourceBadge provenance="simulated" /> },
];

function SchematicDiagram({ topology }: { topology: TopologyFeatureCollection }) {
  const [scale, setScale] = useState(1); const [pan, setPan] = useState({ x: 0, y: 0 });
  const [drag, setDrag] = useState<{ x: number; y: number; panX: number; panY: number } | null>(null);
  const points = useMemo(() => topology.features.flatMap((feature) => feature.geometry.coordinates.flat()), [topology]);
  const xs = points.map(([x]) => x); const ys = points.map(([, y]) => y);
  const box = `${Math.min(...xs, 0) - 1} ${Math.min(...ys, 0) - 1} ${Math.max(Math.max(...xs, 1) - Math.min(...xs, 0) + 2, 2)} ${Math.max(Math.max(...ys, 1) - Math.min(...ys, 0) + 2, 2)}`;
  const reset = () => { setScale(1); setPan({ x: 0, y: 0 }); };
  return <Card className="overflow-hidden p-0"><div className="flex items-center justify-between border-b border-[var(--color-border)] px-3 py-2"><span className="text-xs text-[var(--color-text-muted)]"><Move size={14} className="mr-1 inline" />Перетаскивайте; масштаб {Math.round(scale * 100)}%</span><div className="flex gap-1"><Button size="sm" variant="ghost" aria-label="Уменьшить масштаб" onClick={() => setScale((v) => Math.max(.5, v - .2))}><Minus size={15} /></Button><Button size="sm" variant="ghost" aria-label="Увеличить масштаб" onClick={() => setScale((v) => Math.min(4, v + .2))}><Plus size={15} /></Button><Button size="sm" variant="ghost" aria-label="Сбросить вид схемы" onClick={reset}><RotateCcw size={15} /></Button></div></div><div className="h-[430px] touch-none cursor-grab overflow-hidden bg-[var(--color-panel-2)] active:cursor-grabbing" onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); setDrag({ x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y }); }} onPointerMove={(e) => { if (drag) setPan({ x: drag.panX + e.clientX - drag.x, y: drag.panY + e.clientY - drag.y }); }} onPointerUp={() => setDrag(null)} onWheel={(e) => { e.preventDefault(); setScale((v) => Math.max(.5, Math.min(4, v + (e.deltaY < 0 ? .15 : -.15)))); }}><svg role="img" aria-labelledby="topology-title topology-desc" viewBox={box} className="h-full w-full origin-center transition-transform duration-100" style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})` }}><title id="topology-title">Условная схема объектов</title><desc id="topology-desc">Связи объектов из локального снимка; координаты не являются географическими.</desc>{topology.features.flatMap((feature) => feature.geometry.coordinates.map((line, index) => <polyline key={`${feature.id}-${index}`} points={line.map(([x, y]) => `${x},${y}`).join(' ')} fill="none" stroke="var(--color-data)" strokeWidth="0.08" vectorEffect="non-scaling-stroke" />))}</svg></div></Card>;
}

export default function TopologyPage() {
  const [topology, setTopology] = useState<TopologyFeatureCollection>(); const [error, setError] = useState<string>();
  useEffect(() => { let active = true; fetchTopology().then((result) => { if (active) setTopology(result); }).catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : 'Неизвестная ошибка'); }); return () => { active = false; }; }, []);
  const rows = topology?.features.map((feature) => ({ ...feature.properties, id: feature.id })) ?? [];
  return <><PageHeader eyebrow="Инженерная структура" title="Схема объектов" description="Негеографическое представление подтверждённой иерархии объектов локального источника." /><div role="note" className="mb-4 flex flex-wrap items-center gap-3 border-l-2 border-l-[var(--color-warning)] bg-[var(--color-panel)] p-4 text-sm"><SourceBadge provenance="simulated" /><strong>Координаты условные:</strong><span>реальны ID и иерархия из снимка, но это не карта Москвы.</span></div><div className="space-y-4">{topology && <SchematicDiagram topology={topology} />}<Table ariaLabel="Табличное представление схемы объектов" columns={columns} rows={rows} loading={!topology && !error} error={error} pageSize={12} /></div></>;
}
