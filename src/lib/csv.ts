export type CsvColumn<T> = { key: keyof T & string; label: string };

function escapeValue(value: unknown) {
  const text = String(value ?? '');
  const isNumericPrimitive = typeof value === 'number' || typeof value === 'bigint';
  const safeText = !isNumericPrimitive && /^[\s\x00-\x1f\x7f-\x9f]*[=+\-@]/.test(text) ? `'${text}` : text;
  return /[;,"\r\n]/.test(safeText) ? `"${safeText.replaceAll('"', '""')}"` : safeText;
}

export function toCsv<T extends object>(rows: T[], columns: CsvColumn<T>[]) {
  return [columns.map((column) => escapeValue(column.label)).join(';'), ...rows.map((row) => columns.map((column) => escapeValue(row[column.key])).join(';'))].join('\n');
}

export function downloadCsv(filename: string, content: string) {
  const blob = new Blob([`\uFEFF${content}`], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
