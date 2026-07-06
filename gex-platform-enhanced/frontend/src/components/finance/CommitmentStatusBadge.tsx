// Screen: Shared component — Finance commitment screens
/**
 * CommitmentStatusBadge — visual badge for the capital commitment lifecycle.
 * States: NONE → INDICATIVE → TERM_SHEET → CREDIT_APPROVED → LEGAL_COMPLETE → DRAWN
 */
import type { CommitmentStatus } from '@/data/customerProjects'

interface CommitmentStatusBadgeProps {
  status: CommitmentStatus
  size?: 'sm' | 'md'
  showProgress?: boolean
}

const STATUS_CONFIG: Record<
  CommitmentStatus,
  { label: string; bg: string; text: string; border: string; step: number }
> = {
  NONE:           { label: 'None',            bg: 'bg-gray-100',   text: 'text-gray-500',   border: 'border-gray-200',  step: 0 },
  INDICATIVE:     { label: 'Indicative',      bg: 'bg-blue-50',    text: 'text-blue-700',   border: 'border-blue-200',  step: 1 },
  TERM_SHEET:     { label: 'Term Sheet',      bg: 'bg-amber-50',   text: 'text-amber-700',  border: 'border-amber-300', step: 2 },
  CREDIT_APPROVED:{ label: 'Credit Approved', bg: 'bg-violet-50',  text: 'text-violet-700', border: 'border-violet-300',step: 3 },
  LEGAL_COMPLETE: { label: 'Legal Complete',  bg: 'bg-emerald-50', text: 'text-emerald-700',border: 'border-emerald-300',step: 4 },
  DRAWN:          { label: 'Drawn',           bg: 'bg-green-100',  text: 'text-green-800',  border: 'border-green-400', step: 5 },
}

const TOTAL_STEPS = 5

export function CommitmentStatusBadge({
  status,
  size = 'md',
  showProgress = false,
}: CommitmentStatusBadgeProps) {
  const cfg = STATUS_CONFIG[status]
  const padding = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs'

  return (
    <div className="inline-flex flex-col gap-1">
      <span
        className={`inline-flex items-center gap-1 ${padding} rounded-md border font-semibold ${cfg.bg} ${cfg.text} ${cfg.border}`}
      >
        {cfg.label}
      </span>
      {showProgress && (
        <div className="flex items-center gap-0.5">
          {Array.from({ length: TOTAL_STEPS }).map((_, i) => (
            <div
              key={i}
              className={`h-1 flex-1 rounded-full transition-colors ${
                i < cfg.step ? 'bg-green-500' : i === cfg.step - 1 ? 'bg-green-400' : 'bg-gray-200'
              }`}
            />
          ))}
        </div>
      )}
    </div>
  )
}
