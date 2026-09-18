// Guard: redirect unauthenticated users away from protected routes
import React, { useEffect } from 'react'
import { Navigate } from 'react-router-dom'
import { useUserRole } from '@/contexts/UserRoleContext'
import { isAuthenticated } from '@/lib/authToken'
import { expireSession } from '@/lib/sessionGuard'

/**
 * Renders children only for a signed-in user whose token is still valid.
 *
 * sessionTier alone is not enough: it is set at login and outlives the
 * 30-minute access token, which is how a tab left open kept rendering
 * signed-in pages while every API call 401'd (HANDOFF §8.11).
 */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { sessionTier } = useUserRole()
  const expired = sessionTier === 'authenticated' && !isAuthenticated()

  useEffect(() => {
    if (expired) expireSession()
  }, [expired])

  if (sessionTier !== 'authenticated') {
    return <Navigate to="/login" replace />
  }
  // expireSession reloads onto /login so every UserRoleContext consumer
  // restarts signed out; render nothing until it does.
  if (expired) return null
  return <>{children}</>
}
