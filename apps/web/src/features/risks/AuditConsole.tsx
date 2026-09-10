import { useState } from 'react';
import { ShieldCheck, TriangleAlert } from 'lucide-react';

import { verifyAuditChain, formatError } from '../../api/client';
import { Badge } from '../../components/ui/Badge';
import { Card } from '../../components/ui/Card';
import { SectionHeader } from '../../components/ui/SectionHeader';
import type { AuditVerifyResponse } from '../../types';
import { useSecurityContext } from '../../contexts';

export function AuditConsole() {
  const { context } = useSecurityContext();
  const [result, setResult] = useState<AuditVerifyResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleVerify = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await verifyAuditChain(context);
      setResult(response);
    } catch (caughtError) {
      setResult(null);
      setError(formatError(caughtError));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <SectionHeader eyebrow="Network Operations Center" title="Security & Audit" />
      <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <Card title="Security & Audit" subtitle="Проверка целостности WORM-реестра и мандатного разграничения">
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleVerify}
              disabled={isLoading}
              className="inline-flex items-center rounded-xl border border-cyan-500/40 bg-cyan-500/10 px-4 py-2 text-sm font-medium text-cyan-100 transition hover:bg-cyan-500/15 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isLoading ? 'Проверка...' : 'Проверить целостность цепочки'}
            </button>

            {result ? (
              <Badge tone={result.chain_intact ? 'success' : 'danger'}>
                {result.chain_intact ? 'Хеш-цепочка интактна' : 'Цепочка повреждена'}
              </Badge>
            ) : (
              <Badge tone="neutral">Ожидание проверки</Badge>
            )}
          </div>

          {error && (
            <div className="mt-4 flex items-start gap-3 rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-100">
              <TriangleAlert className="mt-0.5 h-5 w-5" />
              <span>{error}</span>
            </div>
          )}

          {result && (
            <dl className="mt-6 space-y-3 text-sm text-slate-300">
              <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                <dt>Статус</dt>
                <dd className="text-slate-100">{result.status}</dd>
              </div>
              <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                <dt>Всего записей</dt>
                <dd className="text-slate-100">{result.total_records}</dd>
              </div>
              <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                <dt>Цепочка интактна</dt>
                <dd className="text-slate-100">{result.chain_intact ? 'Да' : 'Нет'}</dd>
              </div>
            </dl>
          )}
        </Card>

        <Card title="ABAC Context" subtitle="Симуляция роли и разрешённых районов">
          <div className="space-y-3 text-sm text-slate-200">
            <div className="flex items-center justify-between rounded-xl border border-slate-700 bg-slate-950/70 p-3">
              <span>Субъект</span>
              <span className="font-medium text-slate-100">{context.label}</span>
            </div>
            <div className="flex items-center justify-between rounded-xl border border-slate-700 bg-slate-950/70 p-3">
              <span>Роль</span>
              <span className="font-medium text-slate-100">{context.role}</span>
            </div>
            <div className="flex items-center justify-between rounded-xl border border-slate-700 bg-slate-950/70 p-3">
              <span>Районы</span>
              <span className="font-medium text-slate-100">{context.districts.join(', ')}</span>
            </div>
            <div className="mt-4 flex items-center gap-2 rounded-xl border border-emerald-500/25 bg-emerald-500/5 p-3 text-emerald-200">
              <ShieldCheck className="h-5 w-5" />
              <span>Доступ к карте рисков мандатирован по разрешённым районам.</span>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
