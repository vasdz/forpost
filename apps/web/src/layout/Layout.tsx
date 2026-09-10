import { Outlet } from 'react-router-dom';

import { Sidebar } from './Sidebar';

export function Layout() {
  return (
    <div className="min-h-screen bg-[#020817] text-slate-100 antialiased">
      <div className="mx-auto max-w-[1500px] px-4 py-6 md:px-6">
        <div className="flex gap-6">
          <Sidebar />
          <main className="flex-1">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
