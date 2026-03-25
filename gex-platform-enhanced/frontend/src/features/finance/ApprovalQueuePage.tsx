/**
 * ApprovalQueuePage — WAE pending approvals table.
 * Used in both Finance and Executive workspaces.
 * Shows PENDING requests; lets authorised users APPROVE or REJECT.
 *
 * Backend: GET /api/v1/approvals/pending
 *          POST /api/v1/approvals/{id}/decide
 */
import { useState, useEffect } from 'react'
import { CheckCircle, XCircle, Clock, ChevronDown, ChevronUp, AlertCircle } from 'lucide-react'
import { approvalsAPI } from '@/api'

interface ApprovalRequest {
  id: string
  action_type: string
  project_id: string
  initiator_user_id: string
  status: string
  required_roles: string[]
  min_approvers: number
  approvals_received?: number
  payload_json?: Record<string, any>
  created_at: string
  expires_at?: string
}

const ACTION_LABELS: Record<string, string> = {
  SAF_FORWARD_SALE: 'SAF Forward Sale',
  PPA_EXECUTION: 'PPA Execution',
  FINANCING_DRAWDOWN: 'Financing Drawdown',
  INSURANCE_PLACEMENT: 'Insurance Placement',
  EPC_MILESTONE_PAYMENT: 'EPC Milestone Payment',
  CERTIFICATE_APPLICATION: 'Certificate Application',
  EVIDENCE_EXPORT: 'Evidence Export',
  COUNTERPARTY_NDA: 'Counterparty NDA',
}

const DEMO_REQUESTS: ApprovalRequest[] = [
  {
    id: 'req-001',
    action_type: 'SAF_FORWARD_SALE',
    project_id: 'proj_breizh_saf',
    initiator_user_id: 'usr_bp_01',
    status: 'PENDING',
    required_roles: ['RISK_OFFICER', 'TREASURY_HEAD'],
    min_approvers: 2,
    approvals_received: 1,
    payload_json: { volume_t: 10000, price_eur_t: 2200, counterparty: 'Air France KLM', tenor_months: 24 },
    created_at: '2026-03-16T08:30:00Z',
    expires_at: '2026-03-17T08:30:00Z',
  },
  {
    id: 'req-002',
    action_type: 'FINANCING_DRAWDOWN',
    project_id: 'proj_wales_saf',
    initiator_user_id: 'usr_bp_02',
    status: 'PENDING',
    required_roles: ['RISK_OFFICER', 'CFO', 'LEGAL_COUNSEL'],
    min_approvers: 3,
    approvals_received: 0,
    payload_json: { amount_eur: 45000000, facility: 'ING Green Infrastructure Loan', tranche: 'A' },
    created_at: '2026-03-15T14:00:00Z',
    expires_at: '2026-03-16T14:00:00Z',
  },
  {
    id: 'req-003',
    action_type: 'PPA_EXECUTION',
    project_id: 'proj_rotterdam_nh3',
    initiator_user_id: 'usr_bp_03',
    status: 'PENDING',
    required_roles: ['COMMERCIAL_LEAD', 'RISK_OFFICER'],
    min_approvers: 2,
    approvals_received: 2,
    payload_json: { energy_mwh: 50000, price_eur_mwh: 68, supplier: 'Ørsted A/S', years: 10 },
    created_at: '2026-03-14T10:00:00Z',
    expires_at: '2026-03-21T10:00:00Z',
  },
]

export function ApprovalQueuePage() {
  const [requests, setRequests] = useState<ApprovalRequest[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [deciding, setDeciding] = useState<string | null>(null)
  const [reasonText, setReasonText] = useState('')
  const [toast, setToast] = useState<{ type: 'success' | 'error'; msg: string } | null>(null)

  useEffect(() => {
    approvalsAPI.getPending()
      .then((data) => {
        setRequests(data.requests || [])
        setLoading(false)
      })
      .catch(() => {
        setRequests(DEMO_REQUESTS)
        setLoading(false)
        setError('Backend offline — showing demo queue')
      })
  }, [])

  const handleDecide = async (requestId: string, decision: 'APPROVE' | 'REJECT') => {
    setDeciding(requestId)
    try {
      await approvalsAPI.decide(requestId, {
        approver_user_id: 'usr_current_user',
        decision,
        reason_text: reasonText || undefined,
      })
      setRequests((prev) => prev.filter((r) => r.id !== requestId))
      setToast({ type: 'success', msg: `Request ${requestId} ${decision.toLowerCase()}d` })
      setTimeout(() => setToast(null), 4000)
    } catch (e: any) {
      setToast({ type: 'error', msg: e.message || 'Decision failed' })
      setTimeout(() => setToast(null), 4000)
    } finally {
      setDeciding(null)
      setExpanded(null)
      setReasonText('')
    }
  }

  const isExpired = (expiresAt?: string) =>
    expiresAt ? new Date(expiresAt) < new Date() : false

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Approval Queue</h1>
          <p className="text-sm text-gray-500 mt-1">
            Multi-party approvals required before binding commitments are executed (WAE Domain 1)
          </p>
        </div>
        <div className="text-sm bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
          <span className="font-semibold text-amber-800">{requests.length}</span>
          <span className="text-amber-700"> pending</span>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded p-3 mb-4">
          <AlertCircle size={16} />
          {error}
        </div>
      )}

      {toast && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg text-white text-sm ${
          toast.type === 'success' ? 'bg-green-600' : 'bg-red-600'
        }`}>
          {toast.msg}
        </div>
      )}

      {loading ? (
        <div className="text-center py-12 text-gray-400">Loading approvals…</div>
      ) : requests.length === 0 ? (
        <div className="text-center py-12 border-2 border-dashed border-gray-200 rounded-lg">
          <CheckCircle size={32} className="mx-auto text-green-400 mb-3" />
          <p className="text-gray-500">No pending approvals</p>
        </div>
      ) : (
        <div className="space-y-3">
          {requests.map((req) => {
            const expired = isExpired(req.expires_at)
            const quorumMet = (req.approvals_received ?? 0) >= req.min_approvers

            return (
              <div
                key={req.id}
                className={`border rounded-lg ${expired ? 'border-red-200 bg-red-50/30' : 'border-gray-200 bg-white'}`}
              >
                {/* Header row */}
                <div
                  className="flex items-center gap-4 p-4 cursor-pointer"
                  onClick={() => setExpanded(expanded === req.id ? null : req.id)}
                >
                  <div className={`w-2 h-2 rounded-full shrink-0 ${
                    expired ? 'bg-red-400' : quorumMet ? 'bg-green-400' : 'bg-amber-400'
                  }`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-gray-900 text-sm">
                        {ACTION_LABELS[req.action_type] || req.action_type}
                      </span>
                      <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded">
                        {req.project_id}
                      </span>
                      {expired && (
                        <span className="text-xs text-red-600 bg-red-100 px-2 py-0.5 rounded">
                          EXPIRED
                        </span>
                      )}
                      {quorumMet && !expired && (
                        <span className="text-xs text-green-700 bg-green-100 px-2 py-0.5 rounded">
                          Quorum met
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-gray-500 mt-0.5">
                      Initiated by {req.initiator_user_id} ·{' '}
                      {new Date(req.created_at).toLocaleString()}
                    </div>
                  </div>
                  <div className="text-xs text-gray-500 text-right shrink-0">
                    <div className="flex items-center gap-1">
                      <Clock size={12} />
                      {req.approvals_received ?? 0}/{req.min_approvers}
                    </div>
                  </div>
                  <div className="text-gray-400 shrink-0">
                    {expanded === req.id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </div>
                </div>

                {/* Expanded detail */}
                {expanded === req.id && (
                  <div className="border-t border-gray-100 p-4 space-y-4">
                    {/* Payload */}
                    {req.payload_json && (
                      <div>
                        <div className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
                          Action Payload
                        </div>
                        <div className="bg-gray-50 rounded p-3 text-xs font-mono text-gray-700 space-y-1">
                          {Object.entries(req.payload_json).map(([k, v]) => (
                            <div key={k}>
                              <span className="text-gray-400">{k}: </span>
                              <span>{String(v)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Required roles */}
                    <div>
                      <div className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
                        Required Approvers ({req.approvals_received ?? 0}/{req.min_approvers})
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {req.required_roles.map((role) => (
                          <span
                            key={role}
                            className="text-xs bg-blue-50 text-blue-700 px-2 py-1 rounded"
                          >
                            {role}
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* Decision controls */}
                    {!expired && (
                      <div className="space-y-2">
                        <textarea
                          className="w-full text-sm border border-gray-200 rounded p-2 resize-none"
                          rows={2}
                          placeholder="Optional reason / comment…"
                          value={reasonText}
                          onChange={(e) => setReasonText(e.target.value)}
                        />
                        <div className="flex gap-2">
                          <button
                            onClick={() => handleDecide(req.id, 'APPROVE')}
                            disabled={deciding === req.id}
                            className="flex items-center gap-1.5 px-4 py-2 bg-green-600 text-white text-sm rounded hover:bg-green-700 disabled:opacity-50"
                          >
                            <CheckCircle size={14} />
                            Approve
                          </button>
                          <button
                            onClick={() => handleDecide(req.id, 'REJECT')}
                            disabled={deciding === req.id}
                            className="flex items-center gap-1.5 px-4 py-2 bg-red-600 text-white text-sm rounded hover:bg-red-700 disabled:opacity-50"
                          >
                            <XCircle size={14} />
                            Reject
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      <div className="mt-6 text-xs text-gray-400 border-t pt-4">
        WAE — Workflow Authorization Engine · Domain 1 ·
        Decisions are non-deletable and CSS-signed after quorum is reached
      </div>
    </div>
  )
}
