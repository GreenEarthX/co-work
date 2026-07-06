// Screen: Shared layout component — all authenticated screens
import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Settings, LogOut } from "lucide-react";
import { MENU_TABS, CISO_ITEMS, isVisibleInNav } from "@/config/menuArchitecture";
import { useUserRole } from "@/contexts/UserRoleContext";
import { TopBarDropdown } from "./TopBarDropdown";
import { CISOGate } from "./CISOGate";

export function TopBar() {
  const { role, sessionTier, logout } = useUserRole();
  const navigate = useNavigate();
  const [openTab, setOpenTab] = useState<string | null>(null);
  const [cisoOpen, setCisoOpen] = useState(false);
  const [cisoAuthed, setCisoAuthed] = useState(
    () => sessionStorage.getItem("gex_ciso_session") === "true",
  );
  const [logoError, setLogoError] = useState(false);
  const closeTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest("[data-topbar]")) {
        setOpenTab(null);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Reset logo error when company changes
  useEffect(() => {
    setLogoError(false);
  }, [role.company_logo_url]);

  const handleTabEnter = (tabId: string) => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    setOpenTab(tabId);
  };

  const handleTabLeave = () => {
    closeTimer.current = setTimeout(() => setOpenTab(null), 200);
  };

  const handleCISOClick = () => {
    if (cisoAuthed) {
      setOpenTab(openTab === "ciso" ? null : "ciso");
    } else {
      setCisoOpen(true);
    }
  };

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const functionLabel = role.business_function.replace(/_/g, " ");
  const companyLabel =
    role.company_type === "THIRD_PARTY"
      ? (role.service_type ?? "SERVICE PROVIDER")
      : role.company_type;

  // Company logo: URL if set and not broken, else initial letter
  const showLogo = !!role.company_logo_url && !logoError;
  const companyInitial = (role.company_name ?? "G").charAt(0).toUpperCase();

  return (
    <>
      <div
        data-topbar
        className="h-20 border-b flex items-center px-6 gap-0 sticky top-0 z-40"
        style={{
          background: "#162126",
          borderColor: "rgba(255, 255, 255, 0.08)",
        }}
      >
        {/* GEX platform logo */}
        <button
          onClick={() => navigate("/dashboard")}
          className="mr-10 flex-shrink-0 px-1 py-1"
        >
          <img
            src="/GreenEarthX-updated.png"
            alt="GreenEarthX"
            className="h-11 w-auto object-contain drop-shadow-[0_1px_1px_rgba(0,0,0,0.18)] sm:h-12"
          />
        </button>

        {/* Business-line tabs */}
        {MENU_TABS.map((tab) => {
          // Nav prominence = visible AND not consult-only for this role.
          // Consult-only screens stay fully accessible via the Project profile.
          const visibleItems = tab.items.filter((item) =>
            isVisibleInNav(item, role),
          );
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
                style={
                  isOpen
                    ? {
                        color: "#ffffff",
                        background: "rgba(255, 255, 255, 0.1)",
                      }
                    : { color: "rgba(255, 255, 255, 0.74)" }
                }
              >
                {tab.label}
                <span
                  className="ml-1 text-[10px]"
                  style={{ color: "rgba(255, 255, 255, 0.42)" }}
                >
                  ▾
                </span>
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
          <span
            className="text-[10px] uppercase tracking-[0.14em]"
            style={{ color: "rgba(255, 255, 255, 0.46)" }}
          >
            {companyLabel}
          </span>
          <span
            className="text-[10px]"
            style={{ color: "rgba(255, 255, 255, 0.3)" }}
          >
            ·
          </span>
          <span
            className="text-[10px]"
            style={{ color: "rgba(255, 255, 255, 0.46)" }}
          >
            {functionLabel}
          </span>
        </div>

        {/* User name + avatar — clickable to Account page */}
        <button
          onClick={() => navigate("/account")}
          title="Account & Security"
          className="flex items-center gap-2 mr-2 px-2 py-1 rounded-lg transition-colors hover:bg-white/10"
        >
          <span
            className="text-xs"
            style={{ color: "rgba(255, 255, 255, 0.72)" }}
          >
            {role.user_name}
          </span>
          <div className="flex-shrink-0">
            {showLogo ? (
              <img
                src={role.company_logo_url}
                alt={role.company_name}
                onError={() => setLogoError(true)}
                className="w-8 h-8 rounded-lg object-contain border"
                style={{
                  background: "rgba(255,255,255,0.96)",
                  borderColor: "rgba(255,255,255,0.12)",
                }}
              />
            ) : (
              <div
                title={role.company_name}
                className="w-8 h-8 rounded-lg border
                           flex items-center justify-center
                           text-xs font-semibold"
                style={{
                  background: "rgba(255,255,255,0.08)",
                  borderColor: "rgba(255,255,255,0.14)",
                  color: "rgba(255,255,255,0.72)",
                }}
              >
                {companyInitial}
              </div>
            )}
          </div>
        </button>

        {/* CISO admin — always visible, amber when locked, indigo when authed */}
        <div className="relative mr-1">
          <button
            onClick={handleCISOClick}
            title={
              cisoAuthed
                ? "CISO Admin — authenticated"
                : "CISO Administration (password required)"
            }
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold border transition-colors"
            style={
              cisoAuthed
                ? {
                    borderColor: "rgba(113, 194, 216, 0.28)",
                    background: "rgba(113, 194, 216, 0.12)",
                    color: "#d9f1f8",
                  }
                : {
                    borderColor: "rgba(211, 182, 119, 0.24)",
                    background: "rgba(211, 182, 119, 0.1)",
                    color: "#ead8b4",
                  }
            }
          >
            <Settings className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">CISO</span>
            {cisoAuthed && (
              <span className="w-1.5 h-1.5 rounded-full bg-slate-500" />
            )}
          </button>

          {/* CISO dropdown when authed */}
          {openTab === "ciso" && cisoAuthed && (
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
        {sessionTier === "authenticated" && (
          <button
            onClick={handleLogout}
            title="Sign out"
            className="p-2 rounded-lg transition-colors"
            style={{ color: "rgba(255, 255, 255, 0.52)" }}
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
          setOpenTab("ciso");
        }}
      />
    </>
  );
}
