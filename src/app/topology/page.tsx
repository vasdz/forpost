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
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const points = useMemo(() => topology.features.flatMap((feature) => feature.geometry.coordinates.flat()), [topology]);
  const xs = points.map(([x]) => x); const ys = points.map(([, y]) => y);
  const box = `${Math.min(...xs, 0) - 1} ${Math.min(...ys, 0) - 1} ${Math.max(Math.max(...xs, 1) - Math.min(...xs, 0) + 2, 2)} ${Math.max(Math.max(...ys, 1) - Math.min(...ys, 0) + 2, 2)}`;
  const reset = () => { setScale(1); setPan({ x: 0, y: 0 }); };
  const nodes = topology.features.map((feature) => ({ feature, point: feature.geometry.coordinates.at(-1)?.at(-1) })).filter((node): node is { feature: TopologyFeature; point: number[] } => node.point !== undefined);
  const selected = topology.features.find((feature) => feature.id === selectedId);
  return (
    <Card className="overflow-hidden p-0">
      <div className="flex items-center justify-between border-b border-[var(--color-border)] px-3 py-2">
        <span className="text-xs text-[var(--color-text-muted)]"><Move size={14} className="mr-1 inline" />Перетаскивайте, нажимайте ресурсы; масштаб {Math.round(scale * 100)}%</span>
        <div className="flex gap-1">
          <Button size="sm" variant="ghost" aria-label="Уменьшить масштаб" onClick={() => setScale((value) => Math.max(.5, value - .2))}><Minus size={15} /></Button>
          <Button size="sm" variant="ghost" aria-label="Увеличить масштаб" onClick={() => setScale((value) => Math.min(4, value + .2))}><Plus size={15} /></Button>
          <Button size="sm" variant="ghost" aria-label="Сбросить вид схемы" onClick={reset}><RotateCcw size={15} /></Button>
        </div>
      </div>
      {selected && <div className="grid grid-cols-1 gap-2 border-b border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-3 text-xs md:grid-cols-4"><span><b>Ресурс:</b> {selected.properties.dispatcherName}</span><span><b>ID:</b> {selected.properties.objectId}</span><span><b>Тип:</b> {selected.properties.objectKind}</span><span><b>Родитель:</b> {selected.properties.parentId ?? 'корневой узел'}</span></div>}
      <div className="h-[430px] touch-none cursor-grab overflow-hidden bg-[var(--color-panel-2)] active:cursor-grabbing" onPointerDown={(event) => { event.currentTarget.setPointerCapture(event.pointerId); setDrag({ x: event.clientX, y: event.clientY, panX: pan.x, panY: pan.y }); }} onPointerMove={(event) => { if (drag) setPan({ x: drag.panX + event.clientX - drag.x, y: drag.panY + event.clientY - drag.y }); }} onPointerUp={() => setDrag(null)} onWheel={(event) => { event.preventDefault(); setScale((value) => Math.max(.5, Math.min(4, value + (event.deltaY < 0 ? .15 : -.15)))); }}>
        <svg role="img" aria-labelledby="topology-title topology-desc" viewBox={box} className="h-full w-full origin-center transition-transform duration-100" style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})` }}>
          <title id="topology-title">Условная схема объектов</title>
          <desc id="topology-desc">На концах линий показаны ресурсы из локального снимка. Нажмите ресурс, чтобы прочитать имя, ID и тип. Координаты не являются географическими.</desc>
          {topology.features.flatMap((feature) => feature.geometry.coordinates.map((line, index) => <polyline key={`${feature.id}-${index}`} points={line.map(([x, y]) => `${x},${y}`).join(' ')} fill="none" stroke="var(--color-data)" strokeWidth="0.08" vectorEffect="non-scaling-stroke" />))}
          {nodes.map(({ feature, point }) => {
            const showLabel = selectedId === feature.id || (scale >= 2.8 && feature.properties.parentId === null);
            return <g key={feature.id} onClick={(event) => { event.stopPropagation(); setSelectedId(feature.id); }} className="cursor-pointer"><rect x={point[0] - .2} y={point[1] - .2} width=".4" height=".4" rx=".05" fill={selectedId === feature.id ? 'var(--color-warning)' : 'var(--color-data)'} vectorEffect="non-scaling-stroke" /><title>{`Ресурс: ${feature.properties.dispatcherName} · ID ${feature.properties.objectId} · ${feature.properties.objectKind}`}</title>{showLabel && <><text x={point[0] + .3} y={point[1] - .15} fill="var(--color-text)" fontSize="0.42" stroke="var(--color-panel-2)" strokeWidth="0.08" paintOrder="stroke">{feature.properties.dispatcherName}</text><text x={point[0] + .3} y={point[1] + .35} fill="var(--color-text-muted)" fontSize="0.32" stroke="var(--color-panel-2)" strokeWidth="0.06" paintOrder="stroke">ID {feature.properties.objectId} · {feature.properties.objectKind}</text></>}</g>;
          })}
        </svg>
      </div>
      <p className="border-t border-[var(--color-border)] px-4 py-2 text-xs text-[var(--color-text-muted)]"><span className="mr-3 inline-flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-sm bg-[var(--color-data)]" /> Ресурс из снимка</span>Линии — иерархические связи. Нажмите ресурс, чтобы показать подпись; координаты условные.</p>
    </Card>
  );
}

export default function TopologyPage() {
  const [topology, setTopology] = useState<TopologyFeatureCollection>(); const [error, setError] = useState<string>();
  useEffect(() => { let active = true; fetchTopology().then((result) => { if (active) setTopology(result); }).catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : 'Неизвестная ошибка'); }); return () => { active = false; }; }, []);
  const rows = topology?.features.map((feature) => ({ ...feature.properties, id: feature.id })) ?? [];
  return <><PageHeader eyebrow="Инженерная структура" title="Схема объектов" description="Негеографическое представление подтверждённой иерархии объектов локального источника." /><div role="note" className="mb-4 flex flex-wrap items-center gap-3 border-l-2 border-l-[var(--color-warning)] bg-[var(--color-panel)] p-4 text-sm"><SourceBadge provenance="simulated" /><strong>Координаты условные:</strong><span>реальны ID и иерархия из снимка, но это не карта Москвы.</span></div><div className="space-y-4">{topology && <SchematicDiagram topology={topology} />}<Table ariaLabel="Табличное представление схемы объектов" columns={columns} rows={rows} loading={!topology && !error} error={error} pageSize={12} /></div></>;
}
