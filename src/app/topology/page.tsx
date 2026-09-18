'use client';

import { useEffect, useState } from 'react';

import { PageHeader } from '@/components/features/PageHeader';
import { SourceBadge } from '@/components/features/SourceBadge';
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
  const points = topology.features.flatMap((feature) => feature.geometry.coordinates.flat());
  const xs = points.map(([x]) => x);
  const ys = points.map(([, y]) => y);
  const minX = Math.min(...xs, 0) - 1;
  const maxX = Math.max(...xs, 1) + 1;
  const minY = Math.min(...ys, 0) - 1;
  const maxY = Math.max(...ys, 1) + 1;
  return <Card className="overflow-auto p-0"><svg role="img" aria-labelledby="topology-diagram-title topology-diagram-description" viewBox={`${minX} ${minY} ${Math.max(maxX - minX, 2)} ${Math.max(maxY - minY, 2)}`} className="h-[360px] min-w-[720px] w-full bg-[var(--color-panel-2)] p-5" preserveAspectRatio="xMidYMid meet"><title id="topology-diagram-title">Условная схема объектов</title><desc id="topology-diagram-description">Связи подтверждённой иерархии; координаты рассчитаны для компоновки и не являются географическими.</desc>{topology.features.flatMap((feature) => feature.geometry.coordinates.map((line, index) => <polyline key={`${feature.id}-${index}`} points={line.map(([x, y]) => `${x},${y}`).join(' ')} fill="none" stroke="var(--color-data)" strokeWidth="0.08" vectorEffect="non-scaling-stroke" />))}</svg></Card>;
}

export default function TopologyPage() {
  const [topology, setTopology] = useState<TopologyFeatureCollection>();
  const [error, setError] = useState<string>();
  useEffect(() => {
    let active = true;
    fetchTopology().then((result) => { if (active) setTopology(result); }).catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : 'Неизвестная ошибка'); });
    return () => { active = false; };
  }, []);
  const rows: TopologyRow[] = topology?.features.map((feature) => ({ ...feature.properties, id: feature.id })) ?? [];
  return <><PageHeader eyebrow="Инженерная структура" title="Схема объектов" description="Негеографическое представление подтверждённой иерархии объектов локального источника." /><div role="note" className="mb-4 flex flex-wrap items-center gap-3 border-l-2 border-l-[var(--color-warning)] bg-[var(--color-panel)] p-4 text-sm"><SourceBadge provenance="simulated" /><strong>Координаты условные:</strong><span>схема показывает структуру связей, а не расположение на карте Москвы.</span></div><div className="space-y-4">{topology && <SchematicDiagram topology={topology} />}<Table ariaLabel="Табличное представление схемы объектов" columns={columns} rows={rows} loading={!topology && !error} error={error} pageSize={12} /></div></>;
}
