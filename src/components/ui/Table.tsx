'use client';

import { useMemo, useState, type ReactNode } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { Button } from './Button';

export type TableColumn<T extends { id: string }> = { key: keyof T & string; label: string; sortable?: boolean; render?: (row: T) => ReactNode; className?: string };
type TableProps<T extends { id: string }> = { ariaLabel: string; columns: TableColumn<T>[]; rows: readonly T[]; pageSize?: number; rowKey?: (row: T) => string; onRowClick?: (row: T) => void; loading?: boolean; error?: string };

export function Table<T extends { id: string }>({ ariaLabel, columns, rows, pageSize = 8, rowKey = (row) => String(row.id), onRowClick, loading, error }: TableProps<T>) {
  const [sort, setSort] = useState<{ key: keyof T & string; direction: 'ascending' | 'descending' } | null>(null);
  const [page, setPage] = useState(0);
  const sorted = useMemo(() => !sort ? rows : [...rows].sort((left, right) => {
    const a = String(left[sort.key] ?? ''); const b = String(right[sort.key] ?? '');
    return a.localeCompare(b, 'ru', { numeric: true }) * (sort.direction === 'ascending' ? 1 : -1);
  }), [rows, sort]);
  const pageCount = Math.max(1, Math.ceil(sorted.length / pageSize));
  const safePage = Math.min(page, pageCount - 1);
  const visibleRows = sorted.slice(safePage * pageSize, (safePage + 1) * pageSize);
  const changeSort = (key: keyof T & string) => { setPage(0); setSort((current) => current?.key === key && current.direction === 'ascending' ? { key, direction: 'descending' } : { key, direction: 'ascending' }); };
  if (loading) return <p role="status" aria-busy="true" className="glass-surface p-5 text-sm text-[var(--color-text-muted)]">Загрузка данных: {ariaLabel}</p>;
  if (error) return <p role="alert" className="glass-surface p-5 text-sm">Не удалось загрузить данные: {error}</p>;
  return <div className="data-table-frame overflow-hidden"><div className="max-h-[460px] overflow-auto"><table aria-label={ariaLabel} className="w-full min-w-[620px] border-collapse text-left text-sm"><caption className="sr-only">{ariaLabel}</caption><thead className="sticky top-0 z-10 bg-[var(--color-panel-2)] backdrop-blur-xl"><tr>{columns.map((column) => <th key={column.key} scope="col" aria-sort={sort?.key === column.key ? sort.direction : 'none'} className="border-b border-[var(--color-border)] px-4 py-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--color-text-dim)]">{column.sortable ? <button type="button" onClick={() => changeSort(column.key)} className="inline-flex items-center gap-1.5 hover:text-[var(--color-text)]">{column.label}{sort?.key === column.key && (sort.direction === 'ascending' ? <ChevronUp size={13} /> : <ChevronDown size={13} />)}</button> : column.label}</th>)}{onRowClick && <th scope="col" className="px-4 py-3">Действие</th>}</tr></thead><tbody>{visibleRows.map((row) => <tr key={rowKey(row)} onClick={onRowClick ? () => onRowClick(row) : undefined} className={`border-b border-[var(--color-border)] last:border-0 hover:bg-[var(--color-hover)] ${onRowClick ? 'cursor-pointer' : ''}`}>{columns.map((column) => <td key={column.key} className="px-4 py-3.5">{column.render ? column.render(row) : String(row[column.key] ?? '—')}</td>)}{onRowClick && <td className="px-4 py-3.5"><Button size="sm" variant="secondary" aria-label={`Открыть запись ${row.id}`} onClick={(event) => { event.stopPropagation(); onRowClick(row); }}>Открыть</Button></td>}</tr>)}{!visibleRows.length && <tr><td colSpan={columns.length + (onRowClick ? 1 : 0)} className="p-6 text-center text-[var(--color-text-muted)]">Записи по заданным фильтрам не найдены.</td></tr>}</tbody></table></div><footer className="flex items-center justify-between border-t border-[var(--color-border)] bg-[var(--color-panel-2)] px-4 py-3 text-[11px] text-[var(--color-text-muted)]"><span>Страница {safePage + 1} из {pageCount}</span><div className="flex gap-2"><Button size="sm" variant="secondary" disabled={safePage === 0} onClick={() => setPage((current) => current - 1)}>Назад</Button><Button size="sm" variant="secondary" disabled={safePage >= pageCount - 1} onClick={() => setPage((current) => current + 1)}>Вперёд</Button></div></footer></div>;
}
