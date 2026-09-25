'use client';

import { useEffect, useState } from 'react';
import { PageHeader } from '@/components/features/PageHeader';
import { Card } from '@/components/ui/Card';
import { Select } from '@/components/ui/Select';

type WorkspaceSettings = { density: 'comfortable' | 'compact'; defaultRange: 'day' | 'week' | 'month'; showMarkers: boolean };
const initial: WorkspaceSettings = { density: 'comfortable', defaultRange: 'day', showMarkers: true };

export default function DesignSystemPage() {
  const [settings, setSettings] = useState(initial);
  useEffect(() => { const saved = window.localStorage.getItem('forpost-workspace-settings'); if (saved) { try { setSettings({ ...initial, ...JSON.parse(saved) }); } catch { /* local preference is optional */ } } }, []);
  const update = (patch: Partial<WorkspaceSettings>) => setSettings((value) => { const next = { ...value, ...patch }; window.localStorage.setItem('forpost-workspace-settings', JSON.stringify(next)); return next; });
  return <><PageHeader eyebrow="Системный раздел" title="Настройки рабочего места" description="Локальные параметры отображения сохраняются только в браузере и не меняют модель, данные или права доступа." /><Card className="max-w-3xl space-y-6 p-5"><section><h2 className="font-heading text-lg font-semibold">Временная шкала</h2><p className="mt-1 text-sm text-[var(--color-text-muted)]">Стартовый диапазон применяется при следующем открытии рабочего места.</p><div className="mt-4 max-w-xs"><Select label="Диапазон по умолчанию" value={settings.defaultRange} onChange={(event) => update({ defaultRange: event.target.value as WorkspaceSettings['defaultRange'] })} options={[{ value: 'day', label: 'День' }, { value: 'week', label: 'Неделя' }, { value: 'month', label: 'Месяц' }]} /></div><label className="mt-4 flex items-center gap-2 text-sm"><input type="checkbox" checked={settings.showMarkers} onChange={(event) => update({ showMarkers: event.target.checked })} />Показывать маркеры сработок на шкале</label></section><section className="border-t border-[var(--color-border)] pt-5"><h2 className="font-heading text-lg font-semibold">Плотность интерфейса</h2><div className="mt-4 max-w-xs"><Select label="Плотность таблиц" value={settings.density} onChange={(event) => update({ density: event.target.value as WorkspaceSettings['density'] })} options={[{ value: 'comfortable', label: 'Обычная' }, { value: 'compact', label: 'Компактная' }]} /></div></section><p className="border-t border-[var(--color-border)] pt-4 text-xs text-[var(--color-text-muted)]">Порог модели, горизонт прогноза и источники данных здесь намеренно не меняются: они принадлежат опубликованному ML-релизу и его model card.</p></Card></>;
}
