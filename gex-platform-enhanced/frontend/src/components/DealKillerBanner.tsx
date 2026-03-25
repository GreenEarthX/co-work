/**
 * DealKillerBanner — R1 (Architectural Reform v6.0)
 *
 * Non-dismissable red banner that renders at the TOP of every workspace
 * page when one or more deal-killers are ACTIVE on the selected project.
 *
 * Visible to all actors who have visibility to the affected gates.
 * Cannot be dismissed — it persists until the killer is RESOLVED or WAIVED.
 *
 * Usage:
 *   <DealKillerBanner killers={activeKillers} />
 */

import { AlertTriangle, ArrowRight, XOctagon } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

// ─── Types ────────────────────────────────────────────────────────────────────

export type KillerSeverity = 'FATAL' | 'CRITICAL'

export interface ActiveKiller {
  id:             string
  gate:           string
  severity:       KillerSeverity
  plain_language: string
  action:         string
  page:           string
}

interface DealKillerBannerProps {
  killers: ActiveKiller[]
  /** Project name for display context */
  projectName?: string
}

// ─── Component ────────────────────────────────────────────────────────────────

export function DealKillerBanner({ killers, projectName }: DealKillerBannerProps) {
  const navigate = useNavigate()

  if (killers.length === 0) return null

  const fatalCount    = killers.filter(k => k.severity === 'FATAL').length
  const criticalCount = killers.filter(k => k.severity === 'CRITICAL').length

  const headline =
    fatalCount > 0
      ? `${fatalCount} FATAL DEAL-KILLER${fatalCount > 1 ? 'S' : ''} BLOCKING FID`
      : `${criticalCount} CRITICAL ITEM${criticalCount > 1 ? 'S' : ''} REQUIRE ATTENTION`

  return (
    <div
      role="alert"
      aria-live="assertive"
      className="w-full rounded-lg border border-red-400 bg-red-50 px-4 py-3 shadow-sm"
    >
      {/* Header row */}
      <div className="flex items-center gap-2 mb-2">
        <XOctagon className="w-4 h-4 text-red-600 flex-shrink-0" />
        <span className="text-sm font-bold text-red-700 uppercase tracking-wide">
          {headline}
        </span>
        {projectName && (
          <span className="text-xs text-red-500 ml-1">— {projectName}</span>
        )}
        <span className="ml-auto text-xs text-red-400 italic select-none">
          Cannot be dismissed until resolved
        </span>
      </div>

      {/* Killer list */}
      <ul className="space-y-1.5 pl-1">
        {killers.map(killer => (
          <li key={killer.id} className="flex items-start gap-2">
            {/* Severity dot */}
            <span
              className={`mt-1 flex-shrink-0 w-2 h-2 rounded-full ${
                killer.severity === 'FATAL' ? 'bg-red-600' : 'bg-orange-500'
              }`}
            />

            {/* Text */}
            <div className="flex-1 min-w-0">
              <span className="text-xs text-red-800">
                {killer.plain_language}
              </span>
            </div>

            {/* Navigation CTA */}
            {killer.page && (
              <button
                onClick={() => navigate(killer.page)}
                className="flex-shrink-0 inline-flex items-center gap-1 text-xs font-semibold text-red-700 hover:text-red-900 underline underline-offset-2 transition-colors"
              >
                Resolve
                <ArrowRight className="w-3 h-3" />
              </button>
            )}
          </li>
        ))}
      </ul>

      {/* Warning footer for FATAL */}
      {fatalCount > 0 && (
        <div className="mt-2 pt-2 border-t border-red-200 flex items-center gap-1.5">
          <AlertTriangle className="w-3.5 h-3.5 text-red-500 flex-shrink-0" />
          <p className="text-xs text-red-600">
            IC Pack export, committee-ready signal, and capital unlock classification
            are blocked until all FATAL killers are resolved.
          </p>
        </div>
      )}
    </div>
  )
}

// ─── Hook: fetch active killers for a project ─────────────────────────────────

import { useEffect, useState } from 'react'

export function useActiveKillers(projectId: string | undefined): {
  killers: ActiveKiller[]
  loading: boolean
} {
  const [killers, setKillers] = useState<ActiveKiller[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!projectId) return
    setLoading(true)

    fetch(`/api/v1/deal-killers/${projectId}`)
      .then(r => r.ok ? r.json() : Promise.reject(r))
      .then((data: { active_killers: ActiveKiller[] }) => {
        setKillers(data.active_killers)
      })
      .catch(() => {
        // Demo fallback — representative killers for demo projects
        setKillers(DEMO_KILLERS)
      })
      .finally(() => setLoading(false))
  }, [projectId])

  return { killers, loading }
}

// Demo data — used when API is unavailable
const DEMO_KILLERS: ActiveKiller[] = [
  {
    id:             'DK_G5_NO_EPC',
    gate:           'G5',
    severity:       'FATAL',
    plain_language: 'No EPC or EPCM contract has been executed — construction cannot proceed without a signed engineering, procurement, and construction agreement.',
    action:         'Execute an EPC or EPCM contract with an approved contractor.',
    page:           '/finance/stage-gates',
  },
  {
    id:             'DK_G8_NO_AUDIT_MODEL',
    gate:           'G8',
    severity:       'FATAL',
    plain_language: 'The financial model has not been verified to audit grade — credit committees require an independently reviewed, audited model before approving debt.',
    action:         'Commission a financial model audit from a named firm.',
    page:           '/finance/bankability',
  },
]
