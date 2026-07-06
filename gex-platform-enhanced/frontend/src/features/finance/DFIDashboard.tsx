// Screen: DFI criteria dashboard (/finance/dfi-dashboard)
/**
 * DFIDashboard — per-institution DFI criteria tracking,
 * additionality test results, and catalytic ratio display.
 */
import { useState } from 'react'
import { Building2, Lock, CheckCircle, Clock, AlertCircle, Search } from 'lucide-react'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { useSelectedProject } from '@/contexts/ProjectContext'

// ═══════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════

type CriterionStatus = 'MET' | 'IN_PROGRESS' | 'PENDING' | 'CHECK'

interface DFICriterion {
  code: string
  name: string
  status: CriterionStatus
  blocks_drawdown: boolean
  note?: string
}

interface AdditionalityTest {
  irr_with_dfi: number      // %
  irr_without_dfi: number   // %
  pass: boolean
  catalytic_ratio: number   // commercial / concessional
}

interface DFIInstitution {
  id: string
  name: string
  shortName: string
  criteria: DFICriterion[]
  additionality: AdditionalityTest
}

// ═══════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════

const STATUS_STYLE: Record<CriterionStatus, { bg: string; text: string; border: string; label: string; icon: React.ReactNode }> = {
  MET:         { bg: 'bg-green-100',  text: 'text-green-700',  border: 'border-green-300',  label: 'Met',         icon: <CheckCircle className="w-3.5 h-3.5" /> },
  IN_PROGRESS: { bg: 'bg-amber-100',  text: 'text-amber-700',  border: 'border-amber-300',  label: 'In Progress', icon: <Clock className="w-3.5 h-3.5" /> },
  PENDING:     { bg: 'bg-gray-100',   text: 'text-gray-500',   border: 'border-gray-300',   label: 'Pending',     icon: <AlertCircle className="w-3.5 h-3.5" /> },
  CHECK:       { bg: 'bg-blue-100',   text: 'text-blue-700',   border: 'border-blue-300',   label: 'Check',       icon: <Search className="w-3.5 h-3.5" /> },
}

// ═══════════════════════════════════════════════════════════════
// MOCK DATA
// ═══════════════════════════════════════════════════════════════

const MOCK_DFI: Record<string, DFIInstitution[]> = {
  default: [
    {
      id: 'eib',
      name: 'European Investment Bank',
      shortName: 'EIB',
      criteria: [
        { code: 'EIB-01', name: 'EU Taxonomy Alignment',          status: 'MET',         blocks_drawdown: true,  note: 'Substantial contribution to climate mitigation confirmed' },
        { code: 'EIB-02', name: 'DNSH Assessment',                status: 'MET',         blocks_drawdown: true,  note: 'Do No Significant Harm criteria satisfied' },
        { code: 'EIB-03', name: 'Carbon Footprint Estimate',      status: 'IN_PROGRESS', blocks_drawdown: true,  note: 'Awaiting scope 3 upstream verification' },
        { code: 'EIB-04', name: 'Paris Alignment Certification',  status: 'PENDING',     blocks_drawdown: false, note: 'Requires final board approval' },
      ],
      additionality: { irr_with_dfi: 8.2, irr_without_dfi: 4.1, pass: true, catalytic_ratio: 2.8 },
    },
    {
      id: 'kfw',
      name: 'Kreditanstalt fur Wiederaufbau',
      shortName: 'KfW',
      criteria: [
        { code: 'KfW-01', name: 'German Energy Transition Alignment',  status: 'MET',         blocks_drawdown: false },
        { code: 'KfW-02', name: 'BMZ Development Impact Assessment',   status: 'MET',         blocks_drawdown: true  },
        { code: 'KfW-03', name: 'Environmental & Social Impact Study', status: 'IN_PROGRESS', blocks_drawdown: true, note: 'ESIA Phase 2 underway' },
        { code: 'KfW-04', name: 'Procurement Compliance',              status: 'MET',         blocks_drawdown: false },
        { code: 'KfW-05', name: 'Local Content Requirement',           status: 'PENDING',     blocks_drawdown: false },
      ],
      additionality: { irr_with_dfi: 7.9, irr_without_dfi: 3.8, pass: true, catalytic_ratio: 3.1 },
    },
    {
      id: 'ifc',
      name: 'International Finance Corporation',
      shortName: 'IFC',
      criteria: [
        { code: 'IFC-01', name: 'Performance Standard 1 — Assessment & Mgmt',       status: 'MET',         blocks_drawdown: true  },
        { code: 'IFC-02', name: 'Performance Standard 2 — Labor & Working Conds',    status: 'MET',         blocks_drawdown: true  },
        { code: 'IFC-03', name: 'Performance Standard 3 — Resource Efficiency',       status: 'MET',         blocks_drawdown: true  },
        { code: 'IFC-04', name: 'Performance Standard 4 — Community Health & Safety', status: 'MET',         blocks_drawdown: false },
        { code: 'IFC-05', name: 'Performance Standard 5 — Land Acquisition',          status: 'MET',         blocks_drawdown: true  },
        { code: 'IFC-06', name: 'Performance Standard 6 — Biodiversity',              status: 'IN_PROGRESS', blocks_drawdown: false, note: 'Habitat assessment pending field survey' },
        { code: 'IFC-07', name: 'Performance Standard 8 — Cultural Heritage',         status: 'IN_PROGRESS', blocks_drawdown: false },
        { code: 'IFC-08', name: 'Additionality & Development Impact',                 status: 'CHECK',       blocks_drawdown: true, note: 'Under IFC Board review' },
      ],
      additionality: { irr_with_dfi: 9.1, irr_without_dfi: 5.2, pass: true, catalytic_ratio: 2.4 },
    },
    {
      id: 'bpi',
      name: 'Bpifrance',
      shortName: 'BPI',
      criteria: [
        { code: 'BPI-01', name: 'France 2030 Strategic Alignment',  status: 'MET',     blocks_drawdown: true  },
        { code: 'BPI-02', name: 'French Content & Employment',      status: 'MET',     blocks_drawdown: false },
        { code: 'BPI-03', name: 'Innovation Score Threshold',       status: 'CHECK',   blocks_drawdown: false, note: 'TRL 7+ required, project at TRL 6-7 boundary' },
      ],
      additionality: { irr_with_dfi: 8.5, irr_without_dfi: 4.8, pass: true, catalytic_ratio: 3.5 },
    },
    {
      id: 'dfc',
      name: 'US International Development Finance Corp',
      shortName: 'DFC',
      criteria: [
        { code: 'DFC-01', name: 'Development Impact Assessment',    status: 'PENDING',     blocks_drawdown: true  },
        { code: 'DFC-02', name: 'US Foreign Policy Alignment',      status: 'MET',         blocks_drawdown: false },
        { code: 'DFC-03', name: 'Environmental Assessment (Cat B)',  status: 'IN_PROGRESS', blocks_drawdown: true, note: 'EA report in review' },
      ],
      additionality: { irr_with_dfi: 7.4, irr_without_dfi: 3.2, pass: true, catalytic_ratio: 2.1 },
    },
    {
      id: 'afdb',
      name: 'African Development Bank',
      shortName: 'AfDB',
      criteria: [
        { code: 'AfDB-01', name: 'High 5 Priority Alignment',           status: 'PENDING', blocks_drawdown: false },
        { code: 'AfDB-02', name: 'Environmental & Social Safeguards',    status: 'PENDING', blocks_drawdown: true  },
        { code: 'AfDB-03', name: 'Country Strategy Paper Consistency',   status: 'PENDING', blocks_drawdown: false },
      ],
      additionality: { irr_with_dfi: 6.8, irr_without_dfi: 2.5, pass: true, catalytic_ratio: 1.9 },
    },
  ],
}

// ═══════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════

function criterionStats(criteria: DFICriterion[]) {
  const met = criteria.filter(c => c.status === 'MET').length
  const blocking = criteria.filter(c => c.blocks_drawdown && c.status !== 'MET').length
  const readiness = criteria.length > 0 ? Math.round((met / criteria.length) * 100) : 0
  return { met, total: criteria.length, blocking, readiness }
}

function readinessColor(pct: number): string {
  if (pct >= 80) return 'text-green-600'
  if (pct >= 50) return 'text-amber-600'
  return 'text-red-600'
}

function catalyticColor(ratio: number): string {
  if (ratio >= 5.0) return 'text-green-600'
  if (ratio >= 3.0) return 'text-amber-600'
  return 'text-red-600'
}

// ═══════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════

export function DFIDashboard() {
  const { selectedProjectId } = useSelectedProject()
  const institutions = MOCK_DFI[selectedProjectId] ?? MOCK_DFI['default']
  const [activeTab, setActiveTab] = useState(institutions[0]?.id ?? '')

  const inst = institutions.find(i => i.id === activeTab)

  return (
    <div className="space-y-4 max-w-6xl mx-auto pb-8">

      {/* Header */}
      <div className="rounded-2xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        <div className="flex items-start justify-between px-6 py-4 bg-gradient-to-r from-gray-900 to-gray-800">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Building2 className="w-4 h-4 text-gray-400" />
              <span className="text-xs font-bold uppercase tracking-widest text-gray-400">DFI Dashboard</span>
            </div>
            <h1 className="text-2xl font-black text-white">Development Finance Institution Criteria</h1>
            <p className="text-sm text-gray-400 mt-0.5">Per-institution criteria tracking, additionality test, catalytic ratio</p>
          </div>
        </div>
      </div>

      {/* Institution tabs */}
      <div className="flex items-center gap-1 border-b border-gray-200 overflow-x-auto">
        {institutions.map(i => {
          const stats = criterionStats(i.criteria)
          return (
            <button
              key={i.id}
              type="button"
              onClick={() => setActiveTab(i.id)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-bold rounded-t-lg border border-b-0 transition-colors whitespace-nowrap shrink-0 ${
                activeTab === i.id
                  ? 'bg-white border-gray-200 text-gray-900 -mb-px z-10 relative'
                  : 'bg-gray-50 border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {i.shortName}
              <span className={`text-[10px] font-mono ${readinessColor(stats.readiness)}`}>
                {stats.readiness}%
              </span>
            </button>
          )
        })}
      </div>

      {inst && (() => {
        const stats = criterionStats(inst.criteria)
        return (
          <div className="space-y-4">

            {/* Summary strip */}
            <div className="grid grid-cols-4 gap-3">
              <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm text-center">
                <div className={`text-2xl font-black tabular-nums ${readinessColor(stats.readiness)}`}>
                  {stats.readiness}%
                </div>
                <div className="text-xs font-semibold text-gray-500 mt-1">Readiness</div>
              </div>
              <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm text-center">
                <div className="text-2xl font-black tabular-nums text-gray-900">
                  {stats.met}/{stats.total}
                </div>
                <div className="text-xs font-semibold text-gray-500 mt-1">Criteria Met</div>
              </div>
              <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm text-center">
                <div className={`text-2xl font-black tabular-nums ${stats.blocking > 0 ? 'text-red-600' : 'text-green-600'}`}>
                  {stats.blocking}
                </div>
                <div className="text-xs font-semibold text-gray-500 mt-1">Blocking Drawdown</div>
              </div>
              <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm text-center">
                <div className={`text-2xl font-black tabular-nums ${inst.additionality.pass ? 'text-green-600' : 'text-red-600'}`}>
                  {inst.additionality.pass ? 'PASS' : 'FAIL'}
                </div>
                <div className="text-xs font-semibold text-gray-500 mt-1">Additionality</div>
              </div>
            </div>

            {/* Criteria table */}
            <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
              <div className="px-4 py-2.5 border-b border-gray-100 bg-gray-50 flex items-center gap-2">
                <h3 className="text-xs font-black uppercase tracking-widest text-gray-600">
                  {inst.name} — Criteria Assessment
                </h3>
                <InfoTooltip text="Each criterion must be MET before drawdown if marked as blocking. IN_PROGRESS and PENDING criteria need action." />
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-gray-100">
                      <th className="text-left px-4 py-2 font-semibold text-gray-500 uppercase tracking-wide">Code</th>
                      <th className="text-left px-3 py-2 font-semibold text-gray-500 uppercase tracking-wide">Criterion</th>
                      <th className="text-center px-3 py-2 font-semibold text-gray-500 uppercase tracking-wide">Status</th>
                      <th className="text-center px-3 py-2 font-semibold text-gray-500 uppercase tracking-wide">Blocks Drawdown</th>
                      <th className="text-left px-3 py-2 font-semibold text-gray-500 uppercase tracking-wide">Note</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {inst.criteria.map(c => {
                      const s = STATUS_STYLE[c.status]
                      const isBlocking = c.blocks_drawdown && c.status !== 'MET'
                      return (
                        <tr key={c.code} className={`hover:bg-gray-50/60 ${isBlocking ? 'bg-red-50/30' : ''}`}>
                          <td className="px-4 py-2.5 font-mono font-bold text-gray-700">{c.code}</td>
                          <td className="px-3 py-2.5 font-medium text-gray-800">{c.name}</td>
                          <td className="px-3 py-2.5 text-center">
                            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-xs font-semibold ${s.bg} ${s.text} ${s.border}`}>
                              {s.icon}
                              {s.label}
                            </span>
                          </td>
                          <td className="px-3 py-2.5 text-center">
                            {c.blocks_drawdown ? (
                              <span className={`inline-flex items-center gap-1 text-xs font-semibold ${isBlocking ? 'text-red-600' : 'text-green-600'}`}>
                                <Lock className="w-3 h-3" />
                                {isBlocking ? 'Blocking' : 'Cleared'}
                              </span>
                            ) : (
                              <span className="text-gray-400 text-xs">--</span>
                            )}
                          </td>
                          <td className="px-3 py-2.5 text-gray-500 max-w-[200px] truncate" title={c.note}>
                            {c.note ?? '--'}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Additionality + Catalytic ratio */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

              {/* Additionality test */}
              <div className="rounded-xl border border-gray-200 bg-white shadow-sm p-4">
                <div className="flex items-center gap-2 mb-3">
                  <h3 className="text-xs font-black uppercase tracking-widest text-gray-600">Additionality Test</h3>
                  <InfoTooltip text="Demonstrates that DFI participation is necessary. Project IRR with DFI must exceed IRR without DFI, confirming that DFI capital enables the project to proceed." />
                </div>
                <div className="space-y-3">
                  {/* IRR with DFI */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs text-gray-600">IRR with DFI</span>
                      <span className="text-sm font-black tabular-nums text-green-600">
                        {inst.additionality.irr_with_dfi.toFixed(1)}%
                      </span>
                    </div>
                    <div className="h-3 w-full rounded-full bg-gray-100 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-green-500 transition-all"
                        style={{ width: `${Math.min(inst.additionality.irr_with_dfi / 15 * 100, 100)}%` }}
                      />
                    </div>
                  </div>
                  {/* IRR without DFI */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs text-gray-600">IRR without DFI</span>
                      <span className="text-sm font-black tabular-nums text-red-600">
                        {inst.additionality.irr_without_dfi.toFixed(1)}%
                      </span>
                    </div>
                    <div className="h-3 w-full rounded-full bg-gray-100 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-red-400 transition-all"
                        style={{ width: `${Math.min(inst.additionality.irr_without_dfi / 15 * 100, 100)}%` }}
                      />
                    </div>
                  </div>
                  {/* Delta */}
                  <div className="flex items-center justify-between pt-2 border-t border-gray-100">
                    <span className="text-xs font-semibold text-gray-700">IRR Delta</span>
                    <span className="text-sm font-black tabular-nums text-teal-600">
                      +{(inst.additionality.irr_with_dfi - inst.additionality.irr_without_dfi).toFixed(1)}pp
                    </span>
                  </div>
                  <div className="flex justify-center pt-1">
                    <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-bold ${
                      inst.additionality.pass
                        ? 'bg-green-100 text-green-700 border border-green-300'
                        : 'bg-red-100 text-red-700 border border-red-300'
                    }`}>
                      <CheckCircle className="w-4 h-4" />
                      {inst.additionality.pass ? 'ADDITIONALITY CONFIRMED' : 'ADDITIONALITY NOT DEMONSTRATED'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Catalytic ratio */}
              <div className="rounded-xl border border-gray-200 bg-white shadow-sm p-4">
                <div className="flex items-center gap-2 mb-3">
                  <h3 className="text-xs font-black uppercase tracking-widest text-gray-600">Catalytic Ratio</h3>
                  <InfoTooltip text="Ratio of commercial capital mobilised per unit of concessional/DFI capital. IFC target is 5:1. Higher ratio = stronger catalytic effect." />
                </div>
                <div className="flex flex-col items-center justify-center py-4">
                  <div className={`text-5xl font-black tabular-nums ${catalyticColor(inst.additionality.catalytic_ratio)}`}>
                    {inst.additionality.catalytic_ratio.toFixed(1)}x
                  </div>
                  <div className="text-xs text-gray-500 mt-2">Commercial / Concessional</div>

                  {/* Gauge bar */}
                  <div className="w-full mt-4">
                    <div className="relative h-4 w-full rounded-full bg-gray-100 overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${
                          inst.additionality.catalytic_ratio >= 5.0 ? 'bg-green-500' :
                          inst.additionality.catalytic_ratio >= 3.0 ? 'bg-amber-500' : 'bg-red-500'
                        }`}
                        style={{ width: `${Math.min(inst.additionality.catalytic_ratio / 7 * 100, 100)}%` }}
                      />
                      {/* 5:1 target marker */}
                      <div
                        className="absolute top-0 h-full w-0.5 bg-gray-800"
                        style={{ left: `${(5 / 7) * 100}%` }}
                        title="IFC 5:1 target"
                      />
                    </div>
                    <div className="flex justify-between mt-1">
                      <span className="text-[10px] text-gray-400">0x</span>
                      <span className="text-[10px] text-gray-600 font-bold" style={{ marginLeft: `${(5 / 7) * 100 - 3}%` }}>
                        5:1 target
                      </span>
                      <span className="text-[10px] text-gray-400">7x+</span>
                    </div>
                  </div>

                  {inst.additionality.catalytic_ratio < 5 && (
                    <p className="mt-3 text-xs text-amber-600 font-semibold text-center">
                      Below IFC 5:1 catalytic target — concessional-heavy structure
                    </p>
                  )}
                </div>
              </div>
            </div>
          </div>
        )
      })()}
    </div>
  )
}
