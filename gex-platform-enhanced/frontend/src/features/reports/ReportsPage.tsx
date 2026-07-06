// Screen: Reports & Evidence hub (/reports)
//
// One honest door. Replaces the five former menu entries that all dead-ended
// here (Evidence Upload, Decision Twin, Audit Trail, ESG, Performance Matrix).
// Each is now an in-page view, deep-linkable via ?view=<id>, and each report
// carries an explicit build-state chip (LIVE / PLANNED) — no false promises.
//
// Doctrine: slate-only, square corners, mono labels, colour = state.

import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

type BuildState = 'LIVE' | 'PLANNED'

interface ReportDef {
  name: string
  desc: string
  state: BuildState
}

interface ReportView {
  id: string
  label: string
  blurb: string
  reports: ReportDef[]
}

// The five views correspond 1:1 to the former /reports menu doors.
const VIEWS: ReportView[] = [
  {
    id: 'evidence-upload',
    label: 'Evidence Upload',
    blurb: 'Submit and track gate evidence items; routes to the evidence ledger for hashing and verification.',
    reports: [
      { name: 'Evidence Submission Queue', desc: 'Items awaiting upload across open gates (G0–G11)', state: 'PLANNED' },
      { name: 'Verification Status Log', desc: 'UNVERIFIED → SUBMITTED → CONFIRMED → AUDITED transitions per item', state: 'PLANNED' },
    ],
  },
  {
    id: 'decision-twin',
    label: 'Decision Twin (RFNBO / RED III)',
    blurb: 'Certification-pathway decision model: tests a project against RFNBO temporal-correlation and RED III thresholds.',
    reports: [
      { name: 'RFNBO Eligibility Twin', desc: 'Hourly vs annual matching, additionality, geographic correlation', state: 'PLANNED' },
      { name: 'RED III Pathway Check', desc: 'GHG intensity vs threshold, feedstock eligibility', state: 'PLANNED' },
    ],
  },
  {
    id: 'audit-trail',
    label: 'Audit Trail',
    blurb: 'Immutable event log: evidence submissions, state changes, approvals, commitment signings. Backed by the event store.',
    reports: [
      { name: 'Full Event Log', desc: 'Chronological, hash-chained event stream per project', state: 'PLANNED' },
      { name: 'Approval & Signing Trail', desc: 'WAE approvals, countersignatures, commitment hashes', state: 'PLANNED' },
    ],
  },
  {
    id: 'esg',
    label: 'Environmental & ESG',
    blurb: 'MRV and ESG disclosure reporting for regulators and capital providers.',
    reports: [
      { name: 'MRV Reporting Pack', desc: 'Measurement, Reporting, Verification data for the regulator', state: 'PLANNED' },
      { name: 'ESG Disclosure Summary', desc: 'Emissions, water, community, governance indicators', state: 'PLANNED' },
    ],
  },
  {
    id: 'performance-matrix',
    label: 'Performance Matrix',
    blurb: 'Operational performance: actual vs nameplate, availability, and delivery against contract.',
    reports: [
      { name: 'Capacity Utilization', desc: 'Actual vs nameplate capacity over time', state: 'PLANNED' },
      { name: 'Delivery Performance', desc: 'On-time delivery rate, shortfall and penalty exposure', state: 'PLANNED' },
    ],
  },
]

function StateChip({ state }: { state: BuildState }) {
  const cls = state === 'LIVE'
    ? 'border-l-emerald-600 text-emerald-800 dark:text-emerald-300'
    : 'border-l-slate-400 text-slate-500 dark:text-slate-400'
  return (
    <span className={`inline-flex h-[15px] items-center border border-l-2 border-slate-300 bg-white dark:bg-slate-950 px-1 font-mono text-[8px] font-bold uppercase tracking-[0.08em] leading-none whitespace-nowrap ${cls}`}>
      {state}
    </span>
  )
}

export function ReportsPage() {
  const [params, setParams] = useSearchParams()
  const requested = params.get('view')
  const activeId = requested && VIEWS.some(v => v.id === requested) ? requested : VIEWS[0].id
  const active = useMemo(() => VIEWS.find(v => v.id === activeId) ?? VIEWS[0], [activeId])

  const liveCount = VIEWS.flatMap(v => v.reports).filter(r => r.state === 'LIVE').length
  const totalCount = VIEWS.flatMap(v => v.reports).length

  return (
    <div className="max-w-5xl mx-auto px-2 py-2 space-y-2">

      {/* Status line */}
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-slate-200 dark:border-slate-800 pb-1">
        <h1 className="font-mono text-[12px] font-bold uppercase tracking-[0.12em] text-slate-900 dark:text-slate-100">
          Reports &amp; Evidence
        </h1>
        <span className="font-mono text-[10px] text-slate-500 dark:text-slate-400">
          {liveCount}/{totalCount} reports live · {totalCount - liveCount} planned
        </span>
      </div>

      {/* View tabs — the five former menu doors, now one hub */}
      <div className="flex flex-wrap gap-px bg-slate-200 dark:bg-slate-800 border border-slate-200 dark:border-slate-800">
        {VIEWS.map(v => {
          const on = v.id === active.id
          return (
            <button
              key={v.id}
              onClick={() => setParams(v.id === VIEWS[0].id ? {} : { view: v.id })}
              className={`flex-1 min-w-[140px] px-2 py-1.5 text-left font-mono text-[11px] uppercase tracking-[0.06em] transition-colors ${
                on
                  ? 'bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-100 border-t-2 border-t-[var(--brand,#0ea5a0)]'
                  : 'bg-white/60 dark:bg-slate-950/60 text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
              }`}
            >
              {v.label}
            </button>
          )
        })}
      </div>

      {/* Active view */}
      <section className="border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950">
        <div className="border-b border-slate-200 dark:border-slate-800 px-3 py-2">
          <p className="font-mono text-[11px] text-slate-700 dark:text-slate-300 leading-relaxed">{active.blurb}</p>
        </div>
        <ul className="divide-y divide-slate-100 dark:divide-slate-900">
          {active.reports.map((r, i) => (
            <li key={i} className="grid grid-cols-[minmax(0,1fr)_72px] items-center gap-2 px-3 py-2 hover:bg-slate-50 dark:hover:bg-slate-900">
              <div className="min-w-0">
                <div className="font-mono text-[12px] font-semibold text-slate-900 dark:text-slate-100 truncate">{r.name}</div>
                <div className="font-mono text-[10px] text-slate-500 dark:text-slate-400 leading-snug">{r.desc}</div>
              </div>
              <div className="justify-self-end"><StateChip state={r.state} /></div>
            </li>
          ))}
        </ul>
        <div className="border-t border-slate-200 dark:border-slate-800 px-3 py-1.5">
          <p className="font-mono text-[9px] text-slate-500 dark:text-slate-400 leading-snug">
            Reports marked PLANNED are not yet generated. This hub replaces five separate menu entries
            that all resolved to this page — one door, honest build-state, no false promises.
          </p>
        </div>
      </section>
    </div>
  )
}
