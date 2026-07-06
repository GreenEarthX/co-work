// Primitive E.7 — Causal Nav Bar
// Doctrine: navigation follows causal sequence — a user can only move forward once the
// precondition layer is satisfied; the bar makes causal dependencies visible at a glance.
// Spec: GEX_v4.1_Working_Document.docx Appendix E §E.7

export type CausalLayer = 'BRIDGE' | 'TOKEN' | 'TRADE'

export interface CausalStep {
  id: string
  label: string
  layer: CausalLayer
  unlocked: boolean    // true when preconditions are met
  active: boolean      // currently selected
  href?: string        // router path if unlocked
  badge?: string | number
}

export interface CausalNavBarProps {
  steps: CausalStep[]
  onNavigate?: (step: CausalStep) => void
  className?: string
}

const LAYER_COLOR: Record<CausalLayer, { active: string; unlocked: string; locked: string; accent: string }> = {
  BRIDGE: { active: '#1e3a8a', unlocked: '#dbeafe', locked: '#f8fafc', accent: '#1e3a8a' },
  TOKEN:  { active: '#0ea5a0', unlocked: '#ccfbf1', locked: '#f8fafc', accent: '#0ea5a0' },
  TRADE:  { active: '#7c3aed', unlocked: '#ede9fe', locked: '#f8fafc', accent: '#7c3aed' },
}

function LockIcon({ size = 8 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 8 8" fill="none" className="inline-block opacity-40">
      <rect x="1.5" y="3.5" width="5" height="4" rx="0.5" stroke="#94a3b8" strokeWidth="1" />
      <path d="M2.5 3.5V2.5a1.5 1.5 0 0 1 3 0v1" stroke="#94a3b8" strokeWidth="1" />
    </svg>
  )
}

export function CausalNavBar({
  steps,
  onNavigate,
  className = '',
}: CausalNavBarProps) {
  let lastLayer: CausalLayer | null = null

  return (
    <nav className={`flex items-center flex-wrap gap-0 ${className}`} role="navigation" aria-label="Project causal flow">
      {steps.map((step, i) => {
        const showDivider = lastLayer !== null && lastLayer !== step.layer
        lastLayer = step.layer
        const col = LAYER_COLOR[step.layer]

        const baseCls =
          'relative flex items-center gap-1 px-2 py-1 rounded text-[9px] font-bold uppercase tracking-wide whitespace-nowrap select-none transition-colors'

        const colorCls = step.active
          ? `text-white`
          : step.unlocked
          ? `text-slate-700 hover:opacity-80 cursor-pointer`
          : `text-slate-300 cursor-not-allowed`

        const bg = step.active
          ? col.active
          : step.unlocked
          ? col.unlocked
          : col.locked

        const handleClick = () => {
          if (step.unlocked && onNavigate) onNavigate(step)
        }

        return (
          <div key={step.id} className="flex items-center">
            {/* Layer divider */}
            {showDivider && (
              <div className="mx-1 h-4 w-px bg-slate-200" />
            )}

            <button
              className={`${baseCls} ${colorCls}`}
              style={{ background: bg }}
              onClick={handleClick}
              disabled={!step.unlocked}
              aria-current={step.active ? 'page' : undefined}
            >
              {!step.unlocked && <LockIcon />}
              {step.label}
              {step.badge !== undefined && step.badge !== '' && (
                <span
                  className="ml-0.5 text-[7px] font-bold rounded-full px-1 py-0.5 leading-none"
                  style={{
                    background: step.active ? 'rgba(255,255,255,0.25)' : col.accent + '25',
                    color: step.active ? '#fff' : col.accent,
                  }}
                >
                  {step.badge}
                </span>
              )}
            </button>

            {/* Arrow connector within same layer */}
            {i < steps.length - 1 && steps[i + 1].layer === step.layer && (
              <div className="text-slate-300 text-[10px] mx-0.5">›</div>
            )}
          </div>
        )
      })}
    </nav>
  )
}

// Build CausalStep[] from project state
import type { CustomerProject } from '@/data/customerProjects'

export function causalStepsFromProject(
  project: CustomerProject,
  currentPath: string,
): CausalStep[] {
  const isPostCod = project.status === 'operating'
  const bankabilityScore = project.bankability?.overall_completion ?? 0

  const bridgeSteps: CausalStep[] = [
    {
      id: 'bridge-overview',
      label: 'Overview',
      layer: 'BRIDGE',
      unlocked: true,
      active: currentPath.includes('overview'),
    },
    {
      id: 'bridge-bankability',
      label: 'Bankability',
      layer: 'BRIDGE',
      unlocked: true,
      active: currentPath.includes('bankability'),
      badge: `${bankabilityScore}%`,
    },
    {
      id: 'bridge-finance',
      label: 'Finance',
      layer: 'BRIDGE',
      unlocked: bankabilityScore >= 60,
      active: currentPath.includes('finance'),
    },
    {
      id: 'bridge-risk',
      label: 'Risk',
      layer: 'BRIDGE',
      unlocked: bankabilityScore >= 50,
      active: currentPath.includes('risk'),
    },
  ]

  const tokenSteps: CausalStep[] = [
    {
      id: 'token-mint',
      label: 'Tokenise',
      layer: 'TOKEN',
      unlocked: isPostCod,
      active: currentPath.includes('token'),
    },
  ]

  const tradeSteps: CausalStep[] = [
    {
      id: 'trade-market',
      label: 'Trade',
      layer: 'TRADE',
      unlocked: isPostCod,
      active: currentPath.includes('trade'),
    },
  ]

  return [...bridgeSteps, ...tokenSteps, ...tradeSteps]
}
