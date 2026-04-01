/**
 * WorkflowActions — context-aware action buttons based on workflow state.
 * Surfaces the correct controls to each role at each state transition.
 *
 * R3: "Mark Reviewed" now opens a modal requiring reviewer name, title,
 * and review scope. Transition to REVIEWED is blocked until all fields
 * are populated. This enforces named accountability for reviewed outputs.
 */
import { useEffect, useState } from 'react'
import { AlertTriangle, ChevronRight, FileText, FileJson, FileType, Lock, XCircle, UserCheck } from 'lucide-react'
import type { WorkflowState } from './WorkflowBadge'
import { workflowAPI, type WorkflowPromotionGate } from '@/lib/workflowApi'

// ─────────────────────────────── Types ───────────────────────────────────────

export interface ReviewerDetails {
  reviewerName: string
  reviewerTitle: string
  reviewScope: 'FULL_REVIEW' | 'SPOT_CHECK' | 'METHODOLOGY_ONLY'
}

interface WorkflowActionsProps {
  state: WorkflowState
  objectType: string
  onAdvance?: (toState: WorkflowState, reviewer?: ReviewerDetails) => void
  onExport?: (format: 'pdf' | 'json' | 'word') => void
  onReject?: (reason: string) => void
  userRole?: 'analyst' | 'cfo' | 'viewer'
  projectId?: string
  workflowObjectType?: string
  workflowObjectId?: string
}

// ─────────────────────────────── Helpers ─────────────────────────────────────

function DisabledExportButton({ label, icon: Icon }: { label: string; icon: React.ElementType }) {
  return (
    <div className="relative group">
      <button
        disabled
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 bg-gray-50 text-gray-400 text-xs font-semibold cursor-not-allowed select-none"
      >
        <Lock className="w-3 h-3" />
        <Icon className="w-3 h-3" />
        {label}
      </button>
      {/* Tooltip */}
      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block z-10 whitespace-nowrap">
        <div className="bg-gray-900 text-white text-xs rounded-md px-2.5 py-1.5 shadow-lg">
          Requires approval before export
        </div>
        <div className="w-2 h-2 bg-gray-900 rotate-45 mx-auto -mt-1" />
      </div>
    </div>
  )
}

// ─────────────────────────────── Component ───────────────────────────────────

export function WorkflowActions({
  state,
  objectType,
  onAdvance,
  onExport,
  onReject,
  userRole = 'viewer',
  projectId,
  workflowObjectType,
  workflowObjectId,
}: WorkflowActionsProps) {
  const [showRejectBox, setShowRejectBox] = useState(false)
  const [rejectReason, setRejectReason] = useState('')
  const [workflowGate, setWorkflowGate] = useState<WorkflowPromotionGate | null>(null)
  const [gateLoading, setGateLoading] = useState(false)

  // R3: Reviewer modal state
  const [showReviewerModal, setShowReviewerModal] = useState(false)
  const [reviewerName, setReviewerName]   = useState('')
  const [reviewerTitle, setReviewerTitle] = useState('')
  const [reviewScope, setReviewScope]     = useState<ReviewerDetails['reviewScope']>('FULL_REVIEW')

  useEffect(() => {
    if (!projectId || !workflowObjectType || !workflowObjectId) {
      setWorkflowGate(null)
      setGateLoading(false)
      return
    }

    let active = true
    setGateLoading(true)

    workflowAPI.getState(workflowObjectType, workflowObjectId, projectId)
      .then((data) => {
        if (!active) return
        setWorkflowGate({
          project_id: data.project_id,
          blocked: data.promotion_blocked,
          blocking_findings: data.blocking_findings,
          blocking_reviews: data.blocking_reviews,
          critical_findings: data.critical_findings,
          summary: data.promotion_gate_summary,
          blocking_titles: data.blocking_titles,
          blockers: data.blockers,
        })
      })
      .catch(() => {
        if (!active) return
        setWorkflowGate(null)
      })
      .finally(() => {
        if (!active) return
        setGateLoading(false)
      })

    return () => {
      active = false
    }
  }, [projectId, workflowObjectId, workflowObjectType])

  const canWriteOrReview = userRole === 'analyst' || userRole === 'cfo'
  const isCfo = userRole === 'cfo'
  const isApproved = state === 'APPROVED' || state === 'EXPORTED' || state === 'SHARED_EXTERNAL'
  const promotionBlocked = workflowGate?.blocked ?? false
  const disablePromotions = gateLoading || promotionBlocked

  function handleAdvance(toState: WorkflowState, reviewer?: ReviewerDetails) {
    if (disablePromotions) return
    window.alert(`Demo: advancing ${objectType} state to ${toState}`)
    onAdvance?.(toState, reviewer)
  }

  // R3: Submit reviewer details before marking REVIEWED
  function handleReviewerSubmit() {
    if (!reviewerName.trim() || !reviewerTitle.trim()) return
    handleAdvance('REVIEWED', {
      reviewerName:  reviewerName.trim(),
      reviewerTitle: reviewerTitle.trim(),
      reviewScope,
    })
    setShowReviewerModal(false)
    setReviewerName('')
    setReviewerTitle('')
    setReviewScope('FULL_REVIEW')
  }

  function handleExport(format: 'pdf' | 'json' | 'word') {
    if (disablePromotions) return
    window.alert(`Demo: exporting ${objectType} as ${format.toUpperCase()}`)
    onExport?.(format)
  }

  function handleRejectSubmit() {
    const reason = rejectReason.trim()
    window.alert(`Demo: rejecting ${objectType}. Reason: "${reason || '(none)'}"`)
    onReject?.(reason)
    setShowRejectBox(false)
    setRejectReason('')
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        {/* ── COMPUTED: analyst / cfo can mark reviewed (R3: requires reviewer modal) ── */}
        {state === 'COMPUTED' && canWriteOrReview && (
          <button
            onClick={() => setShowReviewerModal(true)}
            disabled={disablePromotions}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-amber-300 bg-amber-50 text-amber-700 text-xs font-semibold hover:bg-amber-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <UserCheck className="w-3.5 h-3.5" />
            Mark Reviewed
          </button>
        )}

        {/* ── REVIEWED: cfo can approve or reject ── */}
        {state === 'REVIEWED' && isCfo && (
          <>
            <button
              onClick={() => handleAdvance('APPROVED')}
              disabled={disablePromotions}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-green-300 bg-green-50 text-green-700 text-xs font-semibold hover:bg-green-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <ChevronRight className="w-3.5 h-3.5" />
              Approve
            </button>
            <button
              onClick={() => setShowRejectBox(v => !v)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-300 bg-red-50 text-red-600 text-xs font-semibold hover:bg-red-100 transition-colors"
            >
              <XCircle className="w-3.5 h-3.5" />
              Reject
            </button>
          </>
        )}

        {/* ── Export buttons ── */}
        {isApproved && !disablePromotions ? (
          <>
            <button
              onClick={() => handleExport('pdf')}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-300 bg-white text-gray-700 text-xs font-semibold hover:bg-gray-50 transition-colors"
            >
              <FileType className="w-3.5 h-3.5 text-red-500" />
              Export PDF
            </button>
            <button
              onClick={() => handleExport('json')}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-300 bg-white text-gray-700 text-xs font-semibold hover:bg-gray-50 transition-colors"
            >
              <FileJson className="w-3.5 h-3.5 text-blue-500" />
              Export JSON
            </button>
            <button
              onClick={() => handleExport('word')}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-300 bg-white text-gray-700 text-xs font-semibold hover:bg-gray-50 transition-colors"
            >
              <FileText className="w-3.5 h-3.5 text-indigo-500" />
              Export Word
            </button>
          </>
        ) : (
          <>
            <DisabledExportButton label="Export PDF" icon={FileType} />
            <DisabledExportButton label="Export JSON" icon={FileJson} />
            <DisabledExportButton label="Export Word" icon={FileText} />
          </>
        )}
      </div>

      {promotionBlocked && workflowGate && (
        <div className="max-w-2xl rounded-lg border border-red-200 bg-red-50 px-3 py-3 text-xs text-red-800">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
            <div className="space-y-1">
              <p className="font-semibold">
                {workflowGate.summary || 'Promotion is blocked by open adversarial findings.'}
              </p>
              <p>
                Resolve or waive the blocking review items before promoting this workflow artifact.
              </p>
              {workflowGate.blocking_titles.slice(0, 3).map((title) => (
                <p key={title} className="text-red-700">
                  - {title}
                </p>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Inline rejection textarea ── */}
      {showRejectBox && state === 'REVIEWED' && isCfo && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 space-y-2 max-w-sm">
          <p className="text-xs font-semibold text-red-700">Rejection reason</p>
          <textarea
            className="w-full text-xs rounded-md border border-red-300 bg-white px-2.5 py-1.5 text-gray-800 resize-none focus:outline-none focus:ring-2 focus:ring-red-300"
            rows={3}
            placeholder="Describe the issue that must be addressed before approval…"
            value={rejectReason}
            onChange={e => setRejectReason(e.target.value)}
          />
          <div className="flex gap-2">
            <button
              onClick={handleRejectSubmit}
              className="px-3 py-1 rounded-md bg-red-600 text-white text-xs font-semibold hover:bg-red-700 transition-colors"
            >
              Confirm Rejection
            </button>
            <button
              onClick={() => { setShowRejectBox(false); setRejectReason('') }}
              className="px-3 py-1 rounded-md border border-red-300 text-red-600 text-xs font-semibold hover:bg-red-100 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* ── R3: Named reviewer modal ── */}
      {showReviewerModal && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 space-y-3 max-w-sm">
          <div className="flex items-center gap-2">
            <UserCheck className="w-4 h-4 text-amber-600" />
            <p className="text-xs font-bold text-amber-800">Reviewer identification required</p>
          </div>
          <p className="text-xs text-amber-700">
            Marking as Reviewed creates an accountable record. The reviewer's name and title
            will appear on all generated documents and cannot be changed after submission.
          </p>

          <div className="space-y-2">
            <div>
              <label className="block text-xs font-semibold text-amber-800 mb-0.5">
                Reviewer name <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                placeholder="e.g. Dr. Sarah Müller"
                value={reviewerName}
                onChange={e => setReviewerName(e.target.value)}
                className="w-full text-xs rounded-md border border-amber-300 bg-white px-2.5 py-1.5 text-gray-800 focus:outline-none focus:ring-2 focus:ring-amber-300"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-amber-800 mb-0.5">
                Reviewer title <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                placeholder="e.g. Head of Project Finance"
                value={reviewerTitle}
                onChange={e => setReviewerTitle(e.target.value)}
                className="w-full text-xs rounded-md border border-amber-300 bg-white px-2.5 py-1.5 text-gray-800 focus:outline-none focus:ring-2 focus:ring-amber-300"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-amber-800 mb-0.5">
                Review scope <span className="text-red-500">*</span>
              </label>
              <select
                value={reviewScope}
                onChange={e => setReviewScope(e.target.value as ReviewerDetails['reviewScope'])}
                className="w-full text-xs rounded-md border border-amber-300 bg-white px-2.5 py-1.5 text-gray-800 focus:outline-none focus:ring-2 focus:ring-amber-300"
              >
                <option value="FULL_REVIEW">Full review</option>
                <option value="SPOT_CHECK">Spot check</option>
                <option value="METHODOLOGY_ONLY">Methodology only</option>
              </select>
            </div>
          </div>

          <div className="flex gap-2 pt-1">
            <button
              onClick={handleReviewerSubmit}
              disabled={!reviewerName.trim() || !reviewerTitle.trim()}
              className="px-3 py-1.5 rounded-md bg-amber-600 text-white text-xs font-semibold hover:bg-amber-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Confirm Review
            </button>
            <button
              onClick={() => setShowReviewerModal(false)}
              className="px-3 py-1.5 rounded-md border border-amber-300 text-amber-700 text-xs font-semibold hover:bg-amber-100 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
