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
 * Projects come from the canonical registry; listing status and matches come
 * from the market engine (/api/v1/market). Until 2026-10-23 both tabs showed
 * invented numbers — views, enquiries, publish dates and six feedstock pools
 * (gap register G-04). Feedstock aggregation has no backend yet, so that tab
 * now says so instead of showing pools that do not exist.
 */

import { useEffect, useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowUpRight, ArrowDownLeft, Clock, Globe,
  Layers, Plus,
} from 'lucide-react'
import { type CustomerProject } from '@/data/customerProjects'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'
import { marketAPI, type MarketMatch, type OfferListing } from '@/api'

// ── Types ────────────────────────────────────────────────────────────────────

type PublishStatus = 'live' | 'pending' | 'draft'

interface PublishedCapacity {
  projectId: string
  project: string
  molecule: string
  location: string
  capacity_mtpd: number
  listedVolume_mtpd: number
  status: PublishStatus
  matches: number
}

// ── Build data from projects ─────────────────────────────────────────────────

function buildPublishedCapacities(projects: CustomerProject[], listings: OfferListing[],
                                  matches: MarketMatch[]): PublishedCapacity[] {
  return projects.map(p => {
    // No "available" estimate: it was 330 operating days times an assumed 80% of
    // the G4 completion, neither of them a recorded figure (removed 2026-10-23).
    const live = listings.filter(l => l.mine && l.project_id === p.id)

    return {
      projectId: p.id,
      project: p.name,
      molecule: p.molecule,
      location: p.location,
      capacity_mtpd: p.capacity_mtpd,
      listedVolume_mtpd: live.reduce((sum, l) => sum + l.volume_mtpd, 0),
      status: live.length ? 'live' : 'draft',
      matches: matches.filter(m => m.side === 'seller' && m.project_id === p.id).length,
    }
  })
}

// ── Sub-components ───────────────────────────────────────────────────────────

function PublishBadge({ status }: { status: PublishStatus }) {
  const s: Record<PublishStatus, { style: string; label: string; Icon: React.ElementType }> = {
    live:    { style: 'bg-emerald-50 text-emerald-700 border-emerald-200', label: 'LIVE', Icon: Globe },
    pending: { style: 'bg-amber-50 text-amber-700 border-amber-200', label: 'PENDING', Icon: Clock },
    draft:   { style: 'bg-gray-100 text-gray-500 border-gray-200', label: 'NOT LISTED', Icon: Clock },
  }
  const { style, label, Icon } = s[status]
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-bold uppercase px-2 py-0.5 rounded-full border ${style}`}>
      <Icon className="w-2.5 h-2.5" /> {label}
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

  const [listings, setListings] = useState<OfferListing[]>([])
  const [matches, setMatches] = useState<MarketMatch[]>([])
  const [marketError, setMarketError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([marketAPI.offerListings(), marketAPI.myMatches()])
      .then(([o, m]) => { setListings(o.offers); setMatches(m.matches) })
      .catch(e => setMarketError((e as Error).message))
  }, [])

  const published = useMemo(() => {
    const all = buildPublishedCapacities(visibleProjects, listings, matches)
    return filterMol === 'all' ? all : all.filter(c => c.molecule === filterMol)
  }, [filterMol, visibleProjects, listings, matches])

  const liveCount = published.filter(c => c.status === 'live').length
  const totalMatches = published.reduce((s, c) => s + c.matches, 0)

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
          {marketError && (
            <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">{marketError}</div>
          )}
          {/* KPIs */}
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">Live Listings</div>
              <div className="text-2xl font-black text-emerald-600">{liveCount}</div>
              <div className="text-xs text-gray-500 mt-1">open on the market, anonymised</div>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">Matches</div>
              <div className="text-2xl font-black text-gray-900">{totalMatches}</div>
              <div className="text-xs text-gray-500 mt-1">with buyers' RFQs, on your listings</div>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">Not Listed</div>
              <div className="text-2xl font-black text-amber-600">{published.filter(c => c.status !== 'live').length}</div>
              <div className="text-xs text-gray-500 mt-1">projects with no open listing</div>
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
                  {['Project', 'Molecule', 'Location', 'Capacity', 'Listed', 'Status', 'Matches', ''].map(h => (
                    <th key={h} className={`px-5 py-2.5 text-xs font-bold text-gray-500 uppercase tracking-wider ${['Capacity', 'Listed', 'Matches'].includes(h) ? 'text-right' : ''}`}>{h}</th>
                  ))}
                </tr></thead>
                <tbody className="divide-y divide-gray-100">
                  {published.map(c => (
                    <tr key={c.projectId} className="hover:bg-gray-50/50">
                      <td className="px-5 py-3 font-semibold text-gray-900">{c.project}</td>
                      <td className="px-5 py-3"><span className="text-xs font-bold px-2 py-0.5 rounded bg-gray-100 text-gray-700 border border-gray-200">{c.molecule}</span></td>
                      <td className="px-5 py-3 text-gray-600">{c.location}</td>
                      <td className="px-5 py-3 text-right font-mono text-gray-700">{c.capacity_mtpd} MTPD</td>
                      <td className="px-5 py-3 text-right font-mono text-gray-700">{c.listedVolume_mtpd > 0 ? `${c.listedVolume_mtpd} MTPD` : '—'}</td>
                      <td className="px-5 py-3"><PublishBadge status={c.status} /></td>
                      <td className="px-5 py-3 text-right font-mono text-gray-500">{c.matches > 0 ? c.matches : '—'}</td>
                      <td className="px-5 py-3">
                        {c.status === 'live' ? (
                          <button onClick={() => navigate('/trader-dashboard')}
                            className="text-xs font-semibold bg-emerald-600 text-white hover:bg-emerald-700 px-3 py-1.5 rounded-md transition-colors">
                            View Matches
                          </button>
                        ) : (
                          <button onClick={() => navigate('/marketplace')}
                            className="text-xs font-semibold bg-gray-900 text-white hover:bg-gray-800 px-3 py-1.5 rounded-md transition-colors">
                            List on Market
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
                <strong>LIVE</strong> means at least one open listing on the market. Buyers see it without
                your company, project or location; your name is revealed only to a buyer you are matched with,
                and a match binds only when both of you accept.
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

          <div className="bg-white rounded-xl border border-amber-200 p-5">
            <h2 className="text-sm font-bold text-gray-900">Not built yet</h2>
            <p className="text-xs text-gray-600 mt-1 leading-relaxed max-w-2xl">
              Feedstock pooling has no backend on the platform today, so there are no pools to show — the
              figures that used to appear here were illustrative. A molecule feedstock (green hydrogen,
              ammonia, e-methanol) can already be requested on the market with an RFQ.
            </p>
            <button onClick={() => navigate('/rfqs')}
              className="mt-3 text-xs font-semibold bg-gray-900 text-white hover:bg-gray-800 px-3 py-1.5 rounded-lg transition-colors inline-flex items-center gap-1">
              <Plus className="w-3 h-3" /> Request a molecule feedstock
            </button>
          </div>
        </>
      )}
    </div>
  )
}
