// Primitive E.5 — Evidence Density Tile
// Doctrine: a gate is not passed until evidence is filed; filing is not evidence until verified.
// Spec: GEX_v4.1_Working_Document.docx Appendix E §E.5

export type EvidenceVerification = 'MISSING' | 'FILED' | 'CONFIRMED' | 'AUDITED'

export interface EvidenceItem {
  gate_id: string
  gate_label: string
  verification: EvidenceVerification
  filed_at?: string   // ISO date
  confirmed_by?: string
}

export interface EvidenceDensityTileProps {
  items: EvidenceItem[]
  title?: string
  compact?: boolean
  className?: string
}

// Ordered severity: MISSING < FILED < CONFIRMED < AUDITED
const VERIF_ORDER: EvidenceVerification[] = ['MISSING', 'FILED', 'CONFIRMED', 'AUDITED']
const VERIF_INDEX: Record<EvidenceVerification, number> = {
  MISSING: 0, FILED: 1, CONFIRMED: 2, AUDITED: 3,
}

const VERIF_COLOR: Record<EvidenceVerification, { fill: string; stroke: string; label: string }> = {
  MISSING:   { fill: '#f1f5f9', stroke: '#cbd5e1', label: 'Missing' },
  FILED:     { fill: '#fef3c7', stroke: '#d97706', label: 'Filed' },
  CONFIRMED: { fill: '#ccfbf1', stroke: '#0ea5a0', label: 'Confirmed' },
  AUDITED:   { fill: '#0ea5a0', stroke: '#0ea5a0', label: 'Audited' },
}

function densityScore(items: EvidenceItem[]): number {
  if (items.length === 0) return 0
  const sum = items.reduce((s, i) => s + VERIF_INDEX[i.verification], 0)
  return sum / (items.length * (VERIF_ORDER.length - 1))
}

export function EvidenceDensityTile({
  items,
  title = 'Evidence',
  compact = false,
  className = '',
}: EvidenceDensityTileProps) {
  const CELL = compact ? 10 : 13
  const GAP = 1
  const COLS = Math.ceil(Math.sqrt(items.length)) || 1
  const ROWS = Math.ceil(items.length / COLS)
  const W = COLS * (CELL + GAP) - GAP
  const H = ROWS * (CELL + GAP) - GAP

  const score = densityScore(items)
  const scoreColor = score >= 0.75 ? '#16a34a' : score >= 0.5 ? '#d97706' : '#dc2626'

  const counts = VERIF_ORDER.reduce((acc, v) => {
    acc[v] = items.filter(i => i.verification === v).length
    return acc
  }, {} as Record<EvidenceVerification, number>)

  return (
    <div className={`${className}`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-[9px] font-bold text-slate-500 font-mono uppercase tracking-wide">{title}</span>
        <span className="text-[9px] font-bold font-mono" style={{ color: scoreColor }}>
          {Math.round(score * 100)}%
        </span>
      </div>

      <svg
        width="100%"
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="xMidYMid meet"
        className="overflow-visible"
      >
        {items.map((item, idx) => {
          const col = idx % COLS
          const row = Math.floor(idx / COLS)
          const x = col * (CELL + GAP)
          const y = row * (CELL + GAP)
          const c = VERIF_COLOR[item.verification]

          return (
            <rect
              key={item.gate_id}
              x={x}
              y={y}
              width={CELL}
              height={CELL}
              rx="1"
              fill={c.fill}
              stroke={c.stroke}
              strokeWidth="0.75"
            >
              <title>{item.gate_label} — {c.label}{item.confirmed_by ? ` by ${item.confirmed_by}` : ''}</title>
            </rect>
          )
        })}
      </svg>

      {/* Mini legend */}
      {!compact && (
        <div className="flex items-center gap-2 mt-1 flex-wrap">
          {VERIF_ORDER.filter(v => counts[v] > 0).map(v => {
            const c = VERIF_COLOR[v]
            return (
              <div key={v} className="flex items-center gap-0.5">
                <div
                  className="w-2.5 h-2.5 rounded-sm"
                  style={{ background: c.fill, border: `1px solid ${c.stroke}` }}
                />
                <span className="text-[7px] text-slate-500">{c.label} ({counts[v]})</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// Build EvidenceItems from bankability gates
import type { CustomerProject } from '@/data/customerProjects'

export function evidenceFromProject(project: CustomerProject): EvidenceItem[] {
  return (project.bankability?.gates ?? []).map(g => ({
    gate_id: g.id,
    gate_label: g.name ?? g.id,
    verification: g.is_complete
      ? 'CONFIRMED'
      : g.verified_count > 0
      ? 'FILED'
      : 'MISSING',
  }))
}
