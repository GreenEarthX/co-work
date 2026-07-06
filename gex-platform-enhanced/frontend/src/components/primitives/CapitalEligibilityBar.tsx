// Primitive E.2 — Capital Eligibility Bar
// Doctrine: capital is released because a condition has been met, not because a project exists.
// Spec: GEX_v4.1_Working_Document.docx Appendix E §E.2

export type CapitalType = 'EQUITY' | 'GRANT' | 'BRIDGE' | 'CONCESSIONAL' | 'SENIOR_DEBT' | 'ECA'
export type CommitmentStatus = 'NONE' | 'INDICATIVE' | 'TERM_SHEET' | 'CREDIT_APPROVED' | 'LEGAL_COMPLETE' | 'DRAWN'

export interface CapitalTranche {
  type: CapitalType
  label: string
  amount_total: number      // EUR
  amount_committed: number  // committed but not drawn
  amount_drawn: number
  eligible: boolean         // gate passed
  commitment_status: CommitmentStatus
}

interface CapitalEligibilityBarProps {
  tranches: CapitalTranche[]
  currentPhase?: string
  showLegend?: boolean
  className?: string
}

// One distinct hue per capital type — categorical colour variable
const TYPE_COLOR: Record<CapitalType, { solid: string; light: string; outline: string; label: string }> = {
  EQUITY:      { solid: '#0ea5a0', light: '#ccfbf1', outline: '#0ea5a0', label: 'Equity' },
  GRANT:       { solid: '#16a34a', light: '#dcfce7', outline: '#16a34a', label: 'Grant' },
  BRIDGE:      { solid: '#d97706', light: '#fef3c7', outline: '#d97706', label: 'Bridge' },
  CONCESSIONAL:{ solid: '#7c3aed', light: '#ede9fe', outline: '#7c3aed', label: 'Concessional' },
  SENIOR_DEBT: { solid: '#1e3a8a', light: '#dbeafe', outline: '#1e3a8a', label: 'Senior Debt' },
  ECA:         { solid: '#475569', light: '#f1f5f9', outline: '#475569', label: 'ECA' },
}

// Map CommitmentStatus → drawn / committed fractions
function toFractions(t: CapitalTranche): { drawn: number; committed: number; eligible: number } {
  if (!t.eligible || t.amount_total === 0) return { drawn: 0, committed: 0, eligible: 0 }
  const total = t.amount_total
  const drawn     = Math.min(1, t.amount_drawn / total)
  const committed = Math.min(1 - drawn, t.amount_committed / total)
  const eligible  = 1 - drawn - committed
  return { drawn, committed, eligible }
}

// SVG diagonal hatch pattern id per type
function hatchId(type: CapitalType) { return `hatch-${type.toLowerCase()}` }

export function CapitalEligibilityBar({
  tranches,
  currentPhase,
  showLegend = true,
  className = '',
}: CapitalEligibilityBarProps) {
  const totalAmount = tranches.reduce((s, t) => s + t.amount_total, 0)
  if (totalAmount === 0) return null

  const BAR_H = 14
  const W = 600
  const LABEL_H = 16

  // Build segment rects
  let cursor = 0
  const segments = tranches.map(t => {
    const w = (t.amount_total / totalAmount) * W
    const x = cursor
    cursor += w
    const frac = toFractions(t)
    const col = TYPE_COLOR[t.type]
    return { t, x, w, frac, col }
  })

  return (
    <div className={`w-full ${className}`}>
      <svg width="100%" viewBox={`0 0 ${W} ${BAR_H + LABEL_H + 4}`} preserveAspectRatio="none" className="overflow-visible">
        <defs>
          {tranches.map(t => (
            <pattern key={t.type} id={hatchId(t.type)} width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="4" stroke={TYPE_COLOR[t.type].solid} strokeWidth="1.5" strokeOpacity="0.55" />
            </pattern>
          ))}
        </defs>

        {segments.map(({ t, x, w, frac, col }) => {
          if (!t.eligible) {
            // Not eligible: grey outline only
            return (
              <g key={t.type}>
                <rect x={x + 1} y={0} width={w - 2} height={BAR_H} fill="transparent" stroke="#cbd5e1" strokeWidth="1" rx="1" />
              </g>
            )
          }
          const drawnW    = frac.drawn * w
          const committedW = frac.committed * w
          const eligibleW  = frac.eligible * w
          return (
            <g key={t.type}>
              {/* eligible (very light) */}
              {eligibleW > 0 && (
                <rect x={x} y={0} width={drawnW + committedW + eligibleW} height={BAR_H} fill={col.light} rx="1" />
              )}
              {/* committed (hatched) */}
              {committedW > 0 && (
                <rect x={x + drawnW} y={0} width={committedW} height={BAR_H} fill={`url(#${hatchId(t.type)})`} />
              )}
              {/* drawn (solid) */}
              {drawnW > 0 && (
                <rect x={x} y={0} width={drawnW} height={BAR_H} fill={col.solid} rx="1" />
              )}
              {/* segment border */}
              <rect x={x + 0.5} y={0.5} width={w - 1} height={BAR_H - 1} fill="none" stroke={col.outline} strokeWidth="0.75" strokeOpacity="0.4" rx="1" />
              {/* type label below bar */}
              <text x={x + w / 2} y={BAR_H + LABEL_H - 2} textAnchor="middle" fontSize={8} fill={col.solid} fontWeight={600} className="font-mono uppercase">
                {col.label}
              </text>
            </g>
          )
        })}
      </svg>

      {showLegend && (
        <div className="flex items-center gap-4 mt-1 flex-wrap">
          <div className="flex items-center gap-1 text-[10px] text-gray-500">
            <div className="w-6 h-2 rounded-sm" style={{ background: '#0ea5a0' }} />
            <span>Drawn</span>
          </div>
          <div className="flex items-center gap-1 text-[10px] text-gray-500">
            <div className="w-6 h-2 rounded-sm" style={{ background: 'repeating-linear-gradient(45deg, #64748b 0px, #64748b 1px, transparent 1px, transparent 3px)' }} />
            <span>Committed</span>
          </div>
          <div className="flex items-center gap-1 text-[10px] text-gray-500">
            <div className="w-6 h-2 rounded-sm bg-gray-100 border border-gray-300" />
            <span>Eligible</span>
          </div>
          <div className="flex items-center gap-1 text-[10px] text-gray-500">
            <div className="w-6 h-2 rounded-sm border border-slate-300" />
            <span>Gate not passed</span>
          </div>
          {currentPhase && (
            <span className="ml-auto text-[10px] text-gray-400 font-medium">Phase: {currentPhase}</span>
          )}
        </div>
      )}
    </div>
  )
}

// Helper: build CapitalTranche[] from CustomerProject bankability.capital_status
import type { CustomerProject } from '@/data/customerProjects'

const STATUS_TO_DRAWN: Record<string, number> = {
  NONE: 0, INDICATIVE: 0, TERM_SHEET: 0, CREDIT_APPROVED: 0, LEGAL_COMPLETE: 0, DRAWN: 1,
}
const STATUS_TO_COMMITTED: Record<string, number> = {
  NONE: 0, INDICATIVE: 0.2, TERM_SHEET: 0.6, CREDIT_APPROVED: 0.8, LEGAL_COMPLETE: 0.9, DRAWN: 0,
}
// Visual-category mapping: backend canonical CapitalType  →  bar-colour band.
// Keys MUST match backend bankability_engine.CapitalType enum members so the
// fallback render stays consistent with live data.  ECA is a seed-data
// extension (no backend CapitalType.ECA — represented as actor type only).
const LABEL_TO_TYPE: Record<string, CapitalType> = {
  // Backend canonical members
  GRANTS_TA:              'GRANT',
  SEED_VC_ANGEL:          'EQUITY',
  STRATEGIC_EQUITY:       'EQUITY',
  PROJECT_EQUITY:         'EQUITY',
  DFI_MEZZ_GUARANTEES:    'CONCESSIONAL',
  SENIOR_DEBT_COMMITMENT: 'SENIOR_DEBT',
  DEBT_DRAWDOWN:          'SENIOR_DEBT',
  REFINANCE_BONDS_INFRA:  'SENIOR_DEBT',
  // Seed-data extensions (no backend enum equivalent)
  ECA:                    'ECA',
  BRIDGE_CAPITAL:         'BRIDGE',
  CONCESSIONAL:           'CONCESSIONAL',
}

export function tranchesFromProject(project: CustomerProject, gatesPassed: string[]): CapitalTranche[] {
  return project.bankability.capital_status.map(c => {
    const type: CapitalType = LABEL_TO_TYPE[c.type] ?? 'EQUITY'
    const amountM = parseFloat(c.amount.replace(/[^0-9.]/g, '')) || 10
    const total = amountM * 1_000_000
    const drawnFrac     = STATUS_TO_DRAWN[c.commitment_status] ?? 0
    const committedFrac = STATUS_TO_COMMITTED[c.commitment_status] ?? 0
    const eligible = c.is_unlocked || c.gating_gates.every(g => gatesPassed.includes(g))
    return {
      type,
      label: c.name,
      amount_total:     total,
      amount_drawn:     total * drawnFrac,
      amount_committed: total * committedFrac,
      eligible,
      commitment_status: c.commitment_status as CommitmentStatus,
    }
  })
}
