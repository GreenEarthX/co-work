import React, { createContext, useContext, useState, ReactNode } from 'react';

export type CompanyType = 'PRODUCER' | 'OFFTAKER' | 'THIRD_PARTY';
export type ServiceType = 'BANK' | 'INSURER' | 'CERTIFIER' | 'LOGISTICS' | 'ENGINEER' | 'EQUIPMENT' | 'LEGAL' | null;
export type BusinessFunction = 'ENGINEERING' | 'FINANCE_TREASURY' | 'COMMERCIAL' | 'COMPLIANCE_LEGAL' | 'OPERATIONS' | 'EXECUTIVE';

// Session tiers
// 'guest'         — unauthenticated prospect, PUBLIC data only
// 'authenticated' — logged-in user with full role
export type SessionTier = 'guest' | 'authenticated';

export interface UserRole {
  company_type: CompanyType;
  service_type: ServiceType;
  business_function: BusinessFunction;
  company_name: string;
  user_name: string;
  /** Optional URL for the company logo shown in TopBar */
  company_logo_url?: string;
}

export interface AuthSession {
  /** JWT token — sent as Authorization header on API calls */
  token: string;
  /** User e-mail used to log in */
  email: string;
}

interface UserRoleContextType {
  role: UserRole;
  setRole: (role: UserRole) => void;
  isRoleSet: boolean;

  /** 'guest' until the user explicitly logs in */
  sessionTier: SessionTier;
  /** Present only when sessionTier === 'authenticated' */
  authSession: AuthSession | null;

  /** Call on successful login — sets tier to 'authenticated' */
  login: (session: AuthSession, role: UserRole) => void;
  /** Explore without logging in — sets tier to 'guest' */
  continueAsGuest: () => void;
  /** Clear session and return to login screen */
  logout: () => void;
}

const DEFAULT_ROLE: UserRole = {
  company_type: 'PRODUCER',
  service_type: null,
  business_function: 'FINANCE_TREASURY',
  company_name: 'Demo Company',
  user_name: 'Demo User',
};

const UserRoleContext = createContext<UserRoleContextType>({
  role: DEFAULT_ROLE,
  setRole: () => {},
  isRoleSet: false,
  sessionTier: 'guest',
  authSession: null,
  login: () => {},
  continueAsGuest: () => {},
  logout: () => {},
});

const STORAGE_KEY_ROLE    = 'gex_user_role';
const STORAGE_KEY_SESSION = 'gex_auth_session';
const STORAGE_KEY_TIER    = 'gex_session_tier';

export function UserRoleProvider({ children }: { children: ReactNode }) {
  const [role, setRoleState] = useState<UserRole>(() => {
    const saved = localStorage.getItem(STORAGE_KEY_ROLE);
    if (saved) {
      try { return JSON.parse(saved); } catch { /* fall through */ }
    }
    return DEFAULT_ROLE;
  });

  const [isRoleSet, setIsRoleSet] = useState(
    () => !!localStorage.getItem(STORAGE_KEY_ROLE)
  );

  const [sessionTier, setSessionTier] = useState<SessionTier>(() => {
    return (localStorage.getItem(STORAGE_KEY_TIER) as SessionTier) ?? 'guest';
  });

  const [authSession, setAuthSession] = useState<AuthSession | null>(() => {
    const saved = localStorage.getItem(STORAGE_KEY_SESSION);
    if (saved) {
      try { return JSON.parse(saved); } catch { /* fall through */ }
    }
    return null;
  });

  const setRole = (newRole: UserRole) => {
    setRoleState(newRole);
    setIsRoleSet(true);
    localStorage.setItem(STORAGE_KEY_ROLE, JSON.stringify(newRole));
  };

  const login = (session: AuthSession, newRole: UserRole) => {
    setAuthSession(session);
    setSessionTier('authenticated');
    setRole(newRole);
    localStorage.setItem(STORAGE_KEY_SESSION, JSON.stringify(session));
    localStorage.setItem(STORAGE_KEY_TIER, 'authenticated');
  };

  const continueAsGuest = () => {
    setSessionTier('guest');
    localStorage.setItem(STORAGE_KEY_TIER, 'guest');
  };

  const logout = () => {
    setAuthSession(null);
    setSessionTier('guest');
    setIsRoleSet(false);
    setRoleState(DEFAULT_ROLE);
    localStorage.removeItem(STORAGE_KEY_SESSION);
    localStorage.removeItem(STORAGE_KEY_ROLE);
    localStorage.setItem(STORAGE_KEY_TIER, 'guest');
    sessionStorage.removeItem('gex_ciso_session');
  };

  return (
    <UserRoleContext.Provider
      value={{ role, setRole, isRoleSet, sessionTier, authSession, login, continueAsGuest, logout }}
    >
      {children}
    </UserRoleContext.Provider>
  );
}

export function useUserRole() {
  return useContext(UserRoleContext);
}

export default UserRoleContext;
