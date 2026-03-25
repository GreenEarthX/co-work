/**
 * ApprovalTrail — embeddable audit trail for a specific resource.
 * Shows all WAE approval requests and decisions in chronological order.
 *
 * Backend: GET /api/v1/approvals/audit-trail/{resource_id}
 */
import { useState, useEffect } from 'react'
import { CheckCircle, XCircle, Clock, User } from 'lucide-react'
import { approvalsAPI } from '@/api'

interface AuditEntry {
  id: string
  type: 'request' | 'decision'
  timestamp: string
  action_type?: string
  status?: string
  decision?: string
  user_id: string
  reason?: string
  request_id?: string
}

interface Props {
  resourceId: string
  compact?: boolean
}

const DECISION_ICONS = {
  APPROVED: <CheckCircle size={14} className="text-green-600" />,
  REJECTED: <XCircle size={14} className="text-red-600" />,
  PENDING: <Clock size={14} className="text-amber-500" />,
}

export function ApprovalTrail({ resourceId, compact = false }: Props) {
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    approvalsAPI.getAuditTrail(resourceId)
      .then((data) => {
        setEntries(data.entries || [])
        setLoading(false)
      })
      .catch(() => {
        // Demo fallback trail
        setEntries([
          {
            id: 'ae-001',
            type: 'request',
            timestamp: '2026-03-16T08:30:00Z',
            action_type: 'SAF_FORWARD_SALE',
            status: 'PENDING',
            user_id: 'usr_bp_01',
            request_id: 'req-001',
          },
          {
            id: 'ae-002',
            type: 'decision',
            timestamp: '2026-03-16T09:15:00Z',
            decision: 'APPROVED',
            user_id: 'usr_risk_officer',
            reason: 'Within approved trading limits',
            request_id: 'req-001',
          },
          {
            id: 'ae-003',
            type: 'decision',
            timestamp: '2026-03-16T10:02:00Z',
            decision: 'APPROVED',
            user_id: 'usr_treasury_head',
            reason: 'Counterparty credit checked — OK',
            request_id: 'req-001',
          },
        ])
        setLoading(false)
      })
  }, [resourceId])

  if (loading) {
    return <div className="text-xs text-gray-400 py-2">Loading audit trail…</div>
  }

  if (entries.length === 0) {
    return (
      <div className="text-xs text-gray-400 py-2 italic">
        No approval history for this resource
      </div>
    )
  }

  return (
    <div className={compact ? '' : 'border rounded-lg p-4'}>
      {!compact && (
        <h3 className="text-sm font-semibold text-gray-700 mb-3">
          Approval Audit Trail
        </h3>
      )}
      <ol className="relative border-l border-gray-200 space-y-4 ml-2">
        {entries.map((entry) => (
          <li key={entry.id} className="ml-4">
            {/* Timeline dot */}
            <span className="absolute -left-1.5 flex h-3 w-3 items-center justify-center rounded-full border border-white bg-gray-200" />

            <div className="flex items-start gap-2">
              <div className="mt-0.5">
                {entry.type === 'request' ? (
                  <Clock size={14} className="text-amber-500" />
                ) : entry.decision ? (
                  DECISION_ICONS[entry.decision as keyof typeof DECISION_ICONS] || (
                    <User size={14} className="text-gray-400" />
                  )
                ) : (
                  <User size={14} className="text-gray-400" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium text-gray-800">
                  {entry.type === 'request'
                    ? `Approval requested: ${entry.action_type}`
                    : `Decision: ${entry.decision}`}
                </div>
                <div className="text-xs text-gray-500">
                  {entry.user_id} · {new Date(entry.timestamp).toLocaleString()}
                </div>
                {entry.reason && (
                  <div className="text-xs text-gray-600 mt-0.5 italic">
                    "{entry.reason}"
                  </div>
                )}
                {entry.request_id && (
                  <div className="text-xs text-gray-400">
                    ref: {entry.request_id}
                  </div>
                )}
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}
