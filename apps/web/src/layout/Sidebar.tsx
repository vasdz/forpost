import { NavLink } from 'react-router-dom';
import { Activity, Shield, UploadCloud, Database } from 'lucide-react';

import { useSecurityContext } from '../contexts';

const nav = [
  { to: '/dashboard', label: 'Дашборд', icon: Activity },
  { to: '/risks', label: 'Реестр рисков', icon: Shield },
  { to: '/ingest', label: 'Загрузка данных', icon: UploadCloud },
  { to: '/audit', label: 'Аудит', icon: Database },
];

export function Sidebar() {
  const { context, contexts, setContextIndex } = useSecurityContext();

  return (
    <aside className="w-64 shrink-0 rounded-2xl bg-slate-900/80 p-4 text-sm text-slate-200">
      <div className="mb-6 flex items-center gap-3">
        <div className="h-10 w-10 rounded-md bg-cyan-600/20 flex items-center justify-center text-cyan-200">FP</div>
        <div>
          <div className="text-xs font-semibold tracking-wide text-slate-100">Форпост</div>
          <div className="text-[11px] text-slate-400">ODC Console</div>
        </div>
      </div>

      <nav className="mb-6 flex flex-col gap-2">
        {nav.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2 transition ${
                isActive ? 'bg-cyan-500/10 border border-cyan-500/30 text-cyan-100' : 'hover:bg-slate-800/60'
              }`
            }
          >
            <Icon className="h-4 w-4" />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="mt-auto space-y-2 border-t border-slate-800/60 pt-4">
        <div className="text-xs text-slate-400">Текущий контекст</div>
        <div className="flex items-center justify-between gap-2">
          <div>
            <div className="text-sm font-medium text-slate-100">{context.label}</div>
            <div className="text-[12px] text-slate-400">{context.role} • {context.districts.join(', ')}</div>
          </div>
        </div>

        <div className="mt-3 grid gap-2">
          {contexts.map((c, i: number) => (
            <button
              key={c.userId}
              onClick={() => setContextIndex(i)}
              className={`w-full rounded-md px-2 py-1 text-left text-xs transition ${
                c.userId === context.userId ? 'bg-cyan-500/10 border border-cyan-500/30 text-cyan-100' : 'bg-slate-950/70 hover:bg-slate-900'
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}
