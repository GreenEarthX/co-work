/**
 * VerificationBadge — R0 (Architectural Reform v6.0)
 *
 * Compact badge showing verification state with colour coding.
 * Placed on EVERY evidence row in: Stage Gates, Data Room, IC Pack,
 * Offtake Quality, Capital Stack tranches, and Marketplace offers.
 *
 * UNVERIFIED  → gray   — "Unverified"
 * SUBMITTED   → amber  — "Submitted"
 * CONFIRMED   → blue   — "Confirmed · [Firm]"
 * AUDITED     → green  — "Audited · [Firm] Ref: [ref]"
 */

import { ShieldAlert, ShieldCheck, ShieldQuestion, ShieldOff } from 'lucide-react'

// ─── Types ────────────────────────────────────────────────────────────────────

export type VerificationState = 'UNVERIFIED' | 'SUBMITTED' | 'CONFIRMED' | 'AUDITED'

export interface VerificationBadgeProps {
  state: VerificationState
  verifierFirm?: string
  verifierReference?: string
  verifierDate?: string
  /** compact: icon only (for table cells). default: full label */
  compact?: boolean
}

// ─── Config ───────────────────────────────────────────────────────────────────

const CONFIG: Record<
  VerificationState,
  { label: string; bg: string; text: string; border: string; Icon: React.ElementType }
> = {
  UNVERIFIED: {
    label:  'Unverified',
    bg:     'bg-gray-100',
    text:   'text-gray-600',
    border: 'border-gray-300',
    Icon:   ShieldOff,
  },
  SUBMITTED: {
    label:  'Submitted',
    bg:     'bg-amber-50',
    text:   'text-amber-700',
    border: 'border-amber-300',
    Icon:   ShieldQuestion,
  },
  CONFIRMED: {
    label:  'Confirmed',
    bg:     'bg-blue-50',
    text:   'text-blue-700',
    border: 'border-blue-300',
    Icon:   ShieldCheck,
  },
  AUDITED: {
    label:  'Audited',
    bg:     'bg-green-50',
    text:   'text-green-700',
    border: 'border-green-300',
    Icon:   ShieldCheck,
  },
}

// ─── Component ────────────────────────────────────────────────────────────────

export function VerificationBadge({
  state,
  verifierFirm,
  verifierReference,
  verifierDate,
  compact = false,
}: VerificationBadgeProps) {
  const { label, bg, text, border, Icon } = CONFIG[state]

  const dateStr = verifierDate
    ? new Date(verifierDate).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
    : null

  if (compact) {
    return (
      <span
        title={buildTitle(state, verifierFirm, verifierReference, dateStr)}
        className={`inline-flex items-center justify-center w-5 h-5 rounded-full border ${bg} ${border} ${text}`}
      >
        <Icon className="w-3 h-3" />
      </span>
    )
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-xs font-medium ${bg} ${border} ${text}`}
    >
      <Icon className="w-3 h-3 flex-shrink-0" />
      <span>{label}</span>

      {/* Firm name — shown for CONFIRMED and AUDITED */}
      {(state === 'CONFIRMED' || state === 'AUDITED') && verifierFirm && (
        <span className="opacity-75">· {verifierFirm}</span>
      )}

      {/* Reference — shown for AUDITED only */}
      {state === 'AUDITED' && verifierReference && (
        <span className="opacity-75">Ref: {verifierReference}</span>
      )}
    </span>
  )
}

// ─── Weight indicator (secondary display) ────────────────────────────────────

const WEIGHTS: Record<VerificationState, number> = {
  UNVERIFIED: 0.25,
  SUBMITTED:  0.50,
  CONFIRMED:  0.85,
  AUDITED:    1.00,
}

export function VerificationWeight({ state }: { state: VerificationState }) {
  const w = WEIGHTS[state]
  const { text } = CONFIG[state]
  return (
    <span className={`text-xs font-mono font-semibold tabular-nums ${text}`}>
      ×{w.toFixed(2)}
    </span>
  )
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function buildTitle(
  state: VerificationState,
  firm?: string,
  ref?: string,
  date?: string | null,
): string {
  const parts = [CONFIG[state].label]
  if (firm) parts.push(`by ${firm}`)
  if (ref)  parts.push(`Ref: ${ref}`)
  if (date) parts.push(`on ${date}`)
  return parts.join(' ')
}
