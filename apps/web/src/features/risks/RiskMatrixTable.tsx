import { useState } from 'react';

import { Badge } from '../../components/ui/Badge';
import { Card } from '../../components/ui/Card';
import { SectionHeader } from '../../components/ui/SectionHeader';
import type { RiskPrediction } from '../../types';
import { useSecurityContext } from '../../contexts';

const targetDistrictMap: Record<string, string> = {
  'sensor-deg-014': 'rek-1',
  'collector-sector-9': 'rek-1',
  'picket-104-shaft': 'rek-3',
  'pump-station-02': 'rek-4',
};

const categoryLabels: Record<string, string> = {
  sensor_failure: 'sensor_failure',
  fire_risk: 'fire_risk',
  unauthorized_access: 'unauthorized_access',
  infrastructure_wear: 'infrastructure_wear',
};

interface RiskMatrixTableProps {
  risks: RiskPrediction[];
}

export function RiskMatrixTable({ risks }: RiskMatrixTableProps) {
  const { context } = useSecurityContext();
  const [districtFilter, setDistrictFilter] = useState<string>('all');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [selectedRiskId, setSelectedRiskId] = useState<string | null>(null);

  const enrichedRisks = risks.map((risk) => ({
    ...risk,
    district: targetDistrictMap[risk.target_id] ?? 'rek-2',
  }));

  const filteredRisks = enrichedRisks.filter((risk) => {
    const districtMatch = districtFilter === 'all' || risk.district === districtFilter;
    const categoryMatch = categoryFilter === 'all' || risk.category === categoryFilter;
    return districtMatch && categoryMatch;
  });

  const selectedRisk =
    filteredRisks.find((risk) => risk.prediction_id === selectedRiskId) ?? filteredRisks[0] ?? null;

  return (
    <div className="space-y-6">
      <SectionHeader eyebrow="Network Operations Center" title="Risk Matrix Table" />
      <div className="grid gap-6 xl:grid-cols-[1.7fr_0.9fr]">
        <Card title="Risk Matrix" subtitle="Реестр рисков по зонам и категориям">
          <div className="mb-4 flex flex-wrap gap-3">
            <select
              value={districtFilter}
              onChange={(event) => setDistrictFilter(event.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none"
            >
              <option value="all">Все районы</option>
              {Array.from(new Set(enrichedRisks.map((risk) => risk.district))).map((district) => (
                <option key={district} value={district}>
                  {district}
                </option>
              ))}
            </select>

            <select
              value={categoryFilter}
              onChange={(event) => setCategoryFilter(event.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none"
            >
              <option value="all">Все категории</option>
              {Object.entries(categoryLabels).map(([category, label]) => (
                <option key={category} value={category}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          <div className="overflow-hidden rounded-xl border border-slate-800">
            <table className="min-w-full divide-y divide-slate-800 text-left text-sm text-slate-200">
              <thead className="bg-slate-950/90 text-xs uppercase tracking-[0.12em] text-slate-400">
                <tr>
                  <th className="px-4 py-3">Объект</th>
                  <th className="px-4 py-3">Район</th>
                  <th className="px-4 py-3">Категория</th>
                  <th className="px-4 py-3">Вероятность</th>
                  <th className="px-4 py-3">Горизонт</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800 bg-slate-900/40">
                {filteredRisks.map((risk) => (
                  <tr
                    key={risk.prediction_id}
                    className={`cursor-pointer transition-colors ${
                      selectedRisk?.prediction_id === risk.prediction_id ? 'bg-cyan-500/5' : 'hover:bg-slate-800/60'
                    }`}
                    onClick={() => setSelectedRiskId(risk.prediction_id)}
                  >
                    <td className="px-4 py-3 font-medium text-slate-100">{risk.target_id}</td>
                    <td className="px-4 py-3">{risk.district}</td>
                    <td className="px-4 py-3">{risk.category}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <span>{(risk.probability * 100).toFixed(0)}%</span>
                        <div className="h-2 w-16 rounded-full bg-slate-700">
                          <div
                            className={`h-full rounded-full ${
                              risk.probability >= 0.7
                                ? 'bg-rose-500'
                                : risk.probability >= 0.4
                                  ? 'bg-amber-500'
                                  : 'bg-emerald-500'
                            }`}
                            style={{ width: `${Math.min(100, risk.probability * 100)}%` }}
                          />
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">{risk.horizon_hours} ч</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card title="Detail" subtitle={`Контекст доступа: ${context.label}`}>
          {selectedRisk ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.12em] text-slate-400">Объект</p>
                  <p className="mt-2 text-lg font-semibold text-slate-50">{selectedRisk.target_id}</p>
                </div>
                <Badge
                  tone={
                    selectedRisk.probability >= 0.7
                      ? 'danger'
                      : selectedRisk.probability >= 0.4
                        ? 'warning'
                        : 'success'
                  }
                >
                  {(selectedRisk.probability * 100).toFixed(0)}%
                </Badge>
              </div>

              <dl className="space-y-3 text-sm text-slate-300">
                <div className="flex justify-between gap-4 border-b border-slate-800 pb-2">
                  <dt>Район</dt>
                  <dd className="text-slate-100">{selectedRisk.district}</dd>
                </div>
                <div className="flex justify-between gap-4 border-b border-slate-800 pb-2">
                  <dt>Категория</dt>
                  <dd className="text-slate-100">{selectedRisk.category}</dd>
                </div>
                <div className="flex justify-between gap-4 border-b border-slate-800 pb-2">
                  <dt>Горизонт</dt>
                  <dd className="text-slate-100">{selectedRisk.horizon_hours} ч</dd>
                </div>
                <div className="flex justify-between gap-4 border-b border-slate-800 pb-2">
                  <dt>Версия модели</dt>
                  <dd className="text-slate-100">{selectedRisk.model_version}</dd>
                </div>
              </dl>

              <div>
                <p className="text-xs uppercase tracking-[0.12em] text-slate-400">Обоснование</p>
                <p className="mt-2 text-sm leading-6 text-slate-200">{selectedRisk.explanation}</p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-400">Нет данных по выбранному фильтру.</p>
          )}
        </Card>
      </div>
    </div>
  );
}
