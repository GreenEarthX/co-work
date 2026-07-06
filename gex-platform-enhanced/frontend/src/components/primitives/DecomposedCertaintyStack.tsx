// Primitive E.3 — Decomposed Certainty Stack
// Doctrine: certainty is a product of evidence, not assertion; decompose before aggregating.
// Spec: GEX_v4.1_Working_Document.docx Appendix E §E.3

export interface CertaintyAxis {
  id: 'COST' | 'REVENUE' | 'CERTIFICATION' | 'EXECUTION' | 'COUNTERPARTY'
  label: string
  raw_score: number         // [0.0–1.0]
  verification_weight: number // [0.0–1.0]
  weighted_score: number    // raw_score × verification_weight [0.0–1.0]
  blocking_flag: boolean
}

export interface DecomposedCertaintyStackProps {
  axes: CertaintyAxis[]
  effective_score?: number  // aggregate, shown at right edge
  threshold?: number        // minimum acceptable (default 0.70 for senior debt)
  compact?: boolean
  className?: string
}

const AXIS_ORDER: CertaintyAxis['id'][] = ['COST', 'REVENUE', 'CERTIFICATION', 'EXECUTION', 'COUNTERPARTY']

const AXIS_LABEL: Record<CertaintyAxis['id'], string> = {
  COST: 'Cost',
  REVENUE: 'Revenue',
  CERTIFICATION: 'Cert.',
  EXECUTION: 'Execution',
  COUNTERPARTY: 'Counterparty',
}

function barColor(score: number): { fill: string; bg: string; text: string } {
  if (score >= 0.75) return { fill: '#16a34a', bg: '#dcfce7', text: '#15803d' }
  if (score >= 0.50) return { fill: '#d97706', bg: '#fef3c7', text: '#b45309' }
  return { fill: '#dc2626', bg: '#fee2e2', text: '#b91c1c' }
}

export function DecomposedCertaintyStack({
  axes,
  effective_score,
  threshold = 0.70,
  compact = false,
  className = '',
}: DecomposedCertaintyStackProps) {
  const ordered = AXIS_ORDER
    .map(id => axes.find(a => a.id === id))
    .filter(Boolean) as CertaintyAxis[]

  const BAR_W = 200
  const ROW_H = compact ? 14 : 18
  const LABEL_W = compact ? 56 : 72
  const SCORE_W = 32
  const TOTAL_W = LABEL_W + BAR_W + SCORE_W + 8
  const TOTAL_H = ordered.length * (ROW_H + (compact ? 2 : 3)) + (compact ? 0 : 4)

  const thresholdX = threshold * BAR_W

  return (
    <div className={`w-full ${className}`}>
      <svg
        width="100%"
        viewBox={`0 0 ${TOTAL_W} ${TOTAL_H}`}
        preserveAspectRatio="xMidYMid meet"
        className="overflow-visible"
      >
        {ordered.map((axis, i) => {
          const y = i * (ROW_H + (compact ? 2 : 3))
          const col = barColor(axis.weighted_score)
          const fillW = axis.weighted_score * BAR_W

          return (
            <g key={axis.id}>
              {/* Label */}
              <text
                x={LABEL_W - 4}
                y={y + ROW_H / 2 + 3.5}
                textAnchor="end"
                fontSize={compact ? 8 : 9}
                fill={axis.blocking_flag ? '#b91c1c' : '#475569'}
                fontWeight={axis.blocking_flag ? 700 : 500}
                className="font-mono uppercase tracking-wide"
              >
                {AXIS_LABEL[axis.id]}
                {axis.blocking_flag && ' ⚠'}
              </text>

              {/* Bar background */}
              <rect
                x={LABEL_W}
                y={y}
                width={BAR_W}
                height={ROW_H}
                fill={col.bg}
                rx="1.5"
              />

              {/* Bar fill (weighted score) */}
              {fillW > 0 && (
                <rect
                  x={LABEL_W}
                  y={y}
                  width={fillW}
                  height={ROW_H}
                  fill={col.fill}
                  rx="1.5"
                  fillOpacity={0.85}
                />
              )}

              {/* Threshold marker */}
              <line
                x1={LABEL_W + thresholdX}
                y1={y - 1}
                x2={LABEL_W + thresholdX}
                y2={y + ROW_H + 1}
                stroke="#94a3b8"
                strokeWidth="1"
                strokeDasharray="2 2"
              />

              {/* Blocking lock overlay */}
              {axis.blocking_flag && (
                <rect
                  x={LABEL_W + fillW + 2}
                  y={y + ROW_H / 2 - 4}
                  width={8}
                  height={8}
                  fill="none"
                />
              )}

              {/* Weighted score text */}
              <text
                x={LABEL_W + BAR_W + 4}
                y={y + ROW_H / 2 + 3.5}
                fontSize={compact ? 7.5 : 8.5}
                fill={col.text}
                fontWeight={700}
                className="font-mono"
              >
                {Math.round(axis.weighted_score * 100)}
              </text>
            </g>
          )
        })}

        {/* Threshold legend label */}
        <text
          x={LABEL_W + thresholdX}
          y={TOTAL_H + (compact ? 7 : 9)}
          textAnchor="middle"
          fontSize={7}
          fill="#94a3b8"
          className="font-mono"
        >
          min {Math.round(threshold * 100)}
        </text>
      </svg>

      {/* Effective score footer */}
      {effective_score !== undefined && (
        <div className="flex items-center justify-end mt-1 pr-1">
          <span className="text-[9px] text-slate-400 mr-1 font-mono uppercase tracking-wide">Effective score</span>
          <span
            className="text-[11px] font-bold font-mono"
            style={{ color: barColor(effective_score).text }}
          >
            {Math.round(effective_score * 100)}
          </span>
        </div>
      )}
    </div>
  )
}

// Blocking flags from any axis freeze capital eligibility
export function hasBlockingAxis(axes: CertaintyAxis[]): boolean {
  return axes.some(a => a.blocking_flag)
}

// Build CertaintyAxis[] from bankability sub-scores
export function axesFromBankability(bankability: {
  score: number
  gates?: Array<{ id: string; status: string }>
  sub_scores?: Record<string, { raw: number; verification_weight: number; blocking: boolean }>
}): CertaintyAxis[] {
  const sub = bankability.sub_scores ?? {}
  const defaultWeight = bankability.score / 100

  const build = (
    id: CertaintyAxis['id'],
    key: string,
    fallback: number,
  ): CertaintyAxis => {
    const s = sub[key]
    const raw = s?.raw ?? fallback
    const vw = s?.verification_weight ?? defaultWeight
    return {
      id,
      label: AXIS_LABEL[id],
      raw_score: raw,
      verification_weight: vw,
      weighted_score: raw * vw,
      blocking_flag: s?.blocking ?? false,
    }
  }

  return [
    build('COST',          'cost_certainty',          0.6),
    build('REVENUE',       'revenue_certainty',       0.6),
    build('CERTIFICATION', 'certification_certainty', 0.5),
    build('EXECUTION',     'execution_certainty',     0.55),
    build('COUNTERPARTY',  'counterparty_certainty',  0.5),
  ]
}
