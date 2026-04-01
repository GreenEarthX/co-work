import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Settings, LogOut, Leaf } from 'lucide-react';
import { MENU_TABS, CISO_ITEMS, isVisible } from '@/config/menuArchitecture';
import { useUserRole } from '@/contexts/UserRoleContext';
import { TopBarDropdown } from './TopBarDropdown';
import { CISOGate } from './CISOGate';

export function TopBar() {
  const { role, sessionTier, logout } = useUserRole();
  const navigate = useNavigate();
  const [openTab, setOpenTab] = useState<string | null>(null);
  const [cisoOpen, setCisoOpen] = useState(false);
  const [cisoAuthed, setCisoAuthed] = useState(
    () => sessionStorage.getItem('gex_ciso_session') === 'true'
  );
  const [logoError, setLogoError] = useState(false);
  const closeTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest('[data-topbar]')) {
        setOpenTab(null);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  // Reset logo error when company changes
  useEffect(() => { setLogoError(false); }, [role.company_logo_url]);

  const handleTabEnter = (tabId: string) => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    setOpenTab(tabId);
  };

  const handleTabLeave = () => {
    closeTimer.current = setTimeout(() => setOpenTab(null), 200);
  };

  const handleCISOClick = () => {
    if (cisoAuthed) {
      setOpenTab(openTab === 'ciso' ? null : 'ciso');
    } else {
      setCisoOpen(true);
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const functionLabel = role.business_function.replace(/_/g, ' ');
  const companyLabel = role.company_type === 'THIRD_PARTY'
    ? (role.service_type ?? 'SERVICE PROVIDER')
    : role.company_type;

  // Company logo: URL if set and not broken, else initial letter
  const showLogo = !!role.company_logo_url && !logoError;
  const companyInitial = (role.company_name ?? 'G').charAt(0).toUpperCase();

  return (
    <>
      <div
        data-topbar
        className="h-14 border-b flex items-center px-5 gap-0 sticky top-0 z-40 backdrop-blur"
        style={{
          background: 'rgba(243, 244, 242, 0.94)',
          borderColor: 'var(--border)',
        }}
      >
        {/* GEX platform logo */}
        <button
          onClick={() => navigate('/dashboard')}
          className="flex items-center gap-3 mr-8 flex-shrink-0"
        >
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center border"
            style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
          >
            <Leaf className="w-4 h-4" style={{ color: 'var(--brand)' }} />
          </div>
          <span className="text-sm font-semibold tracking-[0.16em]" style={{ color: 'var(--text-primary)' }}>
            GEX
          </span>
        </button>

        {/* Business-line tabs */}
        {MENU_TABS.map((tab) => {
          const visibleItems = tab.items.filter((item) => isVisible(item, role));
          const isOpen = openTab === tab.id;

          return (
            <div
              key={tab.id}
              className="relative"
              onMouseEnter={() => handleTabEnter(tab.id)}
              onMouseLeave={handleTabLeave}
            >
              <button
                onClick={() => setOpenTab(isOpen ? null : tab.id)}
                className="px-3 py-2 text-sm font-medium transition-colors rounded-lg"
                style={isOpen
                  ? { color: 'var(--text-primary)', background: 'var(--surface)' }
                  : { color: 'var(--text-secondary)' }}
              >
                {tab.label}
                <span className="ml-1 text-[10px]" style={{ color: 'var(--text-muted)' }}>▾</span>
              </button>
              {isOpen && (
                <TopBarDropdown
                  label={tab.label}
                  items={visibleItems}
                  isActive={isOpen}
                  onClose={() => setOpenTab(null)}
                />
              )}
            </div>
          );
        })}

        {/* Spacer */}
        <div className="flex-1" />

        {/* Role indicator */}
        <div className="flex items-center gap-2 mr-4">
          <span className="text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--text-muted)' }}>
            {companyLabel}
          </span>
          <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>·</span>
          <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
            {functionLabel}
          </span>
        </div>

        {/* User name */}
        <span className="text-xs mr-3" style={{ color: 'var(--text-secondary)' }}>{role.user_name}</span>

        {/* Company logo / initial — top-right, before CISO gear */}
        <div className="mr-2 flex-shrink-0">
          {showLogo ? (
            <img
              src={role.company_logo_url}
              alt={role.company_name}
              onError={() => setLogoError(true)}
              className="w-8 h-8 rounded-lg object-contain border"
              style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
            />
          ) : (
            <div
              title={role.company_name}
              className="w-8 h-8 rounded-lg border
                         flex items-center justify-center
                         text-xs font-semibold"
              style={{
                background: 'var(--surface)',
                borderColor: 'var(--border)',
                color: 'var(--text-secondary)',
              }}
            >
              {companyInitial}
            </div>
          )}
        </div>

        {/* CISO admin — always visible, amber when locked, indigo when authed */}
        <div className="relative mr-1">
          <button
            onClick={handleCISOClick}
            title={cisoAuthed ? 'CISO Admin — authenticated' : 'CISO Administration (password required)'}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold border transition-colors"
            style={cisoAuthed
              ? {
                  borderColor: '#b8c9d4',
                  background: '#eef4f6',
                  color: '#395566',
                }
              : {
                  borderColor: '#d8cfbf',
                  background: '#f5f0e7',
                  color: '#7a6340',
                }}
          >
            <Settings className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">CISO</span>
            {cisoAuthed && <span className="w-1.5 h-1.5 rounded-full bg-slate-500" />}
          </button>

          {/* CISO dropdown when authed */}
          {openTab === 'ciso' && cisoAuthed && (
            <div className="absolute right-0 top-10">
              <TopBarDropdown
                label="CISO Admin"
                items={CISO_ITEMS}
                isActive={true}
                onClose={() => setOpenTab(null)}
              />
            </div>
          )}
        </div>

        {/* Logout (authenticated only) */}
        {sessionTier === 'authenticated' && (
          <button
            onClick={handleLogout}
            title="Sign out"
            className="p-2 rounded-lg transition-colors"
            style={{ color: 'var(--text-muted)' }}
          >
            <LogOut className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* CISO password gate */}
      <CISOGate
        isOpen={cisoOpen}
        onClose={() => setCisoOpen(false)}
        onAuthenticated={() => {
          setCisoOpen(false);
          setCisoAuthed(true);
          setOpenTab('ciso');
        }}
      />
    </>
  );
}
