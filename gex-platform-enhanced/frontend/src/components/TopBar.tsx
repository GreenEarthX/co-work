// Screen: Shared layout component — all authenticated screens
import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Settings, LogOut } from "lucide-react";
import {
  MENU_TABS,
  CISO_ITEMS,
  isVisibleInNav,
} from "@/config/menuArchitecture";
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

  // Identity banner: job title, falling back to the business function
  const userTitle =
    role.user_title ??
    functionLabel.toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());

  // Company logo: URL if set and not broken, else initial letter
  const showLogo = !!role.company_logo_url && !logoError;
  const companyInitial = (role.company_name ?? "G").charAt(0).toUpperCase();

  return (
    <>
      <div className="sticky top-0 z-40">
        {/* ── Row 1: identity banner — company · user · GEX logo ── */}
        <div
          className="h-16 border-b flex items-center px-6 gap-4"
          style={{
            background: "#EFEFE8",
            borderColor: "rgba(0, 0, 0, 0.10)",
          }}
        >
          {/* Company name */}
          <span
            className="text-xl sm:text-2xl uppercase tracking-[0.06em] font-medium flex-shrink-0"
            style={{ color: "#14524A" }}
          >
            {role.company_name}
          </span>

          {/* Divider */}
          <span
            className="h-8 w-px flex-shrink-0"
            style={{ background: "rgba(0, 0, 0, 0.28)" }}
          />

          {/* User name + title */}
          <div className="flex flex-col leading-tight min-w-0">
            <span
              className="text-sm sm:text-base font-semibold truncate"
              style={{ color: "#1a1a1a" }}
            >
              {role.user_name}
            </span>
            <span
              className="text-xs sm:text-sm truncate"
              style={{ color: "#3d3d3d" }}
            >
              {userTitle}
            </span>
          </div>

          <div className="flex-1" />

          {/* GEX platform logo */}
          <button
            onClick={() => navigate("/dashboard")}
            title="GreenEarthXchange — dashboard"
            className="flex-shrink-0 px-1 py-1"
          >
            <img
              src="/GreenEarthX-updated.png"
              alt="GreenEarthX"
              className="h-10 w-auto object-contain sm:h-11"
            />
          </button>
        </div>

        {/* ── Row 2: navigation ── */}
        <div
          data-topbar
          className="h-20 border-b flex items-center px-6 gap-0"
          style={{
            background:
              "linear-gradient(90deg, #005B4C 0%, #004A55 55%, #003A52 100%)",
            borderColor: "rgba(255, 255, 255, 0.08)",
          }}
        >
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

          {/* Company avatar — clickable to Account page.
              User name lives in the identity banner above. */}
          <button
            onClick={() => navigate("/account")}
            title="Account & Security"
            className="flex items-center mr-2 px-2 py-1 rounded-lg transition-colors hover:bg-white/10"
          >
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
