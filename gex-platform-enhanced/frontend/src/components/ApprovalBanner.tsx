// Screen: Shared component — Approval queue screen, Finance screens
/**
 * ApprovalBanner — displayed when a backend action returns HTTP 202 (PENDING_APPROVAL).
 * Renders an amber notice with the request_id and required approvers.
 * Embedding: wrap any form submit with the WAE response check and pass pending data here.
 */
import { Clock, Users, CheckCircle, XCircle } from 'lucide-react'

interface ApprovalPendingData {
  request_id: string
  action_type: string
  status: 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED'
  required_roles?: string[]
  min_approvers?: number
  approvals_received?: number
  expires_at?: string
  message?: string
}

interface Props {
  pending: ApprovalPendingData | null
  onDismiss?: () => void
}

export function ApprovalBanner({ pending, onDismiss }: Props) {
  if (!pending) return null

  const isApproved = pending.status === 'APPROVED'
  const isRejected = pending.status === 'REJECTED'
  const isPending = pending.status === 'PENDING_APPROVAL'

  const bgClass = isApproved
    ? 'bg-green-50 border-green-400'
    : isRejected
    ? 'bg-red-50 border-red-400'
    : 'bg-amber-50 border-amber-400'

  const iconClass = isApproved
    ? 'text-green-600'
    : isRejected
    ? 'text-red-600'
    : 'text-amber-600'

  return (
    <div className={`border rounded-lg p-4 mb-4 ${bgClass}`}>
      <div className="flex items-start gap-3">
        <div className={`mt-0.5 ${iconClass}`}>
          {isApproved ? (
            <CheckCircle size={20} />
          ) : isRejected ? (
            <XCircle size={20} />
          ) : (
            <Clock size={20} />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className={`font-semibold text-sm ${iconClass}`}>
            {isApproved
              ? 'Action approved'
              : isRejected
              ? 'Action rejected'
              : 'Approval required — action queued'}
          </div>
          <div className="text-sm text-gray-700 mt-1">
            {pending.message ||
              (isPending
                ? `This action (${pending.action_type}) requires multi-party approval before it can proceed.`
                : `Decision recorded for ${pending.action_type}.`)}
          </div>
          <div className="mt-2 flex flex-wrap gap-3 text-xs text-gray-600">
            <span>
              <span className="font-medium">Request ID:</span>{' '}
              <code className="bg-white/60 px-1 rounded">{pending.request_id}</code>
            </span>
            {pending.required_roles && pending.required_roles.length > 0 && (
              <span className="flex items-center gap-1">
                <Users size={12} />
                Required roles: {pending.required_roles.join(', ')}
              </span>
            )}
            {pending.min_approvers != null && (
              <span>
                {pending.approvals_received ?? 0} / {pending.min_approvers} approvers
              </span>
            )}
            {pending.expires_at && (
              <span>
                Expires: {new Date(pending.expires_at).toLocaleString()}
              </span>
            )}
          </div>
        </div>
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="text-gray-400 hover:text-gray-600 text-xs shrink-0"
            title="Dismiss"
          >
            ✕
          </button>
        )}
      </div>
    </div>
  )
}
