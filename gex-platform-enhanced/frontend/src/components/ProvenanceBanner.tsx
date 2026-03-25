/**
 * ProvenanceBanner — R4 (Architectural Reform v6.0)
 *
 * Non-removable provenance disclosure rendered at the top of:
 *   - Banker's Snapshot (BankersSnapshot.tsx)
 *   - IC Pack export (ICPackBuilder.tsx)
 *   - CFO Report (CFOReport.tsx)
 *   - Any document in EXPORTED or SHARED_EXTERNAL state
 *
 * This is document content, not a UI overlay.
 * It cannot be toggled off. It travels with the document on print/export.
 */

import { FileWarning, ShieldCheck, ShieldOff, User } from 'lucide-react'
import type { VerificationState } from './VerificationBadge'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface EvidenceSummary {
  UNVERIFIED: number
  SUBMITTED:  number
  CONFIRMED:  number
  AUDITED:    number
}

export interface ProvenanceBannerProps {
  projectName:    string
  companyName:    string
  evidenceSummary: EvidenceSummary
  reviewerName:   string
  reviewerTitle:  string
  reviewScope:    'FULL_REVIEW' | 'SPOT_CHECK' | 'METHODOLOGY_ONLY'
  reviewDate:     string
  generatedAt?:   string
}

const SCOPE_LABELS: Record<ProvenanceBannerProps['reviewScope'], string> = {
  FULL_REVIEW:       'Full review',
  SPOT_CHECK:        'Spot check',
  METHODOLOGY_ONLY:  'Methodology only',
}

// ─── Component ────────────────────────────────────────────────────────────────

export function ProvenanceBanner({
  projectName,
  companyName,
  evidenceSummary,
  reviewerName,
  reviewerTitle,
  reviewScope,
  reviewDate,
  generatedAt,
}: ProvenanceBannerProps) {
  const total =
    evidenceSummary.UNVERIFIED +
    evidenceSummary.SUBMITTED +
    evidenceSummary.CONFIRMED +
    evidenceSummary.AUDITED

  const verifiedPct = total > 0
    ? Math.round(((evidenceSummary.CONFIRMED + evidenceSummary.AUDITED) / total) * 100)
    : 0

  const displayDate = generatedAt
    ? new Date(generatedAt).toLocaleString('en-GB', {
        day: '2-digit', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit', timeZoneName: 'short',
      })
    : new Date().toLocaleString('en-GB', {
        day: '2-digit', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit', timeZoneName: 'short',
      })

  return (
    <div className="w-full border border-gray-300 rounded-lg bg-gray-50 text-xs print:border-gray-400 print:bg-white">
      {/* Header bar */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-gray-300 bg-gray-100 rounded-t-lg">
        <FileWarning className="w-3.5 h-3.5 text-gray-500 flex-shrink-0" />
        <span className="font-bold text-gray-600 uppercase tracking-wide text-[10px]">
          Provenance Disclosure — GreenEarthX Platform
        </span>
        <span className="ml-auto text-gray-400 text-[10px]">{displayDate}</span>
      </div>

      <div className="px-4 py-3 grid grid-cols-2 gap-x-6 gap-y-1.5">
        {/* Left: project & review info */}
        <div className="space-y-1">
          <Row label="Project" value={projectName} />
          <Row label="Company" value={companyName} />
          <div className="pt-1 border-t border-gray-200 mt-1">
            <div className="flex items-center gap-1 text-gray-500 mb-0.5">
              <User className="w-3 h-3" />
              <span className="font-semibold text-gray-600">Reviewed by</span>
            </div>
            <Row label="Name"  value={reviewerName} />
            <Row label="Title" value={reviewerTitle} />
            <Row label="Scope" value={SCOPE_LABELS[reviewScope]} />
            <Row label="Date"  value={reviewDate} />
          </div>
        </div>

        {/* Right: evidence verification summary */}
        <div className="space-y-1">
          <p className="font-semibold text-gray-600 mb-1">
            Evidence at time of export
          </p>
          <EvidenceRow state="AUDITED"    count={evidenceSummary.AUDITED}    weight="×1.00" color="text-green-700" />
          <EvidenceRow state="CONFIRMED"  count={evidenceSummary.CONFIRMED}  weight="×0.85" color="text-blue-700" />
          <EvidenceRow state="SUBMITTED"  count={evidenceSummary.SUBMITTED}  weight="×0.50" color="text-amber-700" />
          <EvidenceRow state="UNVERIFIED" count={evidenceSummary.UNVERIFIED} weight="×0.25" color="text-gray-500" />
          <div className="pt-1 border-t border-gray-200 mt-1 flex items-center gap-1.5">
            {verifiedPct >= 80
              ? <ShieldCheck className="w-3 h-3 text-green-600" />
              : <ShieldOff   className="w-3 h-3 text-amber-500" />
            }
            <span className={`font-semibold ${verifiedPct >= 80 ? 'text-green-700' : 'text-amber-600'}`}>
              {verifiedPct}% at CONFIRMED or above
            </span>
          </div>
        </div>
      </div>

      {/* Mandatory notice */}
      <div className="px-4 py-2 border-t border-gray-300 bg-gray-100 rounded-b-lg">
        <p className="text-[10px] text-gray-500 leading-relaxed">
          <span className="font-semibold text-gray-600">NOTICE:</span>{' '}
          This document was generated by the GreenEarthX platform using data submitted by the project
          company. It has not been independently verified beyond the evidence states shown above.
          It is not a substitute for institution-specific credit analysis or independent due diligence.
          Distribution is subject to the receiving institution's policies.
        </p>
      </div>
    </div>
  )
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <span className="w-14 flex-shrink-0 text-gray-400">{label}</span>
      <span className="text-gray-700 font-medium">{value}</span>
    </div>
  )
}

function EvidenceRow({
  state, count, weight, color,
}: {
  state: VerificationState
  count: number
  weight: string
  color: string
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-20 text-gray-500">{state}</span>
      <span className={`font-semibold tabular-nums w-6 text-right ${color}`}>{count}</span>
      <span className="text-gray-400 font-mono text-[10px]">{weight}</span>
    </div>
  )
}
