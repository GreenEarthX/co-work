import { Outlet } from 'react-router-dom';
import { TopBar } from './TopBar';

export function Layout() {
  return (
    <div className="min-h-screen" style={{ background: 'var(--bg, #f3f4f2)' }}>
      <TopBar />
      <main className="w-full max-w-[1680px] mx-auto px-6 py-6">
        <Outlet />
      </main>
    </div>
  );
}
