// Screen: Shared component — Finance workflow screens
/**
 * WorkflowBadge — small reusable state badge for governed bankability objects.
 * Shows the current workflow state with colour coding and an optional staleness warning.
 */
import { Pencil, Zap, Eye, CheckCircle, Download, Share2, AlertTriangle, ShieldCheck } from 'lucide-react'

// ─────────────────────────────── Types ───────────────────────────────────────

export type WorkflowState =
  | 'DRAFT'
  | 'COMPUTED'
  | 'REVIEWED'
  | 'INSURANCE_REVIEWED'
  | 'APPROVED'
  | 'EXPORTED'
  | 'SHARED_EXTERNAL'

interface WorkflowBadgeProps {
  state: WorkflowState
  computedAt?: string   // ISO timestamp
  showStale?: boolean   // if true, show amber warning when >7 days old
  size?: 'sm' | 'md'
}

// ─────────────────────────────── Style map ───────────────────────────────────

const STATE_STYLES: Record<
  WorkflowState,
  { bg: string; text: string; border: string; label: string; Icon: React.ElementType }
> = {
  DRAFT: {
    bg: 'bg-gray-100',
    text: 'text-gray-600',
    border: 'border-gray-300',
    label: 'Draft',
    Icon: Pencil,
  },
  COMPUTED: {
    bg: 'bg-blue-100',
    text: 'text-blue-700',
    border: 'border-blue-300',
    label: 'Computed',
    Icon: Zap,
  },
  REVIEWED: {
    bg: 'bg-amber-100',
    text: 'text-amber-700',
    border: 'border-amber-300',
    label: 'Reviewed',
    Icon: Eye,
  },
  INSURANCE_REVIEWED: {
    bg: 'bg-sky-100',
    text: 'text-sky-700',
    border: 'border-sky-300',
    label: 'Insurance Reviewed',
    Icon: ShieldCheck,
  },
  APPROVED: {
    bg: 'bg-green-100',
    text: 'text-green-700',
    border: 'border-green-300',
    label: 'Approved',
    Icon: CheckCircle,
  },
  EXPORTED: {
    bg: 'bg-teal-100',
    text: 'text-teal-700',
    border: 'border-teal-300',
    label: 'Exported',
    Icon: Download,
  },
  SHARED_EXTERNAL: {
    bg: 'bg-purple-100',
    text: 'text-purple-700',
    border: 'border-purple-300',
    label: 'Shared',
    Icon: Share2,
  },
}

// ─────────────────────────────── Helpers ─────────────────────────────────────

function isStale(computedAt: string): boolean {
  const computed = new Date(computedAt)
  const now = new Date()
  const diffMs = now.getTime() - computed.getTime()
  const diffDays = diffMs / (1000 * 60 * 60 * 24)
  return diffDays > 7
}

// ─────────────────────────────── Component ───────────────────────────────────

export function WorkflowBadge({
  state,
  computedAt,
  showStale = true,
  size = 'md',
}: WorkflowBadgeProps) {
  const style = STATE_STYLES[state]
  const { Icon } = style

  const iconSize = size === 'sm' ? 'w-3 h-3' : 'w-3.5 h-3.5'
  const textSize = size === 'sm' ? 'text-xs' : 'text-xs'
  const padding = size === 'sm' ? 'px-2 py-0.5' : 'px-2.5 py-1'

  const staleVisible = showStale && computedAt && isStale(computedAt)

  return (
    <div className="flex items-center gap-1.5">
      {/* State badge */}
      <span
        className={`inline-flex items-center gap-1 ${padding} rounded-md border font-semibold ${textSize} ${style.bg} ${style.text} ${style.border}`}
      >
        <Icon className={iconSize} />
        {style.label}
      </span>

      {/* Staleness warning */}
      {staleVisible && (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border border-amber-300 bg-amber-50 text-amber-700 text-xs font-semibold">
          <AlertTriangle className="w-3 h-3" />
          Stale — recompute recommended
        </span>
      )}
    </div>
  )
}
