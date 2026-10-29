// Screen: Shared layout component — all authenticated screens
/**
 * "Feeds G4 Offtake bankable — 3 of 7 items verified" (JML 2026-10-28).
 *
 * Tells the user which gate the work on this screen feeds and how far the
 * ENGINE has that gate for the selected project, with a link to its open items.
 * It locks nothing: the screen-to-gate map (GET /api/v1/gates/screen-gates) is
 * information only, and the figures are the engine's, scoped to the caller's
 * persona — a gate outside the caller's view is not shown.
 */
import { Link, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getAuthHeader } from '@/lib/authToken'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'
import type { CustomerProject } from '@/data/customerProjects'

const DETERMINATION: Record<string, { label: string; tone: string }> = {
  SATISFIED: { label: 'satisfied', tone: 'text-emerald-700' },
  BLOCKED: { label: 'blocked', tone: 'text-red-700' },
  UNRESOLVED: { label: 'unresolved — confirmed terms missing', tone: 'text-amber-700' },
  INCOMPLETE: { label: 'in progress', tone: 'text-[var(--text-muted)]' },
  WAIVED: { label: 'waived for this financing model', tone: 'text-[var(--text-muted)]' },
}

export function GateFeedLine({ gateIds, bankability }: {
  gateIds: string[]; bankability: CustomerProject['bankability']
}) {
  if (gateIds.length === 0) return null
  if (bankability.evaluated === false) {
    return (
      <p data-testid="screen-gate-line" className="mb-4 font-mono text-[11px] text-amber-700">
        This screen feeds {gateIds.map(g => g.split('_')[0]).join(', ')} — not yet evaluated by the GEX engine.
      </p>
    )
  }
  const gates = gateIds
    .map(id => bankability.gates.find(g => g.id === id))
    .filter((g): g is NonNullable<typeof g> => !!g)
  if (gates.length === 0) return null
  return (
    <div data-testid="screen-gate-line" className="mb-4 flex flex-wrap items-baseline gap-x-6 gap-y-1 text-xs">
      {gates.map(g => {
        const d = DETERMINATION[g.determination ?? ''] ?? DETERMINATION.INCOMPLETE
        const reason = g.determination === 'BLOCKED' || g.determination === 'UNRESOLVED' ? g.blocked_reasons?.[0] : null
        return (
          <span key={g.id}>
            <span className="text-[var(--text-muted)]">Feeds </span>
            <span className="font-mono font-semibold">{g.id.split('_')[0]}</span> {g.name}
            <span className="text-[var(--text-muted)]"> — {g.verified_count} of {g.total_evidence} items verified · </span>
            <span className={d.tone}>{d.label}{reason ? `: ${reason}` : ''}</span>
          </span>
        )
      })}
      <Link to="/project-report" className="text-teal-700 underline">Open items</Link>
    </div>
  )
}

export function ScreenGateLine() {
  const { pathname } = useLocation()
  const { selectedProjectId } = useSelectedProject()
  const { projects } = useVisibleProjects()
  const { data: map } = useQuery<Record<string, string[]>>({
    queryKey: ['screen-gates'],
    queryFn: async () => {
      const r = await fetch('/api/v1/gates/screen-gates', { headers: getAuthHeader() })
      if (!r.ok) throw new Error(`screen-gates ${r.status}`)
      return r.json()
    },
    staleTime: Infinity,
  })
  const gateIds = map?.[pathname] ?? []
  const project = projects.find(p => p.id === selectedProjectId)
  if (!project || gateIds.length === 0) return null
  return <GateFeedLine gateIds={gateIds} bankability={project.bankability} />
}
