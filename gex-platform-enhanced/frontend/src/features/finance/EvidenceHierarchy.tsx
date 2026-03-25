/**
 * EvidenceHierarchy — R9 (Architectural Reform v6.0)
 *
 * Credit Committee Chair view: per-gate table showing exactly how much
 * of the bankability assessment rests on verified vs unverified evidence.
 *
 * Columns:
 *   Gate | AUDITED | CONFIRMED | SUBMITTED | UNVERIFIED | Effective Score
 *
 * "Effective Score" = raw score × mean(verification weights)
 * Raw score shown in parentheses for reference.
 *
 * This replaces the arc-gauge Bankability Score for L4 users.
 * No composite score. No gauge. Evidence hierarchy only.
 */

import { useEffect, useState } from 'react'
import { ShieldCheck, ShieldOff, Info } from 'lucide-react'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { getProjectById, CUSTOMER_PROJECTS } from '@/data/customerProjects'
import { DealKillerBanner, useActiveKillers } from '@/components/DealKillerBanner'

// ─── Types ────────────────────────────────────────────────────────────────────

interface GateSummaryRow {
  gate_id:         string
  AUDITED:         number
  CONFIRMED:       number
  SUBMITTED:       number
  UNVERIFIED:      number
  total:           number
  raw_score:       number
  effective_score: number
}

const GATE_NAMES: Record<string, string> = {
  G0:  'Site & Rights',
  G1:  'Grid & Utilities',
  G2:  'Certification Path',
  G3:  'Key Inputs',
  G4:  'Offtake Bankable',
  G5:  'EPC Risk Priced',
  G6:  'IE Sign-off',
  G7:  'Insurance Bound',
  G8:  'Audit-Grade Model',
  G9:  'Permits Complete',
  G10: 'Financial Close',
  G11: 'COD / Stabilization',
}

// ─── Demo data ────────────────────────────────────────────────────────────────

const DEMO_ROWS: GateSummaryRow[] = [
  { gate_id: 'G0',  AUDITED: 1, CONFIRMED: 3, SUBMITTED: 0, UNVERIFIED: 0, total: 4,  raw_score: 100, effective_score: 93 },
  { gate_id: 'G1',  AUDITED: 1, CONFIRMED: 2, SUBMITTED: 1, UNVERIFIED: 0, total: 4,  raw_score: 95,  effective_score: 76 },
  { gate_id: 'G2',  AUDITED: 2, CONFIRMED: 2, SUBMITTED: 0, UNVERIFIED: 0, total: 4,  raw_score: 90,  effective_score: 85 },
  { gate_id: 'G3',  AUDITED: 0, CONFIRMED: 1, SUBMITTED: 2, UNVERIFIED: 1, total: 4,  raw_score: 80,  effective_score: 44 },
  { gate_id: 'G4',  AUDITED: 0, CONFIRMED: 3, SUBMITTED: 2, UNVERIFIED: 1, total: 6,  raw_score: 78,  effective_score: 39 },
  { gate_id: 'G5',  AUDITED: 0, CONFIRMED: 0, SUBMITTED: 1, UNVERIFIED: 4, total: 5,  raw_score: 45,  effective_score: 11 },
  { gate_id: 'G6',  AUDITED: 0, CONFIRMED: 0, SUBMITTED: 1, UNVERIFIED: 2, total: 3,  raw_score: 40,  effective_score: 10 },
  { gate_id: 'G7',  AUDITED: 0, CONFIRMED: 0, SUBMITTED: 0, UNVERIFIED: 3, total: 3,  raw_score: 30,  effective_score:  8 },
  { gate_id: 'G8',  AUDITED: 1, CONFIRMED: 5, SUBMITTED: 0, UNVERIFIED: 0, total: 6,  raw_score: 68,  effective_score: 65 },
  { gate_id: 'G9',  AUDITED: 0, CONFIRMED: 0, SUBMITTED: 2, UNVERIFIED: 2, total: 4,  raw_score: 20,  effective_score:  9 },
  { gate_id: 'G10', AUDITED: 0, CONFIRMED: 0, SUBMITTED: 0, UNVERIFIED: 4, total: 4,  raw_score: 10,  effective_score:  3 },
  { gate_id: 'G11', AUDITED: 0, CONFIRMED: 0, SUBMITTED: 0, UNVERIFIED: 2, total: 2,  raw_score: 5,   effective_score:  1 },
]

// ─── Main component ───────────────────────────────────────────────────────────

export default function EvidenceHierarchy() {
  const { selectedProjectId } = useSelectedProject()
  const project = getProjectById(selectedProjectId) ?? CUSTOMER_PROJECTS[0]
  const { killers } = useActiveKillers(project.id)
  const [rows, setRows] = useState<GateSummaryRow[]>([])

  useEffect(() => {
    fetch(`/api/v1/verification/summary/${project.id}`)
      .then(r => r.ok ? r.json() : Promise.reject(r))
      .then(data => setRows(data.gates))
      .catch(() => setRows(DEMO_ROWS))
  }, [project.id])

  // Totals row
  const totals = rows.reduce(
    (acc, r) => ({
      AUDITED:    acc.AUDITED    + r.AUDITED,
      CONFIRMED:  acc.CONFIRMED  + r.CONFIRMED,
      SUBMITTED:  acc.SUBMITTED  + r.SUBMITTED,
      UNVERIFIED: acc.UNVERIFIED + r.UNVERIFIED,
      total:      acc.total      + r.total,
    }),
    { AUDITED: 0, CONFIRMED: 0, SUBMITTED: 0, UNVERIFIED: 0, total: 0 },
  )

  const verifiedPct = totals.total > 0
    ? Math.round(((totals.AUDITED + totals.CONFIRMED) / totals.total) * 100)
    : 0

  return (
    <div className="space-y-4 max-w-5xl">
      {/* Header */}
      <div>
        <h1 className="text-lg font-bold text-gray-900">Evidence Hierarchy</h1>
        <p className="text-xs text-gray-500 mt-0.5">
          {project.name} — per-gate verification breakdown for credit committee
        </p>
      </div>

      {/* Deal-Killer Banner */}
      <DealKillerBanner killers={killers} projectName={project.name} />

      {/* Summary strip */}
      <div className="grid grid-cols-5 gap-3">
        {[
          { label: 'Audited',    count: totals.AUDITED,    color: 'bg-green-50 border-green-200 text-green-800', weight: '×1.00' },
          { label: 'Confirmed',  count: totals.CONFIRMED,  color: 'bg-blue-50 border-blue-200 text-blue-800',    weight: '×0.85' },
          { label: 'Submitted',  count: totals.SUBMITTED,  color: 'bg-amber-50 border-amber-200 text-amber-800', weight: '×0.50' },
          { label: 'Unverified', count: totals.UNVERIFIED, color: 'bg-gray-50 border-gray-200 text-gray-600',    weight: '×0.25' },
          { label: 'Verified %', count: `${verifiedPct}%`, color: verifiedPct >= 70 ? 'bg-green-50 border-green-200 text-green-800' : 'bg-red-50 border-red-200 text-red-800', weight: 'CONF+AUD' },
        ].map(s => (
          <div key={s.label} className={`rounded-lg border px-3 py-2 ${s.color}`}>
            <div className="text-lg font-bold tabular-nums">{s.count}</div>
            <div className="text-xs font-medium">{s.label}</div>
            <div className="text-[10px] opacity-60">{s.weight}</div>
          </div>
        ))}
      </div>

      {/* Main table */}
      <div className="rounded-lg border border-gray-200 overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50">
              <th className="text-left px-4 py-2.5 font-semibold text-gray-600">Gate</th>
              <th className="text-right px-3 py-2.5 font-semibold text-green-700">
                <div className="flex items-center justify-end gap-1">
                  Audited
                  <span className="text-[9px] text-green-500 font-normal">×1.00</span>
                </div>
              </th>
              <th className="text-right px-3 py-2.5 font-semibold text-blue-700">
                <div className="flex items-center justify-end gap-1">
                  Confirmed
                  <span className="text-[9px] text-blue-400 font-normal">×0.85</span>
                </div>
              </th>
              <th className="text-right px-3 py-2.5 font-semibold text-amber-600">
                <div className="flex items-center justify-end gap-1">
                  Submitted
                  <span className="text-[9px] text-amber-400 font-normal">×0.50</span>
                </div>
              </th>
              <th className="text-right px-3 py-2.5 font-semibold text-gray-500">
                <div className="flex items-center justify-end gap-1">
                  Unverified
                  <span className="text-[9px] text-gray-400 font-normal">×0.25</span>
                </div>
              </th>
              <th className="text-right px-4 py-2.5 font-semibold text-gray-700">
                <div className="flex items-center justify-end gap-1">
                  Effective Score
                  <InfoTooltip text="Effective = Raw × mean(verification weights). State machine uses effective scores. Raw shown in parentheses." />
                </div>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map(row => {
              const effectiveness = row.raw_score > 0
                ? Math.round((row.effective_score / row.raw_score) * 100)
                : 0

              const effectiveColor =
                effectiveness >= 80 ? 'text-green-700' :
                effectiveness >= 50 ? 'text-amber-600' :
                                      'text-red-600'

              return (
                <tr key={row.gate_id} className="border-b border-gray-100 last:border-0 hover:bg-gray-50">
                  <td className="px-4 py-2.5">
                    <span className="font-bold text-gray-700 mr-2">{row.gate_id}</span>
                    <span className="text-gray-500">{GATE_NAMES[row.gate_id] ?? ''}</span>
                  </td>
                  <td className="px-3 py-2.5 text-right font-semibold text-green-700 tabular-nums">
                    {row.AUDITED > 0 ? row.AUDITED : <span className="text-gray-300">—</span>}
                  </td>
                  <td className="px-3 py-2.5 text-right font-semibold text-blue-700 tabular-nums">
                    {row.CONFIRMED > 0 ? row.CONFIRMED : <span className="text-gray-300">—</span>}
                  </td>
                  <td className="px-3 py-2.5 text-right font-semibold text-amber-600 tabular-nums">
                    {row.SUBMITTED > 0 ? row.SUBMITTED : <span className="text-gray-300">—</span>}
                  </td>
                  <td className="px-3 py-2.5 text-right font-semibold text-gray-500 tabular-nums">
                    {row.UNVERIFIED > 0 ? row.UNVERIFIED : <span className="text-gray-300">—</span>}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <span className={`font-bold tabular-nums ${effectiveColor}`}>
                      {row.effective_score}
                    </span>
                    <span className="text-gray-400 ml-1 font-normal">
                      / {row.raw_score} ({effectiveness}%)
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
          {/* Totals row */}
          <tfoot>
            <tr className="border-t-2 border-gray-300 bg-gray-50">
              <td className="px-4 py-2.5 font-bold text-gray-700">Total evidence items</td>
              <td className="px-3 py-2.5 text-right font-bold text-green-700 tabular-nums">{totals.AUDITED}</td>
              <td className="px-3 py-2.5 text-right font-bold text-blue-700 tabular-nums">{totals.CONFIRMED}</td>
              <td className="px-3 py-2.5 text-right font-bold text-amber-600 tabular-nums">{totals.SUBMITTED}</td>
              <td className="px-3 py-2.5 text-right font-bold text-gray-500 tabular-nums">{totals.UNVERIFIED}</td>
              <td className="px-4 py-2.5 text-right">
                <span className={`font-bold ${verifiedPct >= 70 ? 'text-green-700' : 'text-red-600'}`}>
                  {verifiedPct}% at CONFIRMED+
                </span>
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      <div className="flex items-start gap-2 text-[10px] text-gray-400">
        <Info className="w-3 h-3 mt-0.5 flex-shrink-0" />
        <p>
          Effective score = raw score × mean verification weight across all evidence items in that gate.
          A gate at 80% raw with all UNVERIFIED items yields an effective score of 20.
          The state machine uses effective scores — not raw — to determine bankability state transitions.
          Raw scores are retained for analyst reference only.
        </p>
      </div>
    </div>
  )
}
