// Primitive E.6 — Lineage Trail
// Doctrine: every artefact carries a provenance chain; no artefact is valid without it.
// One identity, one provenance, three layers (bridge → token → trade).
// Spec: GEX_v4.1_Working_Document.docx Appendix E §E.6

export type LineageLayer = 'BRIDGE' | 'TOKEN' | 'TRADE'

export interface LineageNode {
  id: string
  label: string
  layer: LineageLayer
  state: string
  timestamp?: string
  actor?: string
  hash?: string        // short content hash for audit
  verified: boolean
}

export interface LineageTrailProps {
  nodes: LineageNode[]
  highlight_id?: string
  compact?: boolean
  className?: string
}

const LAYER_COLOR: Record<LineageLayer, { dot: string; line: string; badge: string; badgeBg: string }> = {
  BRIDGE: { dot: '#1e3a8a', line: '#bfdbfe', badge: '#1e3a8a', badgeBg: '#dbeafe' },
  TOKEN:  { dot: '#0ea5a0', line: '#ccfbf1', badge: '#0ea5a0', badgeBg: '#ccfbf1' },
  TRADE:  { dot: '#7c3aed', line: '#ede9fe', badge: '#7c3aed', badgeBg: '#ede9fe' },
}

const LAYER_LABEL: Record<LineageLayer, string> = {
  BRIDGE: 'Bridge',
  TOKEN:  'Token',
  TRADE:  'Trade',
}

export function LineageTrail({
  nodes,
  highlight_id,
  compact = false,
  className = '',
}: LineageTrailProps) {
  if (nodes.length === 0) return null

  const DOT_R = compact ? 4 : 5
  const LINE_W = compact ? 1 : 1.5
  const ROW_H = compact ? 18 : 24
  const LEFT = 12
  const W = 280
  const H = nodes.length * ROW_H

  return (
    <div className={`w-full ${className}`}>
      <svg
        width="100%"
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="xMinYMid meet"
        className="overflow-visible"
      >
        {nodes.map((node, i) => {
          const cy = i * ROW_H + ROW_H / 2
          const col = LAYER_COLOR[node.layer]
          const isHighlighted = node.id === highlight_id

          return (
            <g key={node.id}>
              {/* Connector line to next */}
              {i < nodes.length - 1 && (
                <line
                  x1={LEFT}
                  y1={cy + DOT_R}
                  x2={LEFT}
                  y2={cy + ROW_H - DOT_R}
                  stroke={col.line}
                  strokeWidth={LINE_W}
                />
              )}

              {/* Layer transition marker */}
              {i > 0 && nodes[i - 1].layer !== node.layer && (
                <line
                  x1={LEFT - 6}
                  y1={cy - ROW_H / 2}
                  x2={LEFT + 6}
                  y2={cy - ROW_H / 2}
                  stroke="#e2e8f0"
                  strokeWidth="1"
                  strokeDasharray="3 2"
                />
              )}

              {/* Dot */}
              <circle
                cx={LEFT}
                cy={cy}
                r={DOT_R}
                fill={isHighlighted ? col.dot : '#fff'}
                stroke={col.dot}
                strokeWidth={isHighlighted ? 0 : 1.5}
              />
              {node.verified && (
                <circle cx={LEFT} cy={cy} r={DOT_R - 1.5} fill={col.dot} fillOpacity={0.35} />
              )}

              {/* Layer badge */}
              <rect
                x={LEFT + DOT_R + 3}
                y={cy - 5}
                width={28}
                height={10}
                rx="2"
                fill={col.badgeBg}
              />
              <text
                x={LEFT + DOT_R + 17}
                y={cy + 3.5}
                textAnchor="middle"
                fontSize={6}
                fill={col.badge}
                fontWeight={700}
                className="font-mono uppercase"
              >
                {LAYER_LABEL[node.layer]}
              </text>

              {/* State */}
              <text
                x={LEFT + DOT_R + 36}
                y={cy + (compact ? 3 : 3.5)}
                fontSize={compact ? 7.5 : 8.5}
                fill={isHighlighted ? '#0f172a' : '#334155'}
                fontWeight={isHighlighted ? 700 : 500}
                className="font-mono uppercase tracking-wide"
              >
                {node.state}
              </text>

              {/* Label */}
              <text
                x={LEFT + DOT_R + 36}
                y={cy + (compact ? 10 : 12)}
                fontSize={compact ? 6.5 : 7.5}
                fill="#94a3b8"
              >
                {node.label}
                {node.actor ? ` · ${node.actor}` : ''}
                {node.hash ? ` #${node.hash}` : ''}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

// Build LineageNode[] from a project's state across layers
import type { CustomerProject } from '@/data/customerProjects'

export function lineageFromProject(project: CustomerProject): LineageNode[] {
  const nodes: LineageNode[] = []

  // Bridge layer — use project status as proxy
  const bridgeStateMap: Record<string, string> = {
    development: 'scoped',
    construction: 'committed',
    operational: 'drawn',
  }
  nodes.push({
    id: `bridge-${project.id}`,
    label: project.name,
    layer: 'BRIDGE',
    state: bridgeStateMap[project.status ?? 'development'] ?? 'identified',
    verified: (project.bankability?.overall_completion ?? 0) >= 70,
    timestamp: project.completion_date,
  })

  // Token layer — only if post-COD
  if (project.status === 'operating') {
    nodes.push({
      id: `token-${project.id}`,
      label: `${project.name} Token`,
      layer: 'TOKEN',
      state: 'minted',
      verified: true,
    })
  }

  return nodes
}
