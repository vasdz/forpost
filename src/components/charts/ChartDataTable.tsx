export function ChartDataTable({ label, columns, rows }: { label: string; columns: string[]; rows: Array<Array<string | number>> }) {
  return <details className="mt-3 border-t border-[var(--color-border)] pt-3 text-xs">
    <summary className="cursor-pointer py-1 text-[11px] text-[var(--color-text-muted)] hover:text-[var(--color-text)]">Данные таблицей: {label}</summary>
    <div className="mt-2 max-h-64 overflow-auto rounded-[4px] border border-[var(--color-border)]"><table aria-label={label} className="w-full border-collapse text-left">
      <caption className="sr-only">{label}</caption>
      <thead className="bg-[var(--color-panel-2)]"><tr>{columns.map((column) => <th key={column} scope="col" className="border-b border-[var(--color-border)] p-2 text-[10px] uppercase tracking-[0.1em] text-[var(--color-text-dim)]">{column}</th>)}</tr></thead>
      <tbody>{rows.map((row, index) => <tr key={index}>{row.map((value, cell) => <td key={cell} className="border-b border-[var(--color-border)] p-2">{value}</td>)}</tr>)}</tbody>
    </table>{rows.length === 0 && <p className="p-2">Нет данных за выбранный период.</p>}</div>
  </details>;
}
