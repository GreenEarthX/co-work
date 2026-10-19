// Per-company screen access rules — a client CISO's tailoring of the platform's
// default screen access (menuArchitecture.ts `visible_to` + the executive default).
//
// Rules are loaded once per signed-in company from /api/v1/ciso/screen-access and
// held in a module-level registry so that the plain `isVisible()` function — used by
// the menu, the address-bar guard and the project profile — applies them without
// every caller having to pass them in. A rule applies only to the company it was
// loaded for, so switching account never carries one company's rules to another.
import { useEffect, useState } from 'react'
import { getAuthHeader } from '@/lib/authToken'

export type ScreenRuleEffect = 'ALLOW' | 'DENY'

export interface ScreenRule {
  screen_id: string
  business_function: string
  effect: ScreenRuleEffect
  updated_by?: string | null
  updated_at?: string | null
}

let loadedFor: string | null = null
let ruleMap = new Map<string, ScreenRuleEffect>()
let version = 0
const listeners = new Set<() => void>()

const key = (screenId: string, fn: string) => `${screenId}|${fn}`

export function setScreenAccessRules(companyName: string | null, rules: ScreenRule[]): void {
  loadedFor = companyName
  ruleMap = new Map(rules.map(r => [key(r.screen_id, r.business_function), r.effect]))
  version += 1
  listeners.forEach(l => l())
}

/** The CISO rule for this screen and function in this company, if any. */
export function screenRuleFor(companyName: string, screenId: string, fn: string): ScreenRuleEffect | undefined {
  if (!loadedFor || loadedFor !== companyName) return undefined
  return ruleMap.get(key(screenId, fn))
}

export class ScreenAccessRequestError extends Error {
  constructor(message: string, public status: number) { super(message) }
}

export async function fetchScreenAccessRules(): Promise<ScreenRule[]> {
  const r = await fetch('/api/v1/ciso/screen-access', { headers: { ...getAuthHeader() } })
  if (!r.ok) throw new ScreenAccessRequestError(`Screen access rules could not be loaded (HTTP ${r.status}).`, r.status)
  const data = await r.json()
  return Array.isArray(data?.rules) ? data.rules : []
}

export async function saveScreenAccessRules(rules: ScreenRule[]): Promise<ScreenRule[]> {
  const r = await fetch('/api/v1/ciso/screen-access', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
    body: JSON.stringify({
      rules: rules.map(({ screen_id, business_function, effect }) => ({ screen_id, business_function, effect })),
    }),
  })
  const data = await r.json().catch(() => null)
  if (!r.ok) {
    const msg = r.status === 403
      ? 'Only an executive account of this company may change its screen access rules.'
      : Array.isArray(data?.detail?.problems) ? data.detail.problems.join('; ')
      : `The rules were not saved (HTTP ${r.status}).`
    throw new ScreenAccessRequestError(msg, r.status)
  }
  return Array.isArray(data?.rules) ? data.rules : []
}

/**
 * Loads the signed-in company's rules into the registry and re-renders the caller
 * when they change. `ready` turns true once loading has finished — successfully or
 * not; on failure the platform defaults apply and `error` says why.
 */
export function useScreenAccessRules(companyName: string | undefined): { ready: boolean; error: string | null; version: number } {
  const [, setTick] = useState(0)
  const [ready, setReady] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const l = () => setTick(t => t + 1)
    listeners.add(l)
    return () => { listeners.delete(l) }
  }, [])

  useEffect(() => {
    let cancelled = false
    if (!companyName) { setScreenAccessRules(null, []); setReady(true); return }
    setReady(false)
    fetchScreenAccessRules()
      .then(rules => { if (!cancelled) { setScreenAccessRules(companyName, rules); setError(null) } })
      .catch(e => {
        if (cancelled) return
        setScreenAccessRules(companyName, [])
        setError(e instanceof Error ? e.message : String(e))
        console.warn('[screenAccess] defaults apply:', e)
      })
      .finally(() => { if (!cancelled) setReady(true) })
    return () => { cancelled = true }
  }, [companyName])

  return { ready, error, version }
}
