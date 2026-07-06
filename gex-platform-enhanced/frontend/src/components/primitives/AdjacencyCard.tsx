// Primitive E.4 — Adjacency Card
// Doctrine: §3.5 Adjacency — proximity matrix P(A|B); first project pays full information
// cost; subsequent projects inherit platform density as network externality.
// Spec: GEX_v4.1_Working_Document.docx Appendix E §E.4

export interface AdjacencyNeighbour {
  project_id: string
  project_name: string
  fuel_pathway: string      // e.g. "green hydrogen", "e-methanol"
  jurisdiction: string
  certifier: string
  proximity_score: number   // P(A|B) [0.0–1.0]
  density_score: number     // accumulated evidence density [0.0–1.0]
  cohort_credit: number     // %-reduction in information cost [0–100]
  shared_gates: string[]    // gate IDs already satisfied by this neighbour
}

export interface AdjacencyCardProps {
  neighbours: AdjacencyNeighbour[]
  focal_project_id: string
  focal_project_name: string
  platform_density?: number  // overall platform density for this pathway
  max_shown?: number
  compact?: boolean
  className?: string
}

function ProximityDot({ score }: { score: number }) {
  const fill = score >= 0.75 ? '#0ea5a0' : score >= 0.5 ? '#d97706' : '#94a3b8'
  const r = 3 + score * 3
  return (
    <svg width={14} height={14} viewBox="0 0 14 14" className="inline-block shrink-0">
      <circle cx="7" cy="7" r={r} fill={fill} fillOpacity={0.7 + score * 0.3} />
    </svg>
  )
}

function CohortBadge({ credit }: { credit: number }) {
  if (credit < 5) return null
  return (
    <span className="ml-1 text-[8px] font-bold text-teal-700 bg-teal-50 border border-teal-200 rounded px-1 py-0.5">
      -{Math.round(credit)}% cost
    </span>
  )
}

export function AdjacencyCard({
  neighbours,
  focal_project_name,
  platform_density,
  max_shown = 3,
  compact = false,
  className = '',
}: AdjacencyCardProps) {
  const sorted = [...neighbours]
    .sort((a, b) => b.proximity_score - a.proximity_score)
    .slice(0, max_shown)

  if (sorted.length === 0) {
    return (
      <div className={`rounded border border-slate-200 bg-white p-2 ${className}`}>
        <p className="text-[9px] text-slate-400 font-mono uppercase tracking-wide">No adjacent projects</p>
        <p className="text-[8px] text-slate-300 mt-0.5">
          {focal_project_name} pays full information cost — first mover in this pathway.
        </p>
      </div>
    )
  }

  return (
    <div className={`rounded border border-slate-200 bg-white ${compact ? 'p-1.5' : 'p-2'} ${className}`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-[9px] font-bold text-slate-500 font-mono uppercase tracking-wide">
          Adjacent Projects
        </span>
        {platform_density !== undefined && (
          <span className="text-[8px] text-slate-400">
            Platform density{' '}
            <span className="font-bold text-teal-600">{Math.round(platform_density * 100)}%</span>
          </span>
        )}
      </div>

      <div className={`flex flex-col ${compact ? 'gap-0.5' : 'gap-1'}`}>
        {sorted.map(n => (
          <div key={n.project_id} className="flex items-start gap-1.5">
            <div className="pt-0.5">
              <ProximityDot score={n.proximity_score} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1 flex-wrap">
                <span className={`font-semibold text-slate-700 truncate ${compact ? 'text-[8px]' : 'text-[9px]'}`}>
                  {n.project_name}
                </span>
                <CohortBadge credit={n.cohort_credit} />
              </div>
              <div className={`text-slate-400 truncate ${compact ? 'text-[7px]' : 'text-[8px]'}`}>
                {n.fuel_pathway} · {n.jurisdiction} · {n.certifier}
              </div>
              {n.shared_gates.length > 0 && (
                <div className={`text-teal-500 ${compact ? 'text-[7px]' : 'text-[8px]'}`}>
                  {n.shared_gates.length} shared gate{n.shared_gates.length > 1 ? 's' : ''}
                </div>
              )}
            </div>
            <div className="shrink-0 text-right">
              <div className={`font-bold font-mono ${compact ? 'text-[8px]' : 'text-[9px]'} text-slate-600`}>
                {Math.round(n.proximity_score * 100)}%
              </div>
              <div className={`text-slate-400 ${compact ? 'text-[7px]' : 'text-[8px]'}`}>
                P(A|B)
              </div>
            </div>
          </div>
        ))}
      </div>

      {neighbours.length > max_shown && (
        <p className="text-[7px] text-slate-400 mt-1 text-right">
          +{neighbours.length - max_shown} more adjacent projects
        </p>
      )}
    </div>
  )
}

// Stub: derive adjacency from static project list until backend adjacency.py is live
import type { CustomerProject } from '@/data/customerProjects'

export function neighboursFromProjects(
  focal: CustomerProject,
  all: CustomerProject[],
): AdjacencyNeighbour[] {
  return all
    .filter(p => p.id !== focal.id)
    .map(p => {
      const sameFuel = p.molecule === focal.molecule ? 0.4 : 0
      const sameCountry = p.country === focal.country ? 0.2 : 0
      const proximity = Math.min(1, 0.3 + sameFuel + sameCountry + Math.random() * 0.1)
      const density = Math.min(1, (p.bankability?.overall_completion ?? 50) / 100)
      return {
        project_id: p.id,
        project_name: p.name,
        fuel_pathway: p.molecule,
        jurisdiction: p.country,
        certifier: 'TÜV SÜD',
        proximity_score: parseFloat(proximity.toFixed(2)),
        density_score: parseFloat(density.toFixed(2)),
        cohort_credit: Math.round(proximity * 25),
        shared_gates: [],
      }
    })
    .sort((a, b) => b.proximity_score - a.proximity_score)
}
