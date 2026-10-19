// Gate display names, keyed by short id ("G0" … "G11").
// Held identical to the gate engine (backend/app/core/bankability_engine.py,
// rules 4.1.0). Used where a screen must name a gate the current persona's
// engine response does not include (for example, a gate that gates a capital
// tranche but sits outside the viewer's gate scope).
import { gateShortId } from '@/lib/engineReadout'

export const GATE_NAMES: Record<string, string> = {
  G0: 'Site Rights & Social License',
  G1: 'Power, Utilities & Technology Basis',
  G2: 'Green Certification Pathway',
  G3: 'Feedstock & Logistics Terms',
  G4: 'Binding Offtake',
  G5: 'EPC Risk Priced',
  G6: 'Independent Engineer Sign-off',
  G7: 'Insurability Confirmed',
  G8: 'Audit-Grade Financial Model',
  G9: 'Permits Granted & Appeal Risk Managed',
  G10: 'Financial Close',
  G11: 'COD & Stabilization',
}

/** "G0_SITE_RIGHTS" → "G0 Site Rights & Social License" (falls back to the id). */
export function gateLabel(gateId: string): string {
  const short = gateShortId(gateId)
  const name = GATE_NAMES[short]
  return name ? `${short} ${name}` : gateId
}
