/**
 * TermSheetTracker — Tracks convergence of commercial terms (Playbook Annex B checklist).
 * Shows which terms are agreed, pending, or disputed grouped by category.
 */

import { useState } from 'react'
import {
  FileSignature, CheckCircle2, Clock, AlertTriangle, Plus, Filter,
} from 'lucide-react'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { CUSTOMER_PROJECTS } from '@/data/customerProjects'
import { WorkflowBadge } from '@/components/workflow/WorkflowBadge'
import { WorkflowActions } from '@/components/workflow/WorkflowActions'

// ─────────────────────────────── Types ───────────────────────────────────────

type TermStatus = 'AGREED' | 'PENDING' | 'DISPUTED'
type Party = 'Buyer' | 'Seller' | 'Both'

interface TermItem {
  group: string
  term: string
  status: TermStatus
  party: Party
  lastUpdated: string
  notes: string
}

// ─────────────────────────────── Data ────────────────────────────────────────

function buildTerms(projectId: string): TermItem[] {
  const isLeHavre = projectId === 'proj_lehavre_eng'
  const isBremen = projectId === 'proj_bremen_h2'

  function t(
    group: string,
    term: string,
    leHavre: TermStatus,
    bremen: TermStatus,
    other: TermStatus,
    party: Party,
    lastUpdated: string,
    notes: string,
  ): TermItem {
    const status = isLeHavre ? leHavre : isBremen ? bremen : other
    return { group, term, status, party, lastUpdated, notes }
  }

  return [
    // Financial Terms
    t('Financial Terms', 'Pricing & Indexation', 'AGREED', 'AGREED', 'PENDING',
      'Both', '2026-02-14', 'CPI-linked with 3% cap. Annual reset in Q1.'),
    t('Financial Terms', 'Floor price mechanism', 'AGREED', 'AGREED', 'PENDING',
      'Seller', '2026-02-14', 'Floor at €55/MWh H2-equiv. Escalates 1.5%/yr.'),
    t('Financial Terms', 'Price cap', 'AGREED', 'PENDING', 'PENDING',
      'Buyer', '2026-01-20', 'Cap at €120/MWh. Buyer requesting €110 — under review.'),
    t('Financial Terms', 'Escalation formula', 'AGREED', 'DISPUTED', 'PENDING',
      'Both', '2025-12-05', 'Dispute: Seller prefers HHPPI; Buyer insists on CPI only.'),

    // Delivery Terms
    t('Delivery Terms', 'Volume commitment (ToP %)', 'AGREED', 'AGREED', 'PENDING',
      'Buyer', '2026-02-28', '85% take-or-pay over contract year.'),
    t('Delivery Terms', 'Make-good clause', 'AGREED', 'PENDING', 'PENDING',
      'Seller', '2025-11-30', 'Make-good window: 6 months post-shortfall event.'),
    t('Delivery Terms', 'Outage protocol', 'AGREED', 'PENDING', 'PENDING',
      'Both', '2025-12-10', 'Force-majeure outages excluded from ToP obligation.'),
    t('Delivery Terms', 'Delivery point', 'AGREED', 'AGREED', 'PENDING',
      'Both', '2026-01-08', 'Gate delivery at grid injection point / custody meter.'),

    // Risk Allocation
    t('Risk Allocation', 'Force majeure definition', 'AGREED', 'AGREED', 'DISPUTED',
      'Both', '2026-02-01', 'Includes grid curtailment >20% for >15 consecutive days.'),
    t('Risk Allocation', 'Change-in-law clause', 'AGREED', 'PENDING', 'PENDING',
      'Both', '2025-11-15', 'Full pass-through to Buyer if direct regulatory impact.'),
    t('Risk Allocation', 'Curtailment compensation', 'AGREED', 'DISPUTED', 'PENDING',
      'Seller', '2026-01-25', 'Seller claims 100% TOTSA compensation; under negotiation.'),
    t('Risk Allocation', 'Environmental indemnity', 'AGREED', 'PENDING', 'PENDING',
      'Seller', '2025-10-20', 'Covers soil contamination attributable to construction.'),

    // Security Package
    t('Security Package', 'Step-in rights', 'AGREED', 'AGREED', 'PENDING',
      'Buyer', '2026-02-10', 'Lender step-in triggered at 90-day payment default.'),
    t('Security Package', 'Cut-through provisions', 'AGREED', 'PENDING', 'PENDING',
      'Both', '2025-12-18', 'Direct agreement with senior lender pending legal sign-off.'),
    t('Security Package', 'Assignment consent', 'AGREED', 'PENDING', 'PENDING',
      'Both', '2026-01-12', 'Consent not to be unreasonably withheld within 20 business days.'),
    t('Security Package', 'Charge over accounts', 'AGREED', 'AGREED', 'PENDING',
      'Buyer', '2026-02-20', 'DSRA and Revenue account charged in favour of lender group.'),

    // Operational
    t('Operational', 'M&V protocol', 'AGREED', 'AGREED', 'PENDING',
      'Both', '2026-03-01', 'ISO 50006 metering. Quarterly reconciliation by independent auditor.'),
    t('Operational', 'Audit rights', 'AGREED', 'PENDING', 'PENDING',
      'Buyer', '2025-11-28', 'Buyer right to audit books 30 days per year with 10-day notice.'),
    t('Operational', 'Regulatory reporting', 'AGREED', 'AGREED', 'PENDING',
      'Seller', '2026-02-05', 'Monthly RFNBO compliance report to competent authority.'),
  ]
}

// ─────────────────────────────── Status helpers ───────────────────────────────

function statusBadge(status: TermStatus) {
  switch (status) {
    case 'AGREED':
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-green-100 border border-green-300 text-green-700 text-xs font-semibold">
          <CheckCircle2 className="w-3 h-3" /> AGREED
        </span>
      )
    case 'PENDING':
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-100 border border-amber-300 text-amber-700 text-xs font-semibold">
          <Clock className="w-3 h-3" /> PENDING
        </span>
      )
    case 'DISPUTED':
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-red-100 border border-red-300 text-red-700 text-xs font-semibold">
          <AlertTriangle className="w-3 h-3" /> DISPUTED
        </span>
      )
  }
}

// ─────────────────────────────── Component ───────────────────────────────────

const TERM_GROUPS = [
  'Financial Terms',
  'Delivery Terms',
  'Risk Allocation',
  'Security Package',
  'Operational',
]

export function TermSheetTracker() {
  const { selectedProjectId } = useSelectedProject()
  const project = CUSTOMER_PROJECTS.find(p => p.id === selectedProjectId) ?? CUSTOMER_PROJECTS[0]
  const [filterStatus, setFilterStatus] = useState<TermStatus | 'ALL'>('ALL')

  const allTerms = buildTerms(project.id)
  const agreedCount = allTerms.filter(t => t.status === 'AGREED').length
  const pendingCount = allTerms.filter(t => t.status === 'PENDING').length
  const disputedCount = allTerms.filter(t => t.status === 'DISPUTED').length

  const filtered = filterStatus === 'ALL' ? allTerms : allTerms.filter(t => t.status === filterStatus)

  return (
    <div className="space-y-5 animate-fade-in">

      {/* ── Header ── */}
      <div className="flex flex-wrap items-start justify-between gap-4 rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-6 py-4 shadow-card">
        <div>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="font-display text-2xl font-bold text-[var(--text-primary)] flex items-center gap-2">
              <FileSignature className="w-6 h-6 text-[var(--brand)]" />
              Term Sheet Tracker
            </h1>
            <WorkflowBadge state="DRAFT" />
          </div>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">{project.name} · Playbook Annex B Checklist</p>
        </div>
        <WorkflowActions state="DRAFT" objectType="Term Sheet" userRole="analyst" />
      </div>

      {/* ── Summary bar ── */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-5 py-4 shadow-card">
        <div className="flex items-center gap-6 mb-3">
          <div className="flex items-center gap-2">
            <span className="inline-block w-3 h-3 rounded-full bg-green-500" />
            <span className="text-sm font-semibold text-[var(--text-primary)]">Agreed <span className="text-green-600">{agreedCount}</span></span>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-block w-3 h-3 rounded-full bg-amber-400" />
            <span className="text-sm font-semibold text-[var(--text-primary)]">Pending <span className="text-amber-600">{pendingCount}</span></span>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-block w-3 h-3 rounded-full bg-red-500" />
            <span className="text-sm font-semibold text-[var(--text-primary)]">Disputed <span className="text-red-600">{disputedCount}</span></span>
          </div>
        </div>
        {/* Segmented bar */}
        <div className="flex h-2.5 rounded-full overflow-hidden gap-0.5">
          {agreedCount > 0 && (
            <div
              className="bg-green-500 rounded-l-full transition-all duration-700"
              style={{ width: `${(agreedCount / allTerms.length) * 100}%` }}
            />
          )}
          {pendingCount > 0 && (
            <div
              className="bg-amber-400 transition-all duration-700"
              style={{ width: `${(pendingCount / allTerms.length) * 100}%` }}
            />
          )}
          {disputedCount > 0 && (
            <div
              className="bg-red-500 rounded-r-full transition-all duration-700"
              style={{ width: `${(disputedCount / allTerms.length) * 100}%` }}
            />
          )}
        </div>
        <p className="mt-2 text-xs text-[var(--text-muted)]">{allTerms.length} terms total</p>
      </div>

      {/* ── Controls ── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-[var(--text-muted)]" />
          <span className="text-xs text-[var(--text-muted)] font-semibold uppercase tracking-[0.1em]">Filter</span>
          {(['ALL', 'AGREED', 'PENDING', 'DISPUTED'] as const).map(s => (
            <button
              key={s}
              onClick={() => setFilterStatus(s)}
              className={`px-3 py-1 rounded-lg border text-xs font-semibold transition-colors ${
                filterStatus === s
                  ? 'bg-[var(--brand)] text-white border-[var(--brand)]'
                  : 'bg-[var(--surface)] text-[var(--text-secondary)] border-[var(--border)] hover:bg-[var(--surface-hover)]'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        <button
          onClick={() => window.alert('Demo: add term')}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--brand)] bg-[var(--brand)] text-white text-xs font-semibold hover:opacity-90 transition-opacity"
        >
          <Plus className="w-3.5 h-3.5" /> Add Term
        </button>
      </div>

      {/* ── Terms table by group ── */}
      {TERM_GROUPS.map(group => {
        const groupTerms = filtered.filter(t => t.group === group)
        if (groupTerms.length === 0) return null
        return (
          <div key={group} className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card overflow-hidden">
            <div className="border-b border-[var(--border)] px-5 py-3 bg-[var(--surface-hover)]">
              <h2 className="text-xs font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">{group}</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-[var(--border)]">
                    <th className="text-left py-2.5 px-4 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Term</th>
                    <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Status</th>
                    <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Party</th>
                    <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Last Updated</th>
                    <th className="text-left py-2.5 px-4 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Notes</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                  {groupTerms.map((item, idx) => (
                    <tr key={idx} className="hover:bg-[var(--surface-hover)] transition-colors">
                      <td className="py-3 px-4 font-medium text-[var(--text-primary)]">{item.term}</td>
                      <td className="py-3 px-3">{statusBadge(item.status)}</td>
                      <td className="py-3 px-3">
                        <span className="px-2 py-0.5 rounded-md bg-[var(--border)] text-[var(--text-secondary)] font-semibold text-[10px]">
                          {item.party}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-[var(--text-muted)] font-mono">{item.lastUpdated}</td>
                      <td className="py-3 px-4">
                        <button
                          onClick={() => window.alert(`Demo: edit note for "${item.term}"`)}
                          className="text-left text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:underline transition-colors max-w-xs truncate"
                          title={item.notes}
                        >
                          {item.notes}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )
      })}
    </div>
  )
}
