import { Outlet } from 'react-router-dom';
import { TopBar } from './TopBar';

export function Layout() {
  return (
    <div className="min-h-screen" style={{ background: 'var(--surface, #0f1117)' }}>
      <TopBar />
      <main className="w-full max-w-[1920px] mx-auto px-5 py-5">
        <Outlet />
      </main>
    </div>
  );
}
