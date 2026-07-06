/**
 * UserContextBar — Displays current user identity.
 * Context-aware: hides project info on Ecosystem Navigator pages.
 */

import { Building2, User, LogOut, Zap, LogIn } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import InboxBell from "./InboxBell";

interface UserContextBarProps {
  onLoginClick?: () => void;
}

const UserContextBar = ({ onLoginClick }: UserContextBarProps) => {
  const { user, isAuthenticated, logout } = useAuth();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const onMap = pathname === "/" || pathname === "/news";

  if (!isAuthenticated) {
    return onLoginClick ? (
      <button
        onClick={onLoginClick}
        className="inline-flex items-center gap-2 rounded-md bg-white/10 px-4 py-2 text-xs font-medium text-white/80 hover:bg-white/20 transition-colors"
      >
        <LogIn className="h-3.5 w-3.5" /> Sign In
      </button>
    ) : null;
  }

  return (
    <div className="flex items-center gap-3">
      {user?.provider === "demo" && (
        <span className="inline-flex items-center gap-1 rounded-full bg-warning/20 border border-warning/40 px-2 py-0.5 text-[9px] font-bold text-warning uppercase tracking-wider">
          <Zap className="h-2.5 w-2.5" /> Demo
        </span>
      )}

      {!onMap && user?.company && (
        <div className="flex items-center gap-1.5">
          <Building2 className="h-3 w-3 text-white/50" />
          <span className="text-[11px] text-white/80">{user.company}</span>
        </div>
      )}

      <div className="h-4 w-px bg-white/20" />

      <InboxBell />

      <button
        onClick={logout}
        className="inline-flex items-center gap-1.5 rounded-md bg-white/10 px-2.5 py-1.5 text-[11px] text-white/70 hover:bg-white/20 transition-colors"
      >
        <LogOut className="h-3 w-3" /> Sign Out
      </button>

      <button
        onClick={() => navigate("/profile")}
        className="h-7 w-7 rounded-full bg-white/15 flex items-center justify-center hover:bg-white/25 transition-colors cursor-pointer"
        title="View profile"
      >
        <User className="h-3.5 w-3.5 text-white/70" />
      </button>
    </div>
  );
};

export default UserContextBar;
