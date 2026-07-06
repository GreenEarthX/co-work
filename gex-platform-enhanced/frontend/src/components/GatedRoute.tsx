// Screen: Shared component — Route wrapper for gate-locked screens
/**
 * GatedRoute — route-level workflow enforcement.
 *
 * Drop-in replacement for raw <Route element={...} /> that automatically
 * wraps the element in a GateLock using the route's path.
 *
 * Usage in App.tsx:
 *   <Route path="capital-stack" element={<GatedRoute path="/capital-stack"><CapitalStack /></GatedRoute>} />
 */

import { GateLock } from '@/components/GateLock'

interface GatedRouteProps {
  path: string
  children: React.ReactNode
}

export function GatedRoute({ path, children }: GatedRouteProps) {
  return <GateLock path={path}>{children}</GateLock>
}
