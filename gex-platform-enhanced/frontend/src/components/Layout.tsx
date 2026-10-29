// Screen: Shared layout component — all authenticated screens
import { Outlet } from 'react-router-dom';
import { TopBar } from './TopBar';
import { MenuAccessGuard } from './MenuAccessGuard';
import { ScreenGateLine } from './ScreenGateLine';
import { useUserRole } from '@/contexts/UserRoleContext';
import { useScreenAccessRules } from '@/lib/screenAccess';

export function Layout() {
  // The company's CISO screen rules are loaded here, above the menu and the
  // address-bar guard, so both re-render when they arrive or change.
  const { role } = useUserRole();
  const { ready } = useScreenAccessRules(role?.company_name);
  return (
    <div className="min-h-screen" style={{ background: 'var(--bg, #f3f4f2)' }}>
      <TopBar />
      <main className="w-full max-w-[1680px] mx-auto px-6 py-6">
        <MenuAccessGuard rulesReady={ready}>
          <ScreenGateLine />
          <Outlet />
        </MenuAccessGuard>
      </main>
    </div>
  );
}
