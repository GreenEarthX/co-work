import { useState, useEffect, useMemo } from 'react'
import { Plus, RefreshCw, Trash2, TrendingUp, Filter, Tag, Globe, CheckSquare, Square, AlertCircle } from 'lucide-react'
import { offersAPI, rfqsAPI } from '@/lib/api'

export function MarketplacePage() {
  const [offers, setOffers] = useState<any[]>([])
  const [rfqs, setRfqs] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<'supply' | 'demand'>('supply')
  const [selectedOffers, setSelectedOffers] = useState<Set<string>>(new Set())
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [filterMolecule, setFilterMolecule] = useState('all')
  const [filterRegion, setFilterRegion] = useState('all')

  // Create form state
  const [newOffer, setNewOffer] = useState({
    project: '', product: 'H2', volume: '', price: '', region: 'EU', delivery_start: '', delivery_end: '', stage: 'indicative',
  })

  useEffect(() => { loadData() }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [offRes, rfqRes] = await Promise.allSettled([
        offersAPI.list(),
        rfqsAPI.list(),
      ])
      setOffers(offRes.status === 'fulfilled' ? (offRes.value.offers || offRes.value.data || []) : [])
      setRfqs(rfqRes.status === 'fulfilled' ? (rfqRes.value.rfqs || rfqRes.value.data || []) : [])
    } catch (e) {
      console.error('Failed to load marketplace:', e)
    } finally {
      setLoading(false)
    }
  }

  const marketStats = useMemo(() => {
    const prices = offers.map(o => parseFloat(o.price || o.volume || '0')).filter(v => !isNaN(v) && v > 0)
    return {
      avg: prices.length ? (prices.reduce((a, b) => a + b, 0) / prices.length).toFixed(2) : '5.40',
      count: offers.length,
      rfqCount: rfqs.length,
    }
  }, [offers, rfqs])

  const toggleSelect = (id: string) => {
    const next = new Set(selectedOffers)
    next.has(id) ? next.delete(id) : next.add(id)
    setSelectedOffers(next)
  }

  const handleBulkDelete = async () => {
    if (!confirm(`Delete ${selectedOffers.size} selected listings?`)) return
    try {
      await Promise.all(Array.from(selectedOffers).map(id => offersAPI.delete(id)))
      setSelectedOffers(new Set())
      loadData()
    } catch { alert('Bulk delete failed') }
  }

  const handleCreateOffer = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await offersAPI.create({
        ...newOffer,
        volume: parseFloat(newOffer.volume),
        price: parseFloat(newOffer.price),
      })
      setShowCreateForm(false)
      setNewOffer({ project: '', product: 'H2', volume: '', price: '', region: 'EU', delivery_start: '', delivery_end: '', stage: 'indicative' })
      loadData()
    } catch { alert('Failed to create offer') }
  }

  const filteredOffers = offers.filter(o => {
    if (filterMolecule !== 'all' && (o.product || o.molecule) !== filterMolecule) return false
    if (filterRegion !== 'all' && o.region !== filterRegion) return false
    return true
  })

  const molecules = [...new Set(offers.map(o => o.product || o.molecule).filter(Boolean))]
  const regions = [...new Set(offers.map(o => o.region).filter(Boolean))]

  if (loading) return <div className="p-10 text-center text-gray-500"><RefreshCw className="w-8 h-8 animate-spin mx-auto mb-3 text-blue-500" />Loading market data...</div>

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black text-gray-900">Marketplace</h1>
          <p className="text-sm text-gray-600 mt-1">Manage inventory, offers, and market demand</p>
        </div>
        <div className="flex gap-2">
          {selectedOffers.size > 0 && (
            <button onClick={handleBulkDelete} className="flex items-center gap-1 px-3 py-2 bg-red-50 text-red-600 border border-red-200 rounded-lg text-xs font-bold hover:bg-red-100">
              <Trash2 className="w-3 h-3" /> Delete ({selectedOffers.size})
            </button>
          )}
          <button onClick={() => setShowCreateForm(!showCreateForm)} className="flex items-center gap-1 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-semibold hover:bg-blue-700">
            <Plus className="w-4 h-4" /> New Listing
          </button>
          <button onClick={loadData} className="p-2 hover:bg-gray-100 rounded-lg">
            <RefreshCw className="w-5 h-5 text-gray-600" />
          </button>
        </div>
      </div>

      {/* Market Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white p-4 border border-gray-200 rounded-xl">
          <div className="flex items-center gap-2 text-xs font-bold text-gray-500 uppercase mb-2">
            <TrendingUp className="w-3 h-3 text-green-600" /> Avg Price
          </div>
          <div className="text-2xl font-black text-gray-900">€{marketStats.avg}<span className="text-xs font-normal text-gray-400 ml-1">/kg</span></div>
        </div>
        <div className="bg-white p-4 border border-gray-200 rounded-xl">
          <div className="flex items-center gap-2 text-xs font-bold text-gray-500 uppercase mb-2">
            <Tag className="w-3 h-3 text-blue-600" /> Active Listings
          </div>
          <div className="text-2xl font-black text-gray-900">{marketStats.count}</div>
        </div>
        <div className="bg-white p-4 border border-gray-200 rounded-xl">
          <div className="flex items-center gap-2 text-xs font-bold text-gray-500 uppercase mb-2">
            <Globe className="w-3 h-3 text-amber-600" /> Open RFQs
          </div>
          <div className="text-2xl font-black text-gray-900">{marketStats.rfqCount}</div>
        </div>
      </div>

      {/* Create Form */}
      {showCreateForm && (
        <form onSubmit={handleCreateOffer} className="bg-white rounded-xl border border-blue-200 p-6">
          <h3 className="font-bold text-gray-900 mb-4">Create New Listing</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Project Name</label>
              <input type="text" required value={newOffer.project} onChange={e => setNewOffer({ ...newOffer, project: e.target.value })} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Molecule</label>
              <select value={newOffer.product} onChange={e => setNewOffer({ ...newOffer, product: e.target.value })} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                <option>H2</option><option>NH3</option><option>SAF</option><option>eMeOH</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Volume (MT)</label>
              <input type="number" step="0.1" required value={newOffer.volume} onChange={e => setNewOffer({ ...newOffer, volume: e.target.value })} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Price (EUR/kg)</label>
              <input type="number" step="0.01" required value={newOffer.price} onChange={e => setNewOffer({ ...newOffer, price: e.target.value })} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm" />
            </div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Region</label>
              <select value={newOffer.region} onChange={e => setNewOffer({ ...newOffer, region: e.target.value })} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                <option>EU</option><option>APAC</option><option>MENA</option><option>Americas</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Stage</label>
              <select value={newOffer.stage} onChange={e => setNewOffer({ ...newOffer, stage: e.target.value })} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                <option value="indicative">Indicative</option><option value="firm">Firm</option><option value="binding">Binding</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Delivery Start</label>
              <input type="date" value={newOffer.delivery_start} onChange={e => setNewOffer({ ...newOffer, delivery_start: e.target.value })} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Delivery End</label>
              <input type="date" value={newOffer.delivery_end} onChange={e => setNewOffer({ ...newOffer, delivery_end: e.target.value })} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm" />
            </div>
          </div>
          <div className="flex gap-2">
            <button type="submit" className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-semibold hover:bg-blue-700">Create Listing</button>
            <button type="button" onClick={() => setShowCreateForm(false)} className="px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-600 hover:bg-gray-50">Cancel</button>
          </div>
        </form>
      )}

      {/* Tabs */}
      <div className="flex items-center border-b border-gray-200">
        <button onClick={() => setTab('supply')} className={`px-4 py-2 text-sm font-semibold border-b-2 transition-colors ${tab === 'supply' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
          Your Supply ({filteredOffers.length})
        </button>
        <button onClick={() => setTab('demand')} className={`px-4 py-2 text-sm font-semibold border-b-2 transition-colors ${tab === 'demand' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
          Market Demand ({rfqs.length})
        </button>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3">
        <Filter className="w-4 h-4 text-gray-400" />
        <select value={filterMolecule} onChange={e => setFilterMolecule(e.target.value)} className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm">
          <option value="all">All Molecules</option>
          {molecules.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
        <select value={filterRegion} onChange={e => setFilterRegion(e.target.value)} className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm">
          <option value="all">All Regions</option>
          {regions.map(r => <option key={r} value={r}>{r}</option>)}
        </select>
      </div>

      {/* Supply Tab */}
      {tab === 'supply' && (
        <div className="space-y-3">
          {filteredOffers.length === 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-8 text-center text-gray-500">
              No listings found. Create one to start.
            </div>
          )}
          {filteredOffers.map(offer => {
            const hasMatch = rfqs.some(r => (r.product || r.molecule) === (offer.product || offer.molecule) && r.region === offer.region)
            return (
              <div key={offer.id} className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
                <div className="px-5 py-4 flex justify-between items-center bg-gray-50/50">
                  <div className="flex items-center gap-4">
                    <button onClick={() => toggleSelect(offer.id)}>
                      {selectedOffers.has(offer.id) ? <CheckSquare className="w-4 h-4 text-blue-600" /> : <Square className="w-4 h-4 text-gray-300" />}
                    </button>
                    <div>
                      <h3 className="text-sm font-bold text-gray-900">{offer.project || offer.name || 'Unnamed'}</h3>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-xs font-bold px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">{offer.product || offer.molecule || 'H2'}</span>
                        <span className={`text-xs font-semibold px-2 py-0.5 rounded ${offer.stage === 'firm' ? 'bg-green-50 text-green-700' : offer.stage === 'binding' ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-100 text-gray-600'}`}>{offer.stage || 'indicative'}</span>
                        {hasMatch && (
                          <span className="flex items-center gap-1 text-xs font-bold text-amber-600 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                            <AlertCircle className="w-3 h-3" /> Demand Match
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-bold text-gray-900">{offer.volume} {typeof offer.volume === 'number' ? 'MT' : ''}</div>
                    <div className="text-xs text-gray-400">{offer.region}</div>
                  </div>
                </div>
                <div className="px-5 py-3 border-t border-gray-100">
                  <div className="flex justify-between text-xs text-gray-500 mb-1">
                    <span>Allocation</span>
                    <span className="font-bold">60%</span>
                  </div>
                  <div className="w-full bg-gray-100 rounded-full h-1.5 flex overflow-hidden">
                    <div className="bg-green-500 h-full" style={{ width: '40%' }} />
                    <div className="bg-blue-500 h-full" style={{ width: '20%' }} />
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Demand Tab */}
      {tab === 'demand' && (
        <div className="space-y-3">
          {rfqs.length === 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-8 text-center text-gray-500">
              No open RFQs in the market.
            </div>
          )}
          {rfqs.map((rfq: any) => (
            <div key={rfq.id} className="bg-white border border-gray-200 rounded-xl p-5">
              <div className="flex justify-between items-center">
                <div>
                  <h3 className="font-bold text-gray-900">{rfq.buyer || rfq.counterparty || 'Anonymous Buyer'}</h3>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs font-bold px-2 py-0.5 rounded bg-purple-50 text-purple-700 border border-purple-200">{rfq.product || rfq.molecule || 'H2'}</span>
                    <span className="text-xs text-gray-500">{rfq.volume || rfq.volume_mtpd || '—'} MT</span>
                    <span className="text-xs text-gray-500">{rfq.region || '—'}</span>
                  </div>
                </div>
                <button className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs font-semibold hover:bg-blue-700">
                  Respond
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
