// Screen: Shared component — Gate-locked screens
/**
 * GateLock — workflow enforcement wrapper.
 *
 * Wraps a screen's content and shows a locked state when the
 * prerequisite gate is below the completion threshold.
 *
 * Usage:
 *   <GateLock path="/capital-stack">
 *     <CapitalStack />
 *   </GateLock>
 */

import { Lock, ArrowRight, AlertTriangle } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useGateAccess, type GateRequirement } from '@/hooks/useGateAccess'
import { useUserRole, type UserRole } from '@/contexts/UserRoleContext'
import { isEmitRoute, shouldViewLockedScreen } from '@/config/gateAccess'

interface GateLockProps {
  /** The route path of this screen (used to look up gate_prerequisite). */
  path: string
  children: React.ReactNode
}

const GATE_RESOLVE_ROUTES: Record<string, string> = {
  G4: '/offtaker-supply',
  G5: '/stage-gates',
  G6: '/evidence-hierarchy',
  G7: '/insurance-schedule',
  G8: '/dscr-sensitivity',
  G9: '/regulator-dashboard',
  G10: '/stage-gates',
}

export function GateLock({ path, children }: GateLockProps) {
  const { getGateRequirement } = useGateAccess()
  const { role } = useUserRole()
  const req = getGateRequirement(path)

  if (!req || !req.isLocked) return <>{children}</>

  // Gate the verb, not the view. A readiness assessor (lender) sees a
  // diagnostic screen with its gate position stated, rather than a padlock —
  // assessing an unready project is their job, and the gate they were held
  // behind belongs to the sponsor. EMIT routes stay locked for everyone.
  if (shouldViewLockedScreen(role, path)) {
    return (
      <>
        <ReadinessBanner requirement={req} />
        {children}
      </>
    )
  }

  return <LockedScreen requirement={req} isEmit={isEmitRoute(path)} role={role} />
}

/**
 * Shown above a diagnostic screen an assessor is reading ahead of its gate.
 * The figures are visible; the banner prevents them being mistaken for
 * committee-ready output.
 */
function ReadinessBanner({ requirement }: { requirement: GateRequirement }) {
  return (
    <div className="mx-6 mt-4 mb-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
      <div className="flex items-start gap-2.5">
        <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
        <p className="text-sm text-slate-700 leading-relaxed">
          <span className="font-semibold">
            Pre-{requirement.gateShortId}: {requirement.gateName} is {requirement.completionPct}%
            complete
          </span>{' '}
          (this screen is normally released at {requirement.threshold}%). Figures below are shown
          for assessment and are <span className="font-semibold">not committee-ready</span>.
          Closing this gate is the sponsor&apos;s action.
        </p>
      </div>
    </div>
  )
}

function LockedScreen({
  requirement,
  isEmit = false,
  role,
}: {
  requirement: GateRequirement
  isEmit?: boolean
  role?: UserRole
}) {
  const navigate = useNavigate()
  const resolveRoute = GATE_RESOLVE_ROUTES[requirement.gateShortId]

  // An emit gate is not a defect to be worked around — it is the control a
  // lender wants to exist. Say so plainly rather than implying the screen is
  // merely unfinished.
  const heading = isEmit ? 'Not yet releasable' : 'Screen Locked'
  const body = isEmit
    ? `This produces an artefact that leaves the platform. It is released once ${requirement.gateShortId}: ${requirement.gateName} reaches ${requirement.threshold}% — the control that prevents a committee-ready document being issued over an open gate.`
    : `This screen requires ${requirement.gateShortId}: ${requirement.gateName} to reach ${requirement.threshold}% completion before it becomes actionable.`

  // Never tell a lender to "Work on G8" — closing the sponsor's gate is not
  // their action. Point them at the evidence instead.
  const isAssessor = role?.service_type === 'BANK'
  const ctaLabel = isAssessor
    ? `Review ${requirement.gateShortId} evidence`
    : `Work on ${requirement.gateShortId}`

  return (
    <div className="min-h-[60vh] flex items-center justify-center p-8">
      <div
        className="max-w-md w-full rounded-xl p-8 text-center"
        style={{
          border: '1px solid var(--border, #e2e8f0)',
          backgroundColor: 'var(--surface-raised, #f8fafc)',
        }}
      >
        <div
          className="mx-auto w-14 h-14 rounded-full flex items-center justify-center mb-5"
          style={{ backgroundColor: 'var(--surface, #f1f5f9)' }}
        >
          <Lock className="w-6 h-6" style={{ color: 'var(--text-muted, #94a3b8)' }} />
        </div>

        <h2 className="text-lg font-bold mb-2" style={{ color: 'var(--text, #0f172a)' }}>
          {heading}
        </h2>

        <p className="text-sm mb-4" style={{ color: 'var(--text-muted, #64748b)' }}>
          {body}
        </p>

        {/* Progress bar */}
        <div className="mb-5">
          <div className="flex justify-between text-xs mb-1" style={{ color: 'var(--text-muted, #64748b)' }}>
            <span>Current progress</span>
            <span>{requirement.completionPct}% / {requirement.threshold}%</span>
          </div>
          <div className="w-full h-2 rounded-full" style={{ backgroundColor: 'var(--surface, #e2e8f0)' }}>
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${Math.min(100, (requirement.completionPct / requirement.threshold) * 100)}%`,
                backgroundColor: requirement.completionPct > 0 ? '#f59e0b' : '#e2e8f0',
              }}
            />
          </div>
        </div>

        {resolveRoute && (
          <button
            onClick={() => navigate(resolveRoute)}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-colors"
            style={{
              backgroundColor: 'var(--brand, #0ea5a0)',
              color: '#fff',
            }}
          >
            {ctaLabel}
            <ArrowRight className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  )
}
