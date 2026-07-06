// Screen: Capacity screen (/capacity)
/**
 * GreenMesh — Capacity Publishing & Feedstock Aggregation
 *
 * Two clear purposes:
 *
 * 1. PUBLISH DOWNSTREAM CAPACITY — The client creates sales capacity
 *    visible to third-party offtakers. This screen shows confirmation of
 *    what has been published, its status, and where it is displayed.
 *
 * 2. REQUEST UPSTREAM FEEDSTOCK — The client seeks feedstock via GreenMesh
 *    aggregation. The screen shows the aggregation principle: multiple
 *    small suppliers pooled into a single bankable supply line.
 *
 * Data sourced from CUSTOMER_PROJECTS canonical registry.
 */

import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowUpRight, ArrowDownLeft, CheckCircle, Clock, Globe,
  Layers, Plus,
} from 'lucide-react'
import { type CustomerProject } from '@/data/customerProjects'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'

// ── Types ────────────────────────────────────────────────────────────────────

type PublishStatus = 'live' | 'pending' | 'draft'

interface PublishedCapacity {
  projectId: string
  project: string
  molecule: string
  location: string
  capacity_mtpd: number
  availableVolume_mt_pa: number
  publishedDate: string
  status: PublishStatus
  views: number
  enquiries: number
}

interface FeedstockRequest {
  id: string
  projectId: string
  project: string
  feedstock: string
  requiredVolume_mt_pa: number
  suppliersPooled: number
  aggregatedVolume_mt_pa: number
  coveragePct: number
  status: 'fulfilled' | 'partial' | 'open'
  greenmeshSaving: string
}

// ── Build data from projects ─────────────────────────────────────────────────

function buildPublishedCapacities(projects: CustomerProject[]): PublishedCapacity[] {
  return projects.map(p => {
    const g4 = p.bankability.gates.find(g => g.id === 'G4_OFFTAKE_BANKABLE')
    const g4pct = g4?.completion_pct ?? 0
    const annualCap = Math.round(p.capacity_mtpd * 330)
    // Available = total minus what's already committed
    const committed = Math.round(annualCap * (g4pct / 100) * 0.8)
    const available = annualCap - committed

    let status: PublishStatus = 'draft'
    if (p.status === 'operating') status = 'live'
    else if (p.status === 'construction') status = 'pending'

    return {
      projectId: p.id,
      project: p.name,
      molecule: p.molecule,
      location: p.location,
      capacity_mtpd: p.capacity_mtpd,
      availableVolume_mt_pa: Math.max(available, 0),
      publishedDate: p.status === 'operating' ? '2025-12-01' : p.status === 'construction' ? '2026-03-15' : '',
      status,
      views: p.status === 'operating' ? 142 : p.status === 'construction' ? 38 : 0,
      enquiries: p.status === 'operating' ? 7 : p.status === 'construction' ? 2 : 0,
    }
  })
}

const FEEDSTOCK_REQUESTS: FeedstockRequest[] = [
  {
    id: 'fr-1', projectId: 'proj_bremen_h2', project: 'Bremen Green Hydrogen Plant',
    feedstock: 'Green Electricity (Wind PPA)', requiredVolume_mt_pa: 36000,
    suppliersPooled: 4, aggregatedVolume_mt_pa: 38500, coveragePct: 100,
    status: 'fulfilled', greenmeshSaving: '-8% vs single-source PPA',
  },
  {
    id: 'fr-2', projectId: 'proj_rotterdam_nh3', project: 'Rotterdam Green Ammonia Terminal',
    feedstock: 'Green Electricity (Grid PPA)', requiredVolume_mt_pa: 72000,
    suppliersPooled: 2, aggregatedVolume_mt_pa: 45000, coveragePct: 62,
    status: 'partial', greenmeshSaving: '-5% vs spot procurement',
  },
  {
    id: 'fr-3', projectId: 'proj_sansebastian_emethanol', project: 'Project Helios e-Methanol',
    feedstock: 'Biogenic CO2', requiredVolume_mt_pa: 8400,
    suppliersPooled: 3, aggregatedVolume_mt_pa: 7200, coveragePct: 86,
    status: 'partial', greenmeshSaving: '-12% vs individual contracts',
  },
  {
    id: 'fr-4', projectId: 'proj_wales_saf', project: 'Celtic Green SAF Complex',
    feedstock: 'Green Hydrogen', requiredVolume_mt_pa: 2800,
    suppliersPooled: 0, aggregatedVolume_mt_pa: 0, coveragePct: 0,
    status: 'open', greenmeshSaving: 'Estimated -6% with 3+ suppliers',
  },
  {
    id: 'fr-5', projectId: 'proj_hamburgone_emethanol', project: 'HamburgOne e-Methanol Plant',
    feedstock: 'Biogenic CO2', requiredVolume_mt_pa: 8400,
    suppliersPooled: 0, aggregatedVolume_mt_pa: 0, coveragePct: 0,
    status: 'open', greenmeshSaving: 'Estimated -10% with pooling',
  },
  {
    id: 'fr-6', projectId: 'proj_lehavre_eng', project: 'Le Havre e-Gas Hub',
    feedstock: 'Biogenic CO2 (Offshore)', requiredVolume_mt_pa: 18000,
    suppliersPooled: 5, aggregatedVolume_mt_pa: 19200, coveragePct: 100,
    status: 'fulfilled', greenmeshSaving: '-15% vs bilateral agreements',
  },
]

// ── Sub-components ───────────────────────────────────────────────────────────

function PublishBadge({ status }: { status: PublishStatus }) {
  const s: Record<PublishStatus, { style: string; label: string; Icon: React.ElementType }> = {
    live:    { style: 'bg-emerald-50 text-emerald-700 border-emerald-200', label: 'LIVE', Icon: Globe },
    pending: { style: 'bg-amber-50 text-amber-700 border-amber-200', label: 'PENDING', Icon: Clock },
    draft:   { style: 'bg-gray-100 text-gray-500 border-gray-200', label: 'DRAFT', Icon: Clock },
  }
  const { style, label, Icon } = s[status]
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-bold uppercase px-2 py-0.5 rounded-full border ${style}`}>
      <Icon className="w-2.5 h-2.5" /> {label}
    </span>
  )
}

function CoverageBadge({ status }: { status: 'fulfilled' | 'partial' | 'open' }) {
  const s: Record<string, string> = {
    fulfilled: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    partial:   'bg-amber-50 text-amber-700 border-amber-200',
    open:      'bg-gray-100 text-gray-500 border-gray-200',
  }
  return (
    <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full border ${s[status]}`}>
      {status}
    </span>
  )
}

// ── Main Component ───────────────────────────────────────────────────────────

type Tab = 'publish' | 'feedstock'

export function CapacityPage() {
  const navigate = useNavigate()
  const { projects: visibleProjects } = useVisibleProjects()
  const [tab, setTab] = useState<Tab>('publish')
  const [filterMol, setFilterMol] = useState('all')

  const molecules = [...new Set(visibleProjects.map(p => p.molecule))]

  const published = useMemo(() => {
    const all = buildPublishedCapacities(visibleProjects)
    return filterMol === 'all' ? all : all.filter(c => c.molecule === filterMol)
  }, [filterMol, visibleProjects])

  const feedstockReqs = useMemo(() => {
    return filterMol === 'all' ? FEEDSTOCK_REQUESTS : FEEDSTOCK_REQUESTS.filter(fr => {
      const proj = visibleProjects.find(p => p.id === fr.projectId)
      return proj?.molecule === filterMol
    })
  }, [filterMol, visibleProjects])

  const liveCount = published.filter(c => c.status === 'live').length
  const totalEnquiries = published.reduce((s, c) => s + c.enquiries, 0)
  const fulfilledCount = feedstockReqs.filter(f => f.status === 'fulfilled').length

  return (
    <div className="max-w-[1440px] mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-black text-gray-900">GreenMesh</h1>
          <p className="text-sm text-gray-500 mt-1">
            Publish downstream capacity for offtakers & aggregate upstream feedstock
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select value={filterMol} onChange={e => setFilterMol(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm bg-white">
            <option value="all">All Molecules</option>
            {molecules.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
      </div>

      {/* Tab Toggle */}
      <div className="flex items-center gap-1">
        <button onClick={() => setTab('publish')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-colors ${tab === 'publish' ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-500 hover:bg-gray-200'}`}>
          <ArrowUpRight className="w-3.5 h-3.5" /> Published Capacity (Downstream)
        </button>
        <button onClick={() => setTab('feedstock')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-colors ${tab === 'feedstock' ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-500 hover:bg-gray-200'}`}>
          <ArrowDownLeft className="w-3.5 h-3.5" /> Feedstock Aggregation (Upstream)
        </button>
      </div>

      {/* ─── TAB 1: Published Capacity ────────────────────────────────────── */}
      {tab === 'publish' && (
        <>
          {/* KPIs */}
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">Live Listings</div>
              <div className="text-2xl font-black text-emerald-600">{liveCount}</div>
              <div className="text-xs text-gray-500 mt-1">visible to third-party offtakers</div>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">Total Enquiries</div>
              <div className="text-2xl font-black text-gray-900">{totalEnquiries}</div>
              <div className="text-xs text-gray-500 mt-1">from potential buyers</div>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">Pending Publish</div>
              <div className="text-2xl font-black text-amber-600">{published.filter(c => c.status === 'pending').length}</div>
              <div className="text-xs text-gray-500 mt-1">construction-phase projects</div>
            </div>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="px-5 py-3.5 border-b border-gray-100 flex items-center justify-between">
              <h2 className="text-sm font-bold text-gray-900">Your Published Capacity — visible on GreenMesh marketplace</h2>
              <span className="text-xs text-gray-400">{published.length} project{published.length !== 1 ? 's' : ''}</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="bg-gray-50 text-left">
                  {['Project', 'Molecule', 'Location', 'Capacity', 'Available', 'Status', 'Views', 'Enquiries', ''].map(h => (
                    <th key={h} className={`px-5 py-2.5 text-xs font-bold text-gray-500 uppercase tracking-wider ${['Capacity', 'Available', 'Views', 'Enquiries'].includes(h) ? 'text-right' : ''}`}>{h}</th>
                  ))}
                </tr></thead>
                <tbody className="divide-y divide-gray-100">
                  {published.map(c => (
                    <tr key={c.projectId} className="hover:bg-gray-50/50">
                      <td className="px-5 py-3 font-semibold text-gray-900">{c.project}</td>
                      <td className="px-5 py-3"><span className="text-xs font-bold px-2 py-0.5 rounded bg-gray-100 text-gray-700 border border-gray-200">{c.molecule}</span></td>
                      <td className="px-5 py-3 text-gray-600">{c.location}</td>
                      <td className="px-5 py-3 text-right font-mono text-gray-700">{c.capacity_mtpd} MTPD</td>
                      <td className="px-5 py-3 text-right font-mono font-bold text-gray-900">{c.availableVolume_mt_pa.toLocaleString()} MT/yr</td>
                      <td className="px-5 py-3"><PublishBadge status={c.status} /></td>
                      <td className="px-5 py-3 text-right font-mono text-gray-500">{c.views > 0 ? c.views : '—'}</td>
                      <td className="px-5 py-3 text-right font-mono text-gray-500">{c.enquiries > 0 ? c.enquiries : '—'}</td>
                      <td className="px-5 py-3">
                        {c.status === 'live' ? (
                          <button onClick={() => navigate(`/finance-demand`)}
                            className="text-xs font-semibold bg-emerald-600 text-white hover:bg-emerald-700 px-3 py-1.5 rounded-md transition-colors">
                            View Demand
                          </button>
                        ) : c.status === 'pending' ? (
                          <button onClick={() => navigate(`/marketplace`)}
                            className="text-xs font-semibold bg-amber-500 text-white hover:bg-amber-600 px-3 py-1.5 rounded-md transition-colors">
                            Review
                          </button>
                        ) : (
                          <button onClick={() => navigate(`/marketplace`)}
                            className="text-xs font-semibold bg-gray-900 text-white hover:bg-gray-800 px-3 py-1.5 rounded-md transition-colors">
                            Publish
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="px-5 py-3 border-t border-gray-100 bg-gray-50">
              <p className="text-[10px] text-gray-500">
                <Globe className="w-3 h-3 inline mr-1 text-gray-400" />
                <strong>LIVE</strong> listings are visible to registered offtakers on the GreenMesh marketplace.
                Enquiries appear in <strong>Sales</strong> as EOI signals.
                <strong> PENDING</strong> listings become LIVE once the project reaches COD.
              </p>
            </div>
          </div>
        </>
      )}

      {/* ─── TAB 2: Feedstock Aggregation ─────────────────────────────────── */}
      {tab === 'feedstock' && (
        <>
          {/* Explainer */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 rounded-lg bg-teal-50 flex items-center justify-center flex-shrink-0">
                <Layers className="w-5 h-5 text-teal-600" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-gray-900">How GreenMesh Aggregation Works</h3>
                <p className="text-xs text-gray-500 mt-1 leading-relaxed max-w-2xl">
                  Instead of negotiating individual feedstock contracts with each supplier, GreenMesh pools
                  multiple small-volume suppliers into a single bankable supply line. This reduces procurement
                  cost (typically 5–15%), improves supply security through diversification, and creates a
                  single contract counterparty for your finance team.
                </p>
              </div>
            </div>
          </div>

          {/* KPIs */}
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">Fulfilled</div>
              <div className="text-2xl font-black text-emerald-600">{fulfilledCount}</div>
              <div className="text-xs text-gray-500 mt-1">feedstock lines fully covered</div>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">Open Requests</div>
              <div className="text-2xl font-black text-amber-600">{feedstockReqs.filter(f => f.status === 'open').length}</div>
              <div className="text-xs text-gray-500 mt-1">seeking aggregation</div>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">Suppliers Pooled</div>
              <div className="text-2xl font-black text-gray-900">{feedstockReqs.reduce((s, f) => s + f.suppliersPooled, 0)}</div>
              <div className="text-xs text-gray-500 mt-1">across all requests</div>
            </div>
          </div>

          {/* Table */}
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="px-5 py-3.5 border-b border-gray-100 flex items-center justify-between">
              <h2 className="text-sm font-bold text-gray-900">Feedstock Aggregation Requests</h2>
              <button onClick={() => navigate('/marketplace')}
                className="text-xs font-semibold bg-gray-900 text-white hover:bg-gray-800 px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1">
                <Plus className="w-3 h-3" /> New Request
              </button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="bg-gray-50 text-left">
                  {['Project', 'Feedstock', 'Required', 'Pooled Suppliers', 'Aggregated', 'Coverage', 'Saving', 'Status', ''].map(h => (
                    <th key={h} className={`px-5 py-2.5 text-xs font-bold text-gray-500 uppercase tracking-wider ${['Required', 'Pooled Suppliers', 'Aggregated'].includes(h) ? 'text-right' : ''}`}>{h}</th>
                  ))}
                </tr></thead>
                <tbody className="divide-y divide-gray-100">
                  {feedstockReqs.map(fr => (
                    <tr key={fr.id} className="hover:bg-gray-50/50">
                      <td className="px-5 py-3 font-semibold text-gray-900">{fr.project}</td>
                      <td className="px-5 py-3"><span className="text-xs font-bold px-2 py-0.5 rounded bg-gray-100 text-gray-600 border border-gray-200">{fr.feedstock}</span></td>
                      <td className="px-5 py-3 text-right font-mono text-gray-700">{fr.requiredVolume_mt_pa.toLocaleString()} MT</td>
                      <td className="px-5 py-3 text-right font-mono font-bold text-gray-900">{fr.suppliersPooled || '—'}</td>
                      <td className="px-5 py-3 text-right font-mono text-gray-700">{fr.aggregatedVolume_mt_pa > 0 ? `${fr.aggregatedVolume_mt_pa.toLocaleString()} MT` : '—'}</td>
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-2">
                          <div className="w-14 bg-gray-100 rounded-full h-1.5">
                            <div className={`h-full rounded-full ${fr.coveragePct >= 100 ? 'bg-emerald-500' : fr.coveragePct >= 50 ? 'bg-amber-400' : 'bg-gray-300'}`}
                              style={{ width: `${Math.min(fr.coveragePct, 100)}%` }} />
                          </div>
                          <span className="text-xs font-mono text-gray-500">{fr.coveragePct}%</span>
                        </div>
                      </td>
                      <td className="px-5 py-3 text-xs text-teal-600 font-semibold">{fr.greenmeshSaving}</td>
                      <td className="px-5 py-3"><CoverageBadge status={fr.status} /></td>
                      <td className="px-5 py-3">
                        {fr.status === 'open' ? (
                          <button className="text-xs font-semibold bg-teal-600 text-white hover:bg-teal-700 px-3 py-1.5 rounded-md transition-colors">
                            Find Suppliers
                          </button>
                        ) : fr.status === 'partial' ? (
                          <button className="text-xs font-semibold bg-amber-500 text-white hover:bg-amber-600 px-3 py-1.5 rounded-md transition-colors">
                            Add More
                          </button>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-xs text-emerald-600 font-semibold">
                            <CheckCircle className="w-3 h-3" /> Covered
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="px-5 py-3 border-t border-gray-100 bg-gray-50">
              <p className="text-[10px] text-gray-500">
                <Layers className="w-3 h-3 inline mr-1 text-gray-400" />
                GreenMesh aggregation pools multiple suppliers into a single supply line with better pricing
                and diversified risk. Savings shown are estimated vs. single-source procurement.
              </p>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
