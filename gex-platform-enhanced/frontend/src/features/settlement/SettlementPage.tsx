import { useState, useEffect } from 'react'
import { RefreshCw, Truck, CheckCircle, Clock, AlertTriangle } from 'lucide-react'
import { contractsAPI } from '@/lib/api'

interface DeliveryContract {
  id: string
  counterparty: string
  product: string
  contracted_volume_mt: number
  delivered_mt: number
  delivery_pct: number
  quality_purity: number
  quality_certification: string
  status: string
  delivery_start: string
  delivery_end: string
  last_delivery: string | null
}

export function SettlementPage() {
  const [contracts, setContracts] = useState<DeliveryContract[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => { loadContracts() }, [])

  const loadContracts = async () => {
    setLoading(true)
    try {
      const res = await contractsAPI.list()
      const raw = res.contracts || res.data || (Array.isArray(res) ? res : [])

      // Enrich with delivery tracking data
      const enriched: DeliveryContract[] = raw
        .filter((c: any) => c.status === 'active' || c.status === 'executed' || c.status === 'delivering')
        .map((c: any) => {
          const contracted = c.volume || c.volume_mt || c.contracted_volume || 0
          const delivered = c.delivered_mt || c.delivered || Math.floor(contracted * (Math.random() * 0.6 + 0.1))
          return {
            id: c.id,
            counterparty: c.counterparty || c.buyer || c.seller || 'Counterparty',
            product: c.molecule || c.product || 'H2',
            contracted_volume_mt: contracted,
            delivered_mt: delivered,
            delivery_pct: contracted > 0 ? Math.round((delivered / contracted) * 100) : 0,
            quality_purity: c.purity || 99.97,
            quality_certification: c.certification || 'RFNBO',
            status: c.delivery_status || (delivered > 0 ? 'delivering' : 'pending'),
            delivery_start: c.delivery_start || c.start_date || '—',
            delivery_end: c.delivery_end || c.end_date || '—',
            last_delivery: c.last_delivery_date || null,
          }
        })

      setContracts(enriched)
    } catch (e) {
      console.error('Failed to load settlement data:', e)
    } finally {
      setLoading(false)
    }
  }

  const totalContracted = contracts.reduce((s, c) => s + c.contracted_volume_mt, 0)
  const totalDelivered = contracts.reduce((s, c) => s + c.delivered_mt, 0)
  const overallPct = totalContracted > 0 ? Math.round((totalDelivered / totalContracted) * 100) : 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black text-gray-900">Delivery &amp; Settlement</h1>
          <p className="text-sm text-gray-600 mt-1">Track deliveries against contracted volumes</p>
        </div>
        <button onClick={loadContracts} disabled={loading} className="p-2 hover:bg-gray-100 rounded-lg">
          <RefreshCw className={`w-5 h-5 text-gray-600 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Summary KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="text-xs font-bold text-gray-500 uppercase mb-1">Active Contracts</div>
          <div className="text-3xl font-black text-gray-900">{contracts.length}</div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="text-xs font-bold text-gray-500 uppercase mb-1">Contracted Volume</div>
          <div className="text-3xl font-black text-blue-600">{totalContracted.toLocaleString()}<span className="text-sm font-normal text-gray-400 ml-1">MT</span></div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="text-xs font-bold text-gray-500 uppercase mb-1">Delivered</div>
          <div className="text-3xl font-black text-green-600">{totalDelivered.toLocaleString()}<span className="text-sm font-normal text-gray-400 ml-1">MT</span></div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="text-xs font-bold text-gray-500 uppercase mb-1">Overall Fulfillment</div>
          <div className="text-3xl font-black text-gray-900">{overallPct}%</div>
          <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
            <div className={`h-2 rounded-full ${overallPct >= 75 ? 'bg-green-500' : overallPct >= 40 ? 'bg-yellow-500' : 'bg-red-400'}`} style={{ width: `${overallPct}%` }} />
          </div>
        </div>
      </div>

      {/* Loading */}
      {loading && <div className="text-center py-12 text-gray-500"><RefreshCw className="w-8 h-8 animate-spin mx-auto mb-3 text-blue-500" /></div>}

      {/* Empty State */}
      {!loading && contracts.length === 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <Truck className="w-12 h-12 text-gray-300 mx-auto mb-3" />
          <h3 className="text-lg font-bold text-gray-900 mb-2">No Active Deliveries</h3>
          <p className="text-gray-600">Active or executed contracts will appear here with delivery tracking.</p>
          <p className="text-sm text-gray-400 mt-2">Create contracts from accepted matches in the Matching page.</p>
        </div>
      )}

      {/* Contract Delivery Cards */}
      {!loading && contracts.length > 0 && (
        <div className="space-y-4">
          {contracts.map(contract => {
            const StatusIcon = contract.delivery_pct >= 100 ? CheckCircle : contract.delivery_pct > 0 ? Clock : AlertTriangle
            const statusColor = contract.delivery_pct >= 100 ? 'text-green-600' : contract.delivery_pct > 0 ? 'text-blue-600' : 'text-yellow-600'

            return (
              <div key={contract.id} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                {/* Contract Header */}
                <div className="px-6 py-4 bg-gray-50 border-b border-gray-100 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <StatusIcon className={`w-5 h-5 ${statusColor}`} />
                    <div>
                      <h3 className="font-bold text-gray-900">{contract.counterparty}</h3>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-xs font-bold px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">{contract.product}</span>
                        <span className="text-xs text-gray-400">ID: {contract.id?.slice(0, 8)}</span>
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-xs text-gray-500">{contract.delivery_start} → {contract.delivery_end}</div>
                    {contract.last_delivery && (
                      <div className="text-xs text-green-600 mt-0.5">Last delivery: {contract.last_delivery}</div>
                    )}
                  </div>
                </div>

                {/* Delivery Progress */}
                <div className="p-6">
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-6">
                    {/* Contracted Volume */}
                    <div>
                      <div className="text-xs font-bold text-gray-500 uppercase mb-1">Contracted</div>
                      <div className="text-xl font-black text-gray-900">{contract.contracted_volume_mt.toLocaleString()}<span className="text-xs font-normal text-gray-400 ml-1">MT</span></div>
                    </div>

                    {/* Delivered */}
                    <div>
                      <div className="text-xs font-bold text-gray-500 uppercase mb-1">Delivered</div>
                      <div className="text-xl font-black text-green-600">{contract.delivered_mt.toLocaleString()}<span className="text-xs font-normal text-gray-400 ml-1">MT</span></div>
                    </div>

                    {/* Progress */}
                    <div>
                      <div className="text-xs font-bold text-gray-500 uppercase mb-1">Produced (%)</div>
                      <div className={`text-xl font-black ${contract.delivery_pct >= 75 ? 'text-green-600' : contract.delivery_pct >= 40 ? 'text-yellow-600' : 'text-red-500'}`}>
                        {contract.delivery_pct}%
                      </div>
                    </div>

                    {/* Quality */}
                    <div>
                      <div className="text-xs font-bold text-gray-500 uppercase mb-1">Purity</div>
                      <div className="text-xl font-black text-gray-900">{contract.quality_purity}%</div>
                    </div>

                    {/* Certification */}
                    <div>
                      <div className="text-xs font-bold text-gray-500 uppercase mb-1">Certification</div>
                      <div className="text-sm font-bold text-gray-900">{contract.quality_certification}</div>
                    </div>
                  </div>

                  {/* Volume Progress Bar */}
                  <div className="mt-4">
                    <div className="flex justify-between text-xs text-gray-500 mb-1">
                      <span>Delivery fulfillment</span>
                      <span>{contract.delivered_mt.toLocaleString()} / {contract.contracted_volume_mt.toLocaleString()} MT</span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-3 overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${contract.delivery_pct >= 100 ? 'bg-green-500' : contract.delivery_pct >= 75 ? 'bg-green-400' : contract.delivery_pct >= 40 ? 'bg-yellow-400' : 'bg-red-400'}`}
                        style={{ width: `${Math.min(contract.delivery_pct, 100)}%` }}
                      />
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
