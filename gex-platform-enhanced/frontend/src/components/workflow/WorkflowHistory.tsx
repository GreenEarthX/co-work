/**
 * WorkflowHistory — collapsible audit trail of workflow state transitions.
 * Shows a timeline of events with state badges, actor names, timestamps, and optional notes.
 */
import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { WorkflowBadge } from './WorkflowBadge'
import type { WorkflowState } from './WorkflowBadge'

// ─────────────────────────────── Types ───────────────────────────────────────

interface WorkflowEvent {
  state: WorkflowState
  actor: string
  timestamp: string   // ISO string
  note?: string
}

interface WorkflowHistoryProps {
  events: WorkflowEvent[]
  collapsed?: boolean
}

// ─────────────────────────────── Helpers ─────────────────────────────────────

function formatTimestamp(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).replace(',', '')
}

// ─────────────────────────────── Component ───────────────────────────────────

export function WorkflowHistory({ events, collapsed = true }: WorkflowHistoryProps) {
  const [isCollapsed, setIsCollapsed] = useState(collapsed)

  if (events.length === 0) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white shadow-sm px-4 py-3">
        <p className="text-xs text-gray-400 italic">No workflow history yet.</p>
      </div>
    )
  }

  // Most-recent event first for display
  const sorted = [...events].sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
  )

  const latest = sorted[0]
  const remaining = sorted.slice(1)

  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
      {/* Header row */}
      <button
        type="button"
        onClick={() => setIsCollapsed(v => !v)}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-gray-50 border-b border-gray-100 hover:bg-gray-100 transition-colors"
      >
        <span className="text-xs font-black uppercase tracking-widest text-gray-600">
          Workflow History
        </span>
        <div className="flex items-center gap-2">
          {isCollapsed && remaining.length > 0 && (
            <span className="text-xs text-gray-400 font-medium">
              +{remaining.length} earlier event{remaining.length !== 1 ? 's' : ''}
            </span>
          )}
          {isCollapsed ? (
            <ChevronDown className="w-4 h-4 text-gray-400" />
          ) : (
            <ChevronUp className="w-4 h-4 text-gray-400" />
          )}
        </div>
      </button>

      {/* Timeline body */}
      <div className="px-4 py-3 space-y-0">
        {/* Always show the latest event */}
        <TimelineEntry event={latest} isLast={isCollapsed || remaining.length === 0} isFirst />

        {/* Show the rest when expanded */}
        {!isCollapsed && remaining.map((evt, idx) => (
          <TimelineEntry
            key={`${evt.state}-${evt.timestamp}`}
            event={evt}
            isFirst={false}
            isLast={idx === remaining.length - 1}
          />
        ))}
      </div>
    </div>
  )
}

// ─────────────────────────────── Sub-component ───────────────────────────────

function TimelineEntry({
  event,
  isFirst,
  isLast,
}: {
  event: WorkflowEvent
  isFirst: boolean
  isLast: boolean
}) {
  return (
    <div className="flex gap-3">
      {/* Vertical line + dot */}
      <div className="flex flex-col items-center">
        <div className={`w-2.5 h-2.5 rounded-full border-2 mt-1 shrink-0 ${
          isFirst ? 'bg-blue-500 border-blue-500' : 'bg-gray-300 border-gray-300'
        }`} />
        {!isLast && <div className="w-px flex-1 bg-gray-200 my-1" />}
      </div>

      {/* Content */}
      <div className={`pb-3 min-w-0 ${isLast ? '' : ''}`}>
        <div className="flex flex-wrap items-center gap-2 mb-0.5">
          <WorkflowBadge state={event.state} showStale={false} size="sm" />
          <span className="text-xs font-semibold text-gray-700">{event.actor}</span>
          <span className="text-xs text-gray-400 tabular-nums">
            {formatTimestamp(event.timestamp)}
          </span>
        </div>
        {event.note && (
          <p className="text-xs text-gray-500 italic mt-0.5">{event.note}</p>
        )}
      </div>
    </div>
  )
}
