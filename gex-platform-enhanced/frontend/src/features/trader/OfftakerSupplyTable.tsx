// Screen: Offtaker supply table screen (/offtaker-supply)
/**
 * OfftakerSupplyTable — Purchase
 *
 * Mirrors the same feedstock purchase ledger used in Commercial Overview.
 * Buyers use this screen to scan supplier offers and launch RFQs.
 */

import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Filter } from 'lucide-react'
import {
  buildFeedstockSummary,
  FeedstockPurchasesPanel,
} from '@/features/marketplace/MarketplacePage'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'

interface Props {
  molecule?: string
}

export function OfftakerSupplyTable({ molecule }: Props) {
  const navigate = useNavigate()
  const { projects: visibleProjects } = useVisibleProjects()
  const [filterMol, setFilterMol] = useState(molecule ?? 'all')
  const [filterProject, setFilterProject] = useState('all')

  const molecules = [...new Set(visibleProjects.map(p => p.molecule))]

  const filteredProjects = useMemo(() => {
    return visibleProjects.filter(project => {
      if (filterMol !== 'all' && project.molecule !== filterMol) return false
      if (filterProject !== 'all' && project.id !== filterProject) return false
      return true
    })
  }, [filterMol, filterProject, visibleProjects])

  const purchaseSummaries = useMemo(
    () => filteredProjects.map(project => buildFeedstockSummary(project)),
    [filteredProjects],
  )

  const matchingQuery = new URLSearchParams({ mode: 'buy' })
  if (filterProject !== 'all') matchingQuery.set('project', filterProject)

  return (
    <div className="max-w-[1440px] mx-auto space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
         {/*  <div className="inline-flex items-center gap-2 rounded-full bg-gray-100 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.12em] text-gray-600">
            <ShoppingCart className="w-3.5 h-3.5" />
            Purchase
          </div> */}
          <h2 className="mt-3 text-xl font-black text-gray-900">Scan suppliers, issue RFQs</h2>
          <p className="text-sm text-gray-500 mt-0.5 max-w-3xl">
            
            {/* Same feedstock purchases as Commercial Overview. 
            Buyers scan supplier offers here,
            then issue RFQs into the GEX marketplace. */}
          </p>
        </div>
        <button
          onClick={() => navigate(`/matching?${matchingQuery.toString()}`)}
          className="inline-flex items-center gap-2 rounded-lg bg-gray-900 px-4 py-2 text-sm font-semibold text-white hover:bg-gray-800 transition-colors"
        >
          Scan Supplier Offers
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>

      <div className="rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
        This screen is linked to <span className="font-semibold">Commercial Overview &gt; Feedstock Purchases</span>.
        The dataset stays identical for each visible client project.
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <Filter className="w-4 h-4 text-gray-400" />
        <select
          value={filterMol}
          onChange={e => {
            setFilterMol(e.target.value)
            setFilterProject('all')
          }}
          className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm bg-white"
        >
          <option value="all">All Molecules</option>
          {molecules.map(item => (
            <option key={item} value={item}>{item}</option>
          ))}
        </select>
        <select
          value={filterProject}
          onChange={e => setFilterProject(e.target.value)}
          className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm bg-white"
        >
          <option value="all">All Projects</option>
          {(filterMol !== 'all' ? visibleProjects.filter(p => p.molecule === filterMol) : visibleProjects)
            .map(project => (
              <option key={project.id} value={project.id}>{project.name}</option>
            ))}
        </select>
        <span className="text-xs text-gray-400 ml-auto">
          {purchaseSummaries.length} project{purchaseSummaries.length !== 1 ? 's' : ''}
        </span>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <FeedstockPurchasesPanel
          feedstockSummaries={purchaseSummaries}
          emptyMessage="No feedstock purchases match the current filter"
          renderProjectAction={summary => (
            <button
              onClick={() => navigate(`/matching?mode=buy&project=${summary.projectId}`)}
              className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-xs font-semibold text-gray-700 hover:bg-gray-50 transition-colors"
            >
              Match Offers
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          )}
        />
      </div>
    </div>
  )
}
