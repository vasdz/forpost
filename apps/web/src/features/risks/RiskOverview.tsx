import { AlertTriangle, ShieldAlert, ShieldCheck, Zap } from 'lucide-react';

import { Badge } from '../../components/ui/Badge';
import { Card } from '../../components/ui/Card';
import { SectionHeader } from '../../components/ui/SectionHeader';
import type { RiskPrediction } from '../../types';

const categoryNames: Record<string, string> = {
  sensor_failure: 'Отказ СМВУ',
  fire_risk: 'Пожарный риск',
  unauthorized_access: 'Несанкционированный доступ',
  infrastructure_wear: 'Износ конструкции',
};

const statusByProbability = (probability: number): 'success' | 'warning' | 'danger' => {
  if (probability >= 0.7) return 'danger';
  if (probability >= 0.4) return 'warning';
  return 'success';
};

interface RiskOverviewProps {
  risks: RiskPrediction[];
}

export function RiskOverview({ risks }: RiskOverviewProps) {
  const activeIncidents = risks.filter((risk) => risk.probability >= 0.45).length;
  const highRisk = risks.filter((risk) => risk.probability >= 0.7).length;
  const monitored24h = risks.filter((risk) => risk.horizon_hours >= 24).length;

  const categoryCards = Object.entries(categoryNames).map(([category, label]) => {
    const items = risks.filter((risk) => risk.category === category);
    const risk = items.length > 0 ? Math.max(...items.map((item) => item.probability)) : 0;
    const tone = statusByProbability(risk);

    return {
      label,
      count: items.length,
      risk,
      tone,
      category,
    };
  });

  return (
    <div className="space-y-6">
      <SectionHeader eyebrow="Network Operations Center" title="Executive Overview" />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Card>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Актуальные инциденты</p>
              <p className="mt-3 text-3xl font-semibold text-slate-50">{activeIncidents}</p>
            </div>
            <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-rose-200">
              <AlertTriangle className="h-5 w-5" />
            </div>
          </div>
        </Card>

        <Card>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Предупреждения 24h</p>
              <p className="mt-3 text-3xl font-semibold text-slate-50">{monitored24h}</p>
            </div>
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-amber-200">
              <ShieldAlert className="h-5 w-5" />
            </div>
          </div>
        </Card>

        <Card>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Критические риски</p>
              <p className="mt-3 text-3xl font-semibold text-slate-50">{highRisk}</p>
            </div>
            <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-red-200">
              <Zap className="h-5 w-5" />
            </div>
          </div>
        </Card>

        <Card>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Контур устойчивости</p>
              <p className="mt-3 text-3xl font-semibold text-slate-50">{Math.max(0, 100 - highRisk * 15)}%</p>
            </div>
            <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-emerald-200">
              <ShieldCheck className="h-5 w-5" />
            </div>
          </div>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-4">
        {categoryCards.map((card) => (
          <Card key={card.category} title={card.label} className="min-h-[170px]">
            <div className="flex items-center justify-between">
              <span className="text-xs uppercase tracking-[0.18em] text-slate-400">Плотность</span>
              <Badge tone={card.tone}>{card.tone === 'danger' ? 'Critical' : card.tone === 'warning' ? 'Elevated' : 'Stable'}</Badge>
            </div>
            <div className="mt-5 flex items-end justify-between gap-3">
              <div>
                <p className="text-3xl font-semibold text-slate-50">{card.count}</p>
                <p className="mt-1 text-xs text-slate-400">актуальных объектов</p>
              </div>
              <div className="text-right">
                <p className="text-xl font-semibold text-slate-50">{Math.round(card.risk * 100)}%</p>
                <p className="text-xs text-slate-400">вероятность</p>
              </div>
            </div>
            <div className="mt-5 h-2 rounded-full bg-slate-800">
              <div
                className={`h-full rounded-full ${
                  card.tone === 'danger'
                    ? 'bg-rose-500'
                    : card.tone === 'warning'
                      ? 'bg-amber-500'
                      : 'bg-emerald-500'
                }`}
                style={{ width: `${Math.min(100, Math.round(card.risk * 100))}%` }}
              />
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
