/**
 * AuthContext stub — replaces Lovable's Supabase-backed auth.
 * GEX uses UserRoleContext for role state and kycState for KYC.
 * Canvas code imports useAuth() for user identity; we return a
 * static demo user so components render without Supabase.
 */
import { createContext, useContext } from 'react'

export interface AuthUser {
  id: string
  email: string
  name?: string
  company?: string
  provider?: string
  user_metadata?: Record<string, unknown>
}

interface AuthContextValue {
  user: AuthUser | null
  session: unknown
  loading: boolean
  isAuthenticated: boolean
  signOut: () => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue>({
  user: { id: 'demo-user', email: 'demo@greenearthx.com', name: 'Demo User', company: 'GreenEarthX' },
  session: null,
  loading: false,
  isAuthenticated: true,
  signOut: async () => {},
  logout: async () => {},
})

export function useAuth(): AuthContextValue {
  return useContext(AuthContext)
}

export default AuthContext
