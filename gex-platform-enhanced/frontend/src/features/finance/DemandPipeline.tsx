// Screen: Demand pipeline screen (/finance-demand)
/**
 * Sales — downstream buyers per project.
 *
 * Real data only (2026-10-25). This screen used to manufacture "demand signals":
 * each buyer's volume as a fixed fraction of nameplate × 330 days (75 %, 55 %,
 * 30 %, 15 %, 10 %), with invented price indications and expiry dates, chosen by
 * the offtake gate's completion — and a coverage % computed from those
 * inventions. Now it shows what is recorded: the buyers named for the project
 * (project_dataset demand_buyers, UNVERIFIED) and the offtake gate's real
 * completion. Volumes, prices and coverage come from offers and contracts, on
 * the matching and contracts screens.
 */

import { useState } from 'react'
import { ArrowRight, Users, Filter } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { type CustomerProject } from '@/data/customerProjects'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'
import { useProjectDataset, UnverifiedBadge } from './useProjectDataset'

function ProjectBuyers({ project }: { project: CustomerProject }) {
  const navigate = useNavigate()
  const ds = useProjectDataset<string[]>('demand_buyers', project.id)
  const g4 = project.bankability?.gates?.find(g => g.id === 'G4_OFFTAKE_BANKABLE')

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between gap-4">
        <div>
          <h3 className="text-sm font-bold text-gray-900">{project.name}</h3>
          <div className="flex items-center gap-2 mt-0.5 text-xs text-gray-500">
            <span className="font-bold px-2 py-0.5 rounded bg-gray-100 text-gray-700 border border-gray-200">{project.molecule}</span>
            <span>{project.location}</span>
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs text-gray-500">Offtake gate (G4)</div>
          <div className="text-sm font-bold text-gray-900">
            {g4 ? (g4.is_complete ? 'Complete' : `${g4.completion_pct}% complete`) : 'Not evaluated'}
          </div>
        </div>
      </div>
      <div className="px-5 py-3">
        {ds.loading ? (
          <p className="text-sm text-gray-400">Loading…</p>
        ) : ds.error ? (
          <p className="text-sm text-amber-700">Buyers unavailable: {ds.error}</p>
        ) : ds.data && ds.data.length > 0 ? (
          <div className="flex flex-wrap items-center gap-2">
            <UnverifiedBadge verification={ds.verification} />
            {ds.data.map(b => (
              <span key={b} className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs font-semibold text-gray-800">
                <Users className="w-3.5 h-3.5 text-gray-400" /> {b}
              </span>
            ))}
          </div>
        ) : (
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-400">No buyer is recorded for this project.</p>
            <button onClick={() => navigate(`/matching?mode=sell&project=${project.id}`)}
              className="text-xs font-semibold bg-gray-900 text-white hover:bg-gray-800 px-4 py-2 rounded-lg transition-colors">
              Scan Buyer RFQs <ArrowRight className="w-3 h-3 inline ml-1" />
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export function DemandPipeline() {
  const navigate = useNavigate()
  const { projects: visibleProjects } = useVisibleProjects()
  const [filterMol, setFilterMol] = useState('all')
  const molecules = [...new Set(visibleProjects.map(p => p.molecule))]
  const shown = visibleProjects.filter(p => filterMol === 'all' || p.molecule === filterMol)

  return (
    <div className="max-w-[1440px] mx-auto space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-black text-gray-900">Sales</h1>
          <p className="text-sm text-gray-500 mt-1">
            Buyers named for each project, and how far its offtake gate has progressed.
            Volumes, prices and coverage come from offers and contracts.
          </p>
        </div>
        <button
          onClick={() => navigate('/matching?mode=sell')}
          className="inline-flex items-center gap-2 px-4 py-2 bg-gray-900 text-white rounded-lg text-sm font-semibold hover:bg-gray-800 transition-colors"
        >
          Review Market Bids <ArrowRight className="w-4 h-4" />
        </button>
      </div>

      <div className="flex items-center gap-3">
        <Filter className="w-4 h-4 text-gray-400" />
        <select value={filterMol} onChange={e => setFilterMol(e.target.value)}
          className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm bg-white">
          <option value="all">All Molecules</option>
          {molecules.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>

      <div className="space-y-4">
        {shown.length === 0 && <p className="text-sm text-gray-400">No visible projects.</p>}
        {shown.map(p => <ProjectBuyers key={p.id} project={p} />)}
      </div>
    </div>
  )
}
