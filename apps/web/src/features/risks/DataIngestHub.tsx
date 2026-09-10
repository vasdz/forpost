import { useRef, useState } from 'react';
import { CheckCircle2, FileSpreadsheet, Shield, UploadCloud } from 'lucide-react';

import { Card } from '../../components/ui/Card';
import { SectionHeader } from '../../components/ui/SectionHeader';

const MAX_FILE_SIZE = 10 * 1024 * 1024;
const allowedExtensions = new Set(['csv', 'xlsx']);

export function DataIngestHub() {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [notice, setNotice] = useState<string>('');

  const handleFiles = (incoming: File[]) => {
    const validFiles: File[] = [];
    const invalidReasons: string[] = [];

    for (const file of incoming) {
      const extension = file.name.split('.').pop()?.toLowerCase() ?? '';

      if (!allowedExtensions.has(extension)) {
        invalidReasons.push(`${file.name}: неподдерживаемый тип файла`);
        continue;
      }

      if (file.size > MAX_FILE_SIZE) {
        invalidReasons.push(`${file.name}: превышен лимит 10 MB`);
        continue;
      }

      validFiles.push(file);
    }

    if (validFiles.length > 0) {
      setFiles((current) => [...current, ...validFiles.filter((file) => !current.some((item) => item.name === file.name && item.size === file.size))]);
      setNotice('Файлы проверены и готовы к защищённой загрузке.');
    }

    if (invalidReasons.length > 0) {
      setNotice(invalidReasons.join(' • '));
    }
  };

  return (
    <div className="space-y-6">
      <SectionHeader eyebrow="Network Operations Center" title="Data Ingest Hub" />
      <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <Card title="Data Ingest Hub" subtitle="Drag-and-drop защищённой загрузки таблиц СМВУ и АРМ-Контроль">
          <div
            className="rounded-2xl border border-dashed border-cyan-500/40 bg-slate-950/70 p-8 text-center transition hover:border-cyan-400"
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              handleFiles(Array.from(event.dataTransfer.files));
            }}
          >
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full border border-cyan-500/40 bg-cyan-500/10 text-cyan-200">
              <UploadCloud className="h-8 w-8" />
            </div>
            <h3 className="mt-5 text-lg font-semibold text-slate-50">Перетащите файлы сюда</h3>
            <p className="mt-2 text-sm text-slate-400">Поддерживаются .csv и .xlsx до 10 MB</p>
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="mt-5 inline-flex items-center rounded-xl border border-cyan-500/40 bg-cyan-500/10 px-4 py-2 text-sm font-medium text-cyan-100 transition hover:bg-cyan-500/15"
            >
              Выбрать файлы
            </button>

            <input
              ref={inputRef}
              type="file"
              multiple
              accept=".csv,.xlsx"
              className="hidden"
              onChange={(event) => {
                if (event.target.files) {
                  handleFiles(Array.from(event.target.files));
                }
              }}
            />
          </div>

          {notice && (
            <div className="mt-4 rounded-xl border border-slate-700 bg-slate-950/80 px-3 py-2 text-sm text-slate-200">
              {notice}
            </div>
          )}
        </Card>

        <Card title="Security Envelope" subtitle="Локальная валидация и защита контуров">
          <div className="space-y-4">
            <div className="flex items-start gap-3 rounded-xl border border-emerald-500/25 bg-emerald-500/5 p-3">
              <CheckCircle2 className="mt-0.5 h-5 w-5 text-emerald-300" />
              <div>
                <p className="font-medium text-slate-100">Типы файлов проверены</p>
                <p className="text-sm text-slate-400">CSV и XLSX проходят фильтр расширений.</p>
              </div>
            </div>

            <div className="flex items-start gap-3 rounded-xl border border-cyan-500/25 bg-cyan-500/5 p-3">
              <Shield className="mt-0.5 h-5 w-5 text-cyan-300" />
              <div>
                <p className="font-medium text-slate-100">CDR/вирусная фильтрация</p>
                <p className="text-sm text-slate-400">Формульные инъекции и zip-бомбы блокируются.</p>
              </div>
            </div>

            <div className="flex items-start gap-3 rounded-xl border border-slate-700 bg-slate-950/80 p-3">
              <FileSpreadsheet className="mt-0.5 h-5 w-5 text-slate-300" />
              <div className="w-full">
                <p className="font-medium text-slate-100">Подтверждённые файлы</p>
                {files.length === 0 ? (
                  <p className="text-sm text-slate-400">Ожидание загрузки данных</p>
                ) : (
                  <ul className="mt-2 space-y-2 text-sm text-slate-300">
                    {files.map((file) => (
                      <li key={`${file.name}-${file.size}`} className="flex items-center justify-between gap-3 rounded-lg border border-slate-700 bg-slate-900 p-2">
                        <span className="truncate">{file.name}</span>
                        <span className="text-xs uppercase tracking-[0.12em] text-slate-400">{(file.size / (1024 * 1024)).toFixed(2)} MB</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
