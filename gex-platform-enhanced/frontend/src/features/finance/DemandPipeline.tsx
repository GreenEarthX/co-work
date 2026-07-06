// Screen: Demand pipeline screen (/finance-demand)
/**
 * Sales — Projected Downstream Sales to Third Parties
 *
 * Simple, action-oriented screen showing:
 *   - Which projects have demand signals / LOIs / contracts from third-party offtakers
 *   - Coverage % vs bankable threshold (70%)
 *   - Clear next actions per project
 *
 * Data sourced from CUSTOMER_PROJECTS canonical registry.
 * The Commercial Overview shows the producer's own projected sales.
 * This screen focuses on the sales pipeline: which buyers are bidding, and at what stage.
 */

import { useState, useMemo } from 'react'
import { ArrowRight, Users, Target, AlertTriangle, CheckCircle, Plus, Filter } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { type CustomerProject } from '@/data/customerProjects'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'

// ── Types ────────────────────────────────────────────────────────────────────

interface DemandSignal {
  buyer: string
  volume_mt_pa: number
  stage: 'EOI' | 'LOI' | 'TERM_SHEET' | 'CONTRACTED'
  price_indication: string
  expires: string | null
}

interface ProjectDemand {
  project: CustomerProject
  signals: DemandSignal[]
  totalDemand_mt: number
  annualCapacity_mt: number
  coveragePct: number
  meetsThreshold: boolean
}

// ── Derive demand signals from project data ──────────────────────────────────

const STAGE_ORDER: Record<string, number> = { CONTRACTED: 4, TERM_SHEET: 3, LOI: 2, EOI: 1 }

/** Real offtaker names extracted from each project's description field. */
const PROJECT_BUYERS: Record<string, string[]> = {
  proj_bremen_h2:              ['Bremen Port Industrial Consortium'],
  proj_rotterdam_nh3:          ['EU Fertiliser Manufacturers Consortium'],
  proj_sansebastian_emethanol: ['Maersk', 'CMA CGM'],
  proj_wales_saf:              ['British Airways', 'easyJet'],
  proj_lehavre_eng:            ['Engie SA'],
  proj_hamburgone_emethanol:   ['BremenThree AG'],
  proj_madrid2_sansebastian:   ['RotterdamOfftake4 AG'],
}

function buildDemandForProject(p: CustomerProject): ProjectDemand {
  const annualCapacity = Math.round(p.capacity_mtpd * 330)
  const g4 = p.bankability.gates.find(g => g.id === 'G4_OFFTAKE_BANKABLE')
  const g4pct = g4?.completion_pct ?? 0
  const buyers = PROJECT_BUYERS[p.id] ?? ['Market enquiry']

  // Generate demand signals using real offtaker names and G4 gate progress
  const signals: DemandSignal[] = []

  if (g4 && g4.is_complete) {
    // Fully contracted
    signals.push({
      buyer: buyers[0],
      volume_mt_pa: Math.round(annualCapacity * 0.75),
      stage: 'CONTRACTED',
      price_indication: 'Fixed — see term sheet',
      expires: null,
    })
  } else if (g4 && g4pct >= 70) {
    signals.push({
      buyer: buyers[0],
      volume_mt_pa: Math.round(annualCapacity * 0.55),
      stage: 'TERM_SHEET',
      price_indication: 'Gabillon-indexed',
      expires: '2026-09-30',
    })
    if (buyers.length > 1) {
      signals.push({
        buyer: buyers[1],
        volume_mt_pa: Math.round(annualCapacity * 0.15),
        stage: 'LOI',
        price_indication: 'Market price',
        expires: '2026-12-31',
      })
    }
  } else if (g4 && g4pct >= 30) {
    signals.push({
      buyer: buyers[0],
      volume_mt_pa: Math.round(annualCapacity * 0.30),
      stage: 'LOI',
      price_indication: 'Indicative — pending Gabillon ref',
      expires: '2026-12-31',
    })
    if (buyers.length > 1) {
      signals.push({
        buyer: buyers[1],
        volume_mt_pa: Math.round(annualCapacity * 0.10),
        stage: 'EOI',
        price_indication: 'TBD',
        expires: null,
      })
    }
  } else if (g4pct > 0) {
    signals.push({
      buyer: buyers[0],
      volume_mt_pa: Math.round(annualCapacity * 0.10),
      stage: 'EOI',
      price_indication: 'TBD',
      expires: null,
    })
  }

  const totalDemand = signals.reduce((s, d) => s + d.volume_mt_pa, 0)
  const coveragePct = annualCapacity > 0 ? Math.round((totalDemand / annualCapacity) * 100) : 0

  return {
    project: p,
    signals,
    totalDemand_mt: totalDemand,
    annualCapacity_mt: annualCapacity,
    coveragePct,
    meetsThreshold: coveragePct >= 70,
  }
}

// ── Stage badge ──────────────────────────────────────────────────────────────

const STAGE_STYLE: Record<string, string> = {
  CONTRACTED:  'bg-gray-100 text-gray-900 border-gray-200',
  TERM_SHEET:  'bg-gray-100 text-gray-700 border-gray-200',
  LOI:         'bg-gray-100 text-gray-600 border-gray-200',
  EOI:         'bg-gray-100 text-gray-500 border-gray-200',
}

// ── Main Component ───────────────────────────────────────────────────────────

export function DemandPipeline() {
  const navigate = useNavigate()
  const { projects: visibleProjects } = useVisibleProjects()
  const [filterMol, setFilterMol] = useState('all')
  const [filterThreshold, setFilterThreshold] = useState('all')

  const molecules = [...new Set(visibleProjects.map(p => p.molecule))]

  const projectDemands = useMemo(() => {
    return visibleProjects
      .filter(p => filterMol === 'all' || p.molecule === filterMol)
      .map(p => buildDemandForProject(p))
      .filter(pd => {
        if (filterThreshold === 'met') return pd.meetsThreshold
        if (filterThreshold === 'below') return !pd.meetsThreshold
        return true
      })
      .sort((a, b) => b.coveragePct - a.coveragePct)
  }, [filterMol, filterThreshold, visibleProjects])

  const totalSignals = projectDemands.reduce((s, pd) => s + pd.signals.length, 0)
  const projectsMeetingThreshold = projectDemands.filter(pd => pd.meetsThreshold).length

  return (
    <div className="max-w-[1440px] mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-black text-gray-900">Sales</h1>
          <p className="text-sm text-gray-500 mt-1">
            Downstream sales pipeline by project, with buyer signals and bid readiness
          </p>
        </div>
        <button
          onClick={() => navigate('/matching?mode=sell')}
          className="inline-flex items-center gap-2 px-4 py-2 bg-gray-900 text-white rounded-lg text-sm font-semibold hover:bg-gray-800 transition-colors"
        >
          <Plus className="w-4 h-4" /> Review Market Bids
        </button>
      </div>

      {/* KPI Strip */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">Total Signals</div>
          <div className="text-2xl font-black text-gray-900">{totalSignals}</div>
          <div className="text-xs text-gray-500 mt-1">across {projectDemands.length} projects</div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">Above 70% Threshold</div>
          <div className={`text-2xl font-black ${projectsMeetingThreshold > 0 ? 'text-emerald-600' : 'text-gray-400'}`}>
            {projectsMeetingThreshold} / {projectDemands.length}
          </div>
          <div className="text-xs text-gray-500 mt-1">bankable coverage</div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">Action Required</div>
          <div className="text-2xl font-black text-amber-600">
            {projectDemands.filter(pd => !pd.meetsThreshold && pd.signals.length > 0).length}
          </div>
          <div className="text-xs text-gray-500 mt-1">projects need more buyer coverage</div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3">
        <Filter className="w-4 h-4 text-gray-400" />
        <select value={filterMol} onChange={e => setFilterMol(e.target.value)}
          className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm bg-white">
          <option value="all">All Molecules</option>
          {molecules.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
        <select value={filterThreshold} onChange={e => setFilterThreshold(e.target.value)}
          className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm bg-white">
          <option value="all">All Projects</option>
          <option value="met">Above 70% Threshold</option>
          <option value="below">Below 70% Threshold</option>
        </select>
      </div>

      {/* Project Cards */}
      <div className="space-y-4">
        {projectDemands.map(pd => (
          <div key={pd.project.id} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            {/* Project header */}
            <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div>
                  <h3 className="text-sm font-bold text-gray-900">{pd.project.name}</h3>
                  <div className="flex items-center gap-2 mt-0.5 text-xs text-gray-500">
                    <span className="font-bold px-2 py-0.5 rounded bg-gray-100 text-gray-700 border border-gray-200">{pd.project.molecule}</span>
                    <span>{pd.project.location}</span>
                    <span>&middot; {pd.project.capacity_mtpd} MTPD</span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-4">
                {/* Coverage bar */}
                <div className="text-right">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs text-gray-500">Coverage</span>
                    <span className={`text-xs font-bold ${pd.meetsThreshold ? 'text-emerald-600' : 'text-amber-600'}`}>
                      {pd.coveragePct}%
                    </span>
                  </div>
                  <div className="w-32 bg-gray-100 rounded-full h-2 relative">
                    <div
                      className={`h-full rounded-full transition-all ${pd.meetsThreshold ? 'bg-emerald-500' : pd.coveragePct >= 40 ? 'bg-amber-400' : 'bg-gray-300'}`}
                      style={{ width: `${Math.min(pd.coveragePct, 100)}%` }}
                    />
                    <div className="absolute top-0 bottom-0 w-0.5 bg-red-400" style={{ left: '70%' }} title="70% bankable threshold" />
                  </div>
                </div>
                {pd.meetsThreshold ? (
                  <CheckCircle className="w-5 h-5 text-emerald-500" />
                ) : pd.signals.length > 0 ? (
                  <AlertTriangle className="w-5 h-5 text-amber-400" />
                ) : (
                  <Target className="w-5 h-5 text-gray-300" />
                )}
              </div>
            </div>

            {/* Demand signals table */}
            {pd.signals.length > 0 ? (
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 text-left">
                    <th className="px-5 py-2 text-xs font-bold text-gray-500 uppercase tracking-wider">Buyer</th>
                    <th className="px-5 py-2 text-xs font-bold text-gray-500 uppercase tracking-wider text-right">Volume (MT/yr)</th>
                    <th className="px-5 py-2 text-xs font-bold text-gray-500 uppercase tracking-wider">Stage</th>
                    <th className="px-5 py-2 text-xs font-bold text-gray-500 uppercase tracking-wider">Price</th>
                    <th className="px-5 py-2 text-xs font-bold text-gray-500 uppercase tracking-wider">Expires</th>
                    <th className="px-5 py-2 text-xs font-bold text-gray-500 uppercase tracking-wider">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {pd.signals
                    .sort((a, b) => (STAGE_ORDER[b.stage] ?? 0) - (STAGE_ORDER[a.stage] ?? 0))
                    .map((sig, i) => (
                    <tr key={i} className="hover:bg-gray-50/50">
                      <td className="px-5 py-2.5 font-semibold text-gray-900 flex items-center gap-2">
                        <Users className="w-3.5 h-3.5 text-gray-400" /> {sig.buyer}
                      </td>
                      <td className="px-5 py-2.5 text-right font-mono font-bold text-gray-700">{sig.volume_mt_pa.toLocaleString()}</td>
                      <td className="px-5 py-2.5">
                        <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full border ${STAGE_STYLE[sig.stage]}`}>
                          {sig.stage.replace('_', ' ')}
                        </span>
                      </td>
                      <td className="px-5 py-2.5 text-gray-600 text-xs">{sig.price_indication}</td>
                      <td className="px-5 py-2.5 text-xs text-gray-500 font-mono">{sig.expires ?? '—'}</td>
                      <td className="px-5 py-2.5">
                        {sig.stage === 'EOI' && (
                          <button onClick={() => navigate(`/matching?mode=sell&project=${pd.project.id}`)}
                            className="text-xs font-semibold text-gray-900 bg-gray-100 hover:bg-gray-200 px-2.5 py-1 rounded-md transition-colors">
                            Qualify <ArrowRight className="w-3 h-3 inline ml-1" />
                          </button>
                        )}
                        {sig.stage === 'LOI' && (
                          <button onClick={() => navigate('/term-sheet')}
                            className="text-xs font-semibold bg-amber-500 text-white hover:bg-amber-600 px-2.5 py-1 rounded-md transition-colors">
                            Advance <ArrowRight className="w-3 h-3 inline ml-1" />
                          </button>
                        )}
                        {sig.stage === 'TERM_SHEET' && (
                          <button onClick={() => navigate('/contracts')}
                            className="text-xs font-semibold bg-teal-600 text-white hover:bg-teal-700 px-2.5 py-1 rounded-md transition-colors">
                            Close <ArrowRight className="w-3 h-3 inline ml-1" />
                          </button>
                        )}
                        {sig.stage === 'CONTRACTED' && (
                          <span className="text-xs text-emerald-600 font-semibold">Secured</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="px-5 py-6 text-center">
                <p className="text-sm text-gray-400 mb-3">No demand signals yet for this project</p>
                <button onClick={() => navigate(`/matching?mode=sell&project=${pd.project.id}`)}
                  className="text-xs font-semibold bg-gray-900 text-white hover:bg-gray-800 px-4 py-2 rounded-lg transition-colors">
                  Scan Buyer RFQs <ArrowRight className="w-3 h-3 inline ml-1" />
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
