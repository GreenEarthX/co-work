// Screen: Shared library (no screen)
/**
 * resolveActionRoute — the ONE place that decides where a claim/blocker/risk
 * sends a user. Screens describe the action; this resolver decides the route.
 *
 * Why this exists: F1–F5 were not five bugs, they were one missing abstraction
 * showing five symptoms — route decisions smeared across enginePersona,
 * canEnterRoute, riskCategoryWay, roleNextActionRoute, EVIDENCE_META.route and
 * GateLock. Centralising them here kills the whole class: a screen can no
 * longer "correctly detect a problem then send the user to the wrong/locked
 * place", because it no longer chooses the place.
 *
 * DERIVE, don't enumerate. The resolver does NOT hold a (action × role) matrix
 * (that rots like the static registry did). It takes the action's preferred
 * destination + owner + optional fallback, and derives status from the route
 * guard table via canEnterRoute (the permission primitive).
 *
 * Migration is strangler-pattern: call-sites delegate here one at a time.
 * audit-causal-ways.mjs proves each migration by showing the call-site's edges
 * flow through the resolver and its guarded targets become resolver-handled.
 */

import { canEnterRoute, resolveEvidenceRoute } from '@/data/evidenceCatalog'

export interface RouteUser {
  business_function: string
  service_type?: string | null
  company_type?: string
}

export interface RouteAction {
  /** Stable id for the kind of action — telemetry/audit, e.g. "evidence:ppa_register". */
  kind: string
  /** Where the OWNER works this. May contain {project_id}. */
  preferred_route?: string
  /** Who owns the work — surfaced when the viewer cannot act. */
  owner_function?: string
  /** Universal surface any authorised viewer can reach when the preferred
   *  route is not enterable (e.g. a read-only scoreboard). May contain {project_id}. */
  fallback_route?: string
}

export type RouteStatus =
  | 'allowed'    // viewer can enter the preferred route — act directly
  | 'fallback'   // preferred not enterable; routed to a reachable fallback
  | 'forbidden'  // no enterable destination — read-only; owner named

export interface ResolvedRoute {
  status: RouteStatus
  /** Concrete, param-substituted path — or null when read-only. */
  route: string | null
  /** Human reason, e.g. "worked by FINANCE_TREASURY". */
  reason?: string
  owner_function?: string
}

export function resolveActionRoute(
  user: RouteUser,
  action: RouteAction,
  projectId: string,
): ResolvedRoute {
  const preferred = resolveEvidenceRoute(action.preferred_route, projectId)

  // 1. Preferred route the viewer is permitted to enter → act directly.
  if (preferred && canEnterRoute(action.preferred_route, user)) {
    return { status: 'allowed', route: preferred }
  }

  // 2. Preferred exists but the viewer cannot enter it → a reachable fallback,
  //    if one is declared and enterable. Name the owner so the viewer knows
  //    who acts on the preferred surface.
  const fallback = resolveEvidenceRoute(action.fallback_route, projectId)
  if (fallback && canEnterRoute(action.fallback_route, user)) {
    return {
      status: 'fallback',
      route: fallback,
      reason: action.owner_function ? `worked by ${action.owner_function}` : undefined,
      owner_function: action.owner_function,
    }
  }

  // 3. Nothing the viewer can enter → read-only. Never hand back a route the
  //    viewer will bounce off (the F4 "you told me to work this then sent me
  //    to a locked/forbidden page" failure).
  return {
    status: 'forbidden',
    route: null,
    reason: action.owner_function ? `worked by ${action.owner_function}` : 'no accessible route',
    owner_function: action.owner_function,
  }
}
