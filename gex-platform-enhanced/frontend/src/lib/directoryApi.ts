// Screen: API client (no screen)
//
// Staff directory — teams, roles, members, permission gates and who holds
// which gate, from GET /api/v1/directory/*.
//
// These five collections used to be read straight out of Supabase by
// `useTeamData`, under the anon key baked into the shipped bundle. Measured
// 2026-09-19: all five answered an unauthenticated request. They now come from
// the backend, which requires a bearer token.
//
// ACCESS: GEX staff only. A user of a paying customer may not read GEX's
// internal directory in any instance — not the names, not the teams, not the
// gates — so the server answers them 403. That is not an error condition for
// the UI: the caller simply has no directory, and a screen that offers
// @mentions shows none. `forbidden` carries that distinction so a refusal is
// never rendered as "something went wrong".
//
// `email` and `phone` are OPTIONAL on purpose. The server omits them — omits,
// not nulls — for a reader without staff rights, so the type says `?` and
// every consumer must decide what to show when they are absent. A required
// field here would compile, then render "undefined" to whoever may not see it.
import { getAuthToken } from '@/lib/authToken'

const API_PREFIX = '/api/v1/directory'

export interface TeamRow {
  id: string
  name: string
  description: string
  primary_modules: string
}

export interface RoleRow {
  id: string
  role_code: string
  role_name: string
  permission_tier: string
  is_default_admin: boolean
  team_id: string
}

export interface TeamUserRow {
  id: string
  full_name: string
  organisation: string | null
  status: string
  primary_team_id: string
  primary_role_id: string
  secondary_team_id: string | null
  secondary_role_id: string | null
  /** Staff-only. Absent — not null — for everyone else. */
  email?: string
  /** Staff-only. Absent — not null — for everyone else. */
  phone?: string
}

export interface PermissionGate {
  id: string
  gate_name: string
  trigger_description: string
}

export interface GateStatusRow {
  user_id: string
  gate_id: string
  status: string
}

export interface DirectoryOverview {
  teams: TeamRow[]
  roles: RoleRow[]
  members: TeamUserRow[]
  gates: PermissionGate[]
  gate_statuses: GateStatusRow[]
  /** Whether this caller was served `email`/`phone`. */
  personal_data_included: boolean
  /** True when the server refused: this caller is not GEX staff. */
  forbidden?: boolean
}

/** What a caller with no right to the directory sees. Not an error state. */
export const NO_DIRECTORY: DirectoryOverview = {
  teams: [], roles: [], members: [], gates: [], gate_statuses: [],
  personal_data_included: false, forbidden: true,
}

class DirectoryForbidden extends Error {}

async function get<T>(path: string): Promise<T> {
  const token = getAuthToken()
  const res = await fetch(`${API_PREFIX}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  })
  // 403 is a decision, not a failure. 401 is a dead session, which the auth
  // bridge handles globally — neither should be retried here.
  if (res.status === 403) throw new DirectoryForbidden()
  if (!res.ok) throw new Error(`directory: HTTP ${res.status}`)
  return (await res.json()) as T
}

export async function fetchDirectoryOverview(): Promise<DirectoryOverview> {
  try {
    return await get<DirectoryOverview>('/overview')
  } catch (e) {
    if (e instanceof DirectoryForbidden) return NO_DIRECTORY
    throw e
  }
}

export async function fetchDirectoryMembers(): Promise<TeamUserRow[]> {
  try {
    return await get<TeamUserRow[]>('/members')
  } catch (e) {
    if (e instanceof DirectoryForbidden) return []
    throw e
  }
}

export async function fetchDirectoryGateStatus(): Promise<GateStatusRow[]> {
  try {
    return await get<GateStatusRow[]>('/gate-status')
  } catch (e) {
    if (e instanceof DirectoryForbidden) return []
    throw e
  }
}
