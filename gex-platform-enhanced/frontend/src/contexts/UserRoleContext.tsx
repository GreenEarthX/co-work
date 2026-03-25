import React, { createContext, useContext, useState, ReactNode } from 'react';

export type CompanyType = 'PRODUCER' | 'OFFTAKER' | 'THIRD_PARTY';
export type ServiceType = 'BANK' | 'INSURER' | 'CERTIFIER' | 'LOGISTICS' | 'ENGINEER' | 'EQUIPMENT' | 'LEGAL' | null;
export type BusinessFunction = 'ENGINEERING' | 'FINANCE_TREASURY' | 'COMMERCIAL' | 'COMPLIANCE_LEGAL' | 'OPERATIONS' | 'EXECUTIVE';

export interface UserRole {
  company_type: CompanyType;
  service_type: ServiceType;
  business_function: BusinessFunction;
  company_name: string;
  user_name: string;
}

interface UserRoleContextType {
  role: UserRole;
  setRole: (role: UserRole) => void;
  isRoleSet: boolean;
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
});

export function UserRoleProvider({ children }: { children: ReactNode }) {
  const [role, setRoleState] = useState<UserRole>(() => {
    const saved = localStorage.getItem('gex_user_role');
    if (saved) {
      try { return JSON.parse(saved); } catch { /* fall through */ }
    }
    return DEFAULT_ROLE;
  });
  const [isRoleSet, setIsRoleSet] = useState(() => !!localStorage.getItem('gex_user_role'));

  const setRole = (newRole: UserRole) => {
    setRoleState(newRole);
    setIsRoleSet(true);
    localStorage.setItem('gex_user_role', JSON.stringify(newRole));
  };

  return (
    <UserRoleContext.Provider value={{ role, setRole, isRoleSet }}>
      {children}
    </UserRoleContext.Provider>
  );
}

export function useUserRole() {
  return useContext(UserRoleContext);
}

export default UserRoleContext;
