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

import { Lock, ArrowRight } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useGateAccess, type GateRequirement } from '@/hooks/useGateAccess'

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
  const req = getGateRequirement(path)

  if (!req || !req.isLocked) return <>{children}</>

  return <LockedScreen requirement={req} />
}

function LockedScreen({ requirement }: { requirement: GateRequirement }) {
  const navigate = useNavigate()
  const resolveRoute = GATE_RESOLVE_ROUTES[requirement.gateShortId]

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
          Screen Locked
        </h2>

        <p className="text-sm mb-4" style={{ color: 'var(--text-muted, #64748b)' }}>
          This screen requires <span className="font-semibold">{requirement.gateShortId}: {requirement.gateName}</span> to
          reach {requirement.threshold}% completion before it becomes actionable.
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
            Work on {requirement.gateShortId}
            <ArrowRight className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  )
}
