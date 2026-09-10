import { useState } from 'react';
import { AlertCircle, CheckCircle2, Loader2, Plus } from 'lucide-react';

import { generateMaintenanceOrders } from '../../api/client';
import { useMaintenanceOrdersQuery } from '../../api/queries';
import { Badge } from '../../components/ui/Badge';
import { Card } from '../../components/ui/Card';
import { SectionHeader } from '../../components/ui/SectionHeader';
import type { MaintenanceOrder, MaintenancePriority } from '../../types';
import { useSecurityContext } from '../../contexts/security';

const priorityConfig: Record<MaintenancePriority, { label: string; tone: 'success' | 'info' | 'warning' | 'danger' }> = {
  low: { label: 'Низкий', tone: 'success' },
  medium: { label: 'Средний', tone: 'info' },
  high: { label: 'Высокий', tone: 'warning' },
  critical: { label: 'Критический', tone: 'danger' },
};

const statusConfig: Record<string, { label: string; icon: React.ReactNode }> = {
  draft: { label: 'Черновик', icon: '📋' },
  pending_approval: { label: 'На утверждении', icon: '⏳' },
  approved: { label: 'Утверждена', icon: '✅' },
  completed: { label: 'Завершена', icon: '🔒' },
};

export function MaintenanceHub() {
  const { context } = useSecurityContext();
  const { data: orders, isLoading, error } = useMaintenanceOrdersQuery(context);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generatedCount, setGeneratedCount] = useState(0);

  const handleGenerateOrders = async () => {
    try {
      setIsGenerating(true);
      const response = await generateMaintenanceOrders(context, false);
      setGeneratedCount(response.generated_count);
      // Refresh orders after generation
      setTimeout(() => {
        window.location.reload();
      }, 1000);
    } catch (err) {
      console.error('Failed to generate orders:', err);
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow="Управление ППР"
        title="Заявки и планы превентивного обслуживания"
        action={
          <button
            onClick={handleGenerateOrders}
            disabled={isGenerating}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-cyan-500 text-slate-900 font-medium hover:bg-cyan-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isGenerating ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Plus className="w-4 h-4" />
            )}
            Сгенерировать заявки
          </button>
        }
      />

      {generatedCount > 0 && (
        <div className="p-4 bg-emerald-900 border border-emerald-600 rounded-lg text-emerald-100 flex items-center gap-2">
          <CheckCircle2 className="w-5 h-5" />
          <span>Успешно создано {generatedCount} заявок на обслуживание</span>
        </div>
      )}

      {error && (
        <div className="p-4 bg-rose-900 border border-rose-600 rounded-lg text-rose-100 flex items-center gap-2">
          <AlertCircle className="w-5 h-5" />
          <span>Ошибка загрузки заявок</span>
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-slate-500" />
        </div>
      ) : orders && orders.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700">
                <th className="px-4 py-3 text-left font-semibold text-slate-300">ID заявки</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-300">Объект</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-300">Категория</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-300">Приоритет</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-300">Статус</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-300">Срок (ч)</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-300">Действие</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order: MaintenanceOrder) => (
                <tr key={order.order_id} className="border-b border-slate-700 hover:bg-slate-800/30">
                  <td className="px-4 py-3 font-mono text-cyan-400">{order.order_id}</td>
                  <td className="px-4 py-3 text-slate-200">{order.target_id}</td>
                  <td className="px-4 py-3">
                    <span className="text-xs px-2 py-1 rounded bg-slate-700 text-slate-300">
                      {order.risk_category}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={priorityConfig[order.priority].tone}>
                      {priorityConfig[order.priority].label}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span>{statusConfig[order.status].icon}</span>
                      <span className="text-xs">{statusConfig[order.status].label}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-24 bg-slate-700 rounded-full h-2 overflow-hidden">
                        <div
                          className={`h-full ${
                            order.deadline_hours > 72
                              ? 'bg-emerald-500'
                              : order.deadline_hours > 24
                                ? 'bg-amber-500'
                                : 'bg-rose-500'
                          }`}
                          style={{ width: `${Math.min(100, (order.deadline_hours / 168) * 100)}%` }}
                        />
                      </div>
                      <span className="text-xs text-slate-400 w-10">{order.deadline_hours}ч</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <button className="text-xs px-3 py-1 rounded bg-slate-700 hover:bg-slate-600 text-slate-200 transition-colors">
                      Подробнее
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Card title="Нет активных заявок" subtitle="Все системы в норме">
          <p className="text-slate-400 text-sm">
            Нажмите кнопку «Сгенерировать заявки» для преобразования рисков в заявки на обслуживание.
          </p>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Информация о регламентах">
          <div className="space-y-3 text-sm text-slate-300">
            <p>
              <strong>Нормативная база:</strong> ГОСТ Р, СНиП, ГОСТ 55275-2012, ГОСТ 12.1.004-91
            </p>
            <p>
              <strong>Зоны ответственности:</strong> РЭК-1, РЭК-2, РЭК-3, РЭК-4
            </p>
            <p className="text-xs text-slate-400">
              Заявки генерируются автоматически из прогнозов модели рисков и могут быть утверждены диспетчером.
            </p>
          </div>
        </Card>

        <Card title="Статистика">
          <div className="space-y-3">
            <div className="flex justify-between items-center text-sm">
              <span className="text-slate-400">Всего заявок:</span>
              <span className="text-lg font-bold text-cyan-400">{orders?.length || 0}</span>
            </div>
            <div className="flex justify-between items-center text-sm">
              <span className="text-slate-400">Критических:</span>
              <span className="text-lg font-bold text-rose-400">
                {orders?.filter((o: MaintenanceOrder) => o.priority === 'critical').length || 0}
              </span>
            </div>
            <div className="flex justify-between items-center text-sm">
              <span className="text-slate-400">На утверждении:</span>
              <span className="text-lg font-bold text-amber-400">
                {orders?.filter((o: MaintenanceOrder) => o.status === 'pending_approval').length || 0}
              </span>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
