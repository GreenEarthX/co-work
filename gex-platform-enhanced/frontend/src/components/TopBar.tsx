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
        className="h-12 bg-gray-900 border-b border-gray-800 flex items-center px-4 gap-0 sticky top-0 z-40"
      >
        {/* GEX platform logo */}
        <button
          onClick={() => navigate('/dashboard')}
          className="flex items-center gap-2 mr-6 flex-shrink-0"
        >
          <div className="w-7 h-7 rounded-md bg-teal-600 flex items-center justify-center">
            <Leaf className="w-3.5 h-3.5 text-white" />
          </div>
          <span className="text-sm font-bold text-gray-200 tracking-wide">GEX</span>
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
                className={`px-3 py-2 text-sm font-medium transition-colors rounded-md
                  ${isOpen
                    ? 'text-white bg-gray-800'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
                  }`}
              >
                {tab.label}
                <span className="ml-1 text-[10px] text-gray-600">▾</span>
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
          <span className="text-[10px] text-gray-500 uppercase tracking-wider">
            {companyLabel}
          </span>
          <span className="text-[10px] text-gray-600">·</span>
          <span className="text-[10px] text-gray-500">
            {functionLabel}
          </span>
        </div>

        {/* User name */}
        <span className="text-xs text-gray-400 mr-3">{role.user_name}</span>

        {/* Company logo / initial — top-right, before CISO gear */}
        <div className="mr-2 flex-shrink-0">
          {showLogo ? (
            <img
              src={role.company_logo_url}
              alt={role.company_name}
              onError={() => setLogoError(true)}
              className="w-7 h-7 rounded-md object-contain bg-gray-800 border border-gray-700"
            />
          ) : (
            <div
              title={role.company_name}
              className="w-7 h-7 rounded-md bg-gray-700 border border-gray-600
                         flex items-center justify-center
                         text-xs font-bold text-gray-300"
            >
              {companyInitial}
            </div>
          )}
        </div>

        {/* CISO admin gear */}
        <div className="relative mr-1">
          <button
            onClick={handleCISOClick}
            className={`p-2 rounded-lg transition-colors ${
              cisoAuthed
                ? 'text-indigo-400 hover:bg-indigo-900/30'
                : 'text-gray-600 hover:text-gray-400 hover:bg-gray-800'
            }`}
            title="CISO Administration"
          >
            <Settings className="w-4 h-4" />
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
            className="p-2 rounded-lg text-gray-600 hover:text-red-400 hover:bg-red-900/20 transition-colors"
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
