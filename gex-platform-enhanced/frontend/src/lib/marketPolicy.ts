/**
 * What the signed-in user may do in the market (decision D-B, JML 2026-11-14).
 *
 * The rule lives in ONE place, the backend's core/market_policy.py: Commercial lists supply,
 * raises RFQs, enquires and makes or accepts proposals; the CEO and the CFO approve trade
 * confirmations; Engineering and Operations read. Screens ask GET /api/v1/market/policy and show
 * only the actions the server would accept, so a button never leads to a refusal.
 */
import { useEffect, useState } from 'react'

import { marketAPI } from '@/api'

export type MarketAction =
  | 'capacity.create' | 'token.mint' | 'listing.create' | 'listing.open' | 'listing.withdraw'
  | 'rfq.create' | 'rfq.change' | 'enquiry.send' | 'enquiry.reply'
  | 'proposal.create' | 'proposal.accept' | 'proposal.decline'
  | 'trade.confirm.request' | 'trade.confirm.approve' | 'product.declare'

let cached: Promise<Set<string>> | null = null

/** Forget the cached policy (sign-in and sign-out change who is asking). */
export function resetMarketPolicy(): void {
  cached = null
}

export function useMarketPolicy(): { ready: boolean; can: (action: MarketAction) => boolean } {
  const [allowed, setAllowed] = useState<Set<string> | null>(null)
  useEffect(() => {
    let live = true
    cached = cached ?? marketAPI.policy().then(p => new Set(p.allowed)).catch(() => new Set<string>())
    cached.then(s => { if (live) setAllowed(s) })
    return () => { live = false }
  }, [])
  // Until the server answers, nothing is offered: never a button the server would refuse.
  return { ready: allowed !== null, can: (a: MarketAction) => !!allowed?.has(a) }
}
