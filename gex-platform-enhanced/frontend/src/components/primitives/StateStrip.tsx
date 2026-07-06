// Primitive E.1 — State Strip
// Doctrine: every artefact carries a verification state and is non-negotiable on every view.
// Spec: GEX_v4.1_Working_Document.docx Appendix E §E.1

export type VerificationState = 'UNVERIFIED' | 'SUBMITTED' | 'CONFIRMED' | 'AUDITED'

// Named state machines per layer
export const BRIDGE_STATES = [
  'identified', 'scoped', 'costed', 'evidenced', 'eligible',
  'approved', 'committed', 'drawable', 'drawn', 'closed',
] as const

export const TOKEN_STATES = [
  'minted', 'reserved', 'matched', 'settled', 'retired', 'voided',
] as const

export const TRADING_STATES = [
  'draft', 'open', 'reserved', 'matched', 'settled', 'expired',
] as const

interface StateStripProps {
  states: readonly string[]
  activeState: string
  verificationState?: VerificationState
  compact?: boolean
  className?: string
}

function VerificationIcon({ state }: { state: VerificationState }) {
  const base = 'w-3 h-3 rounded-full border flex items-center justify-center text-[7px] leading-none'
  if (state === 'UNVERIFIED') return (
    <div className={`${base} border-slate-300 bg-white`} title="Unverified" />
  )
  if (state === 'SUBMITTED') return (
    <div className={`${base} border-amber-400 bg-amber-50`} title="Submitted">
      <div className="w-1.5 h-1.5 rounded-full bg-amber-400" />
    </div>
  )
  if (state === 'CONFIRMED') return (
    <div className={`${base} border-teal-500 bg-teal-500`} title="Confirmed" />
  )
  // AUDITED
  return (
    <div className={`${base} border-teal-700 bg-teal-700 text-white font-bold`} title="Audited">★</div>
  )
}

export function StateStrip({
  states,
  activeState,
  verificationState = 'UNVERIFIED',
  compact = false,
  className = '',
}: StateStripProps) {
  const activeIdx = states.indexOf(activeState)

  return (
    <div className={`flex items-center gap-0 overflow-x-auto ${className}`}>
      {states.map((state, i) => {
        const isActive    = i === activeIdx
        const isCompleted = i < activeIdx
        // isFuture = i > activeIdx

        const nodeCls = compact
          ? 'px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wide whitespace-nowrap'
          : 'px-2 py-1 rounded text-[10px] font-bold uppercase tracking-wide whitespace-nowrap'

        const colorCls = isActive
          ? 'bg-[#0ea5a0] text-white'
          : isCompleted
          ? 'bg-teal-100 text-teal-700'
          : 'bg-white text-slate-400 border border-slate-200'

        return (
          <div key={state} className="flex items-center">
            <div className="relative flex flex-col items-center">
              <div className={`${nodeCls} ${colorCls}`}>{state}</div>
              {isActive && (
                <div className="absolute -bottom-4">
                  <VerificationIcon state={verificationState} />
                </div>
              )}
            </div>
            {i < states.length - 1 && (
              <div className={`mx-0.5 text-[10px] ${isCompleted ? 'text-teal-400' : 'text-slate-200'}`}>›</div>
            )}
          </div>
        )
      })}
    </div>
  )
}
