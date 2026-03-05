import { useState, useEffect } from 'react'
import { DollarSign, TrendingUp, Calendar, Users, AlertCircle, RefreshCw } from 'lucide-react'
import { financeAPI } from '@/lib/api'

interface Contract {
  id: string
  counterparty: string
  molecule: string
  volume_mtpd: number
  price_eur_kg: number
  pricingBasis: string
  startDate: string
  endDate: string
  tenor_years: number
  status: 'active' | 'negotiating' | 'expired'
  creditRating: string
}

export function RevenueOfftakePage() {
  const [contracts, setContracts] = useState<Contract[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const data = await financeAPI.getContracts()
      setContracts(data)
    } catch (error) {
      console.error('Failed to load contracts:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center justify-center h-64">
          <RefreshCw className="w-8 h-8 text-brand animate-spin" />
        </div>
      </div>
    )
  }
  const totalCapacity = 50.0
  const contractedVolume = contracts.filter(c => c.status === 'active').reduce((sum, c) => sum + c.volume_mtpd, 0)
  const coveragePct = (contractedVolume / totalCapacity) * 100

  const weightedAvgPrice = contracts
    .filter(c => c.status === 'active')
    .reduce((sum, c) => sum + (c.price_eur_kg * c.volume_mtpd), 0) / contractedVolume

  const avgTenor = contracts
    .filter(c => c.status === 'active')
    .reduce((sum, c) => sum + c.tenor_years, 0) / contracts.filter(c => c.status === 'active').length

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-black text-gray-900">Revenue & Offtake</h1>
        <p className="text-sm text-gray-500 mt-1">
          Contract stack, coverage analysis & counterparty exposure
        </p>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex items-center gap-2 mb-2">
            <DollarSign className="w-4 h-4 text-brand" />
            <span className="text-xs font-bold text-gray-500 uppercase">Coverage</span>
          </div>
          <div className="text-3xl font-black text-gray-900">{coveragePct.toFixed(0)}%</div>
          <div className="text-xs text-gray-500 mt-1">{contractedVolume} / {totalCapacity} MTPD</div>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-4 h-4 text-green-600" />
            <span className="text-xs font-bold text-gray-500 uppercase">Avg Price</span>
          </div>
          <div className="text-3xl font-black text-gray-900">€{weightedAvgPrice.toFixed(2)}</div>
          <div className="text-xs text-gray-500 mt-1">per kg (weighted)</div>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Calendar className="w-4 h-4 text-blue-600" />
            <span className="text-xs font-bold text-gray-500 uppercase">Avg Tenor</span>
          </div>
          <div className="text-3xl font-black text-gray-900">{avgTenor.toFixed(1)}</div>
          <div className="text-xs text-gray-500 mt-1">years</div>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Users className="w-4 h-4 text-purple-600" />
            <span className="text-xs font-bold text-gray-500 uppercase">Offtakers</span>
          </div>
          <div className="text-3xl font-black text-gray-900">{contracts.filter(c => c.status === 'active').length}</div>
          <div className="text-xs text-gray-500 mt-1">active contracts</div>
        </div>
      </div>

      {/* Contract Stack Visualization */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="text-lg font-bold text-gray-900 mb-4">Contract Stack</h2>
        
        <div className="space-y-3">
          {contracts.filter(c => c.status === 'active').map((contract) => {
            const widthPct = (contract.volume_mtpd / totalCapacity) * 100
            
            return (
              <div key={contract.id} className="flex items-center gap-3">
                <div className="flex-1">
                  <div 
                    className="bg-green-500 h-16 rounded-lg flex items-center px-4 hover:bg-green-600 transition-colors cursor-pointer"
                    style={{ width: `${widthPct}%`, minWidth: '200px' }}
                  >
                    <div className="text-white">
                      <div className="font-bold">{contract.counterparty}</div>
                      <div className="text-xs opacity-90">
                        {contract.volume_mtpd} MTPD • €{contract.price_eur_kg}/kg • {contract.tenor_years}y
                      </div>
                    </div>
                  </div>
                </div>
                <div className="text-sm text-gray-600 w-32 text-right">
                  {widthPct.toFixed(0)}% capacity
                </div>
              </div>
            )
          })}

          {/* Negotiating */}
          {contracts.filter(c => c.status === 'negotiating').map((contract) => {
            const widthPct = (contract.volume_mtpd / totalCapacity) * 100
            
            return (
              <div key={contract.id} className="flex items-center gap-3">
                <div className="flex-1">
                  <div 
                    className="bg-yellow-300 h-16 rounded-lg flex items-center px-4 border-2 border-yellow-500 border-dashed"
                    style={{ width: `${widthPct}%`, minWidth: '200px' }}
                  >
                    <div className="text-yellow-900">
                      <div className="font-bold">{contract.counterparty}</div>
                      <div className="text-xs">
                        {contract.volume_mtpd} MTPD • €{contract.price_eur_kg}/kg • Negotiating
                      </div>
                    </div>
                  </div>
                </div>
                <div className="text-sm text-gray-600 w-32 text-right">
                  {widthPct.toFixed(0)}% capacity
                </div>
              </div>
            )
          })}

          {/* Uncontracted */}
          {totalCapacity - contractedVolume > 0 && (
            <div className="flex items-center gap-3">
              <div className="flex-1">
                <div 
                  className="bg-gray-200 h-16 rounded-lg flex items-center px-4"
                  style={{ width: `${((totalCapacity - contractedVolume) / totalCapacity) * 100}%`, minWidth: '150px' }}
                >
                  <div className="text-gray-700">
                    <div className="font-bold">Uncontracted</div>
                    <div className="text-xs">
                      {(totalCapacity - contractedVolume).toFixed(1)} MTPD • Merchant exposure
                    </div>
                  </div>
                </div>
              </div>
              <div className="text-sm text-gray-600 w-32 text-right">
                {(((totalCapacity - contractedVolume) / totalCapacity) * 100).toFixed(0)}% capacity
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Contract Details Table */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="text-lg font-bold text-gray-900 mb-4">Contract Details</h2>
        
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-200">
                <th className="text-left py-3 px-4 text-xs font-bold text-gray-500 uppercase">Contract</th>
                <th className="text-left py-3 px-4 text-xs font-bold text-gray-500 uppercase">Counterparty</th>
                <th className="text-right py-3 px-4 text-xs font-bold text-gray-500 uppercase">Volume</th>
                <th className="text-right py-3 px-4 text-xs font-bold text-gray-500 uppercase">Price</th>
                <th className="text-left py-3 px-4 text-xs font-bold text-gray-500 uppercase">Pricing Basis</th>
                <th className="text-left py-3 px-4 text-xs font-bold text-gray-500 uppercase">Period</th>
                <th className="text-center py-3 px-4 text-xs font-bold text-gray-500 uppercase">Rating</th>
                <th className="text-center py-3 px-4 text-xs font-bold text-gray-500 uppercase">Status</th>
              </tr>
            </thead>
            <tbody>
              {contracts.map((contract) => (
                <tr key={contract.id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="py-3 px-4 text-sm font-semibold text-gray-900">{contract.id}</td>
                  <td className="py-3 px-4 text-sm text-gray-900">{contract.counterparty}</td>
                  <td className="py-3 px-4 text-sm text-right font-semibold text-gray-900">
                    {contract.volume_mtpd} MTPD
                  </td>
                  <td className="py-3 px-4 text-sm text-right font-semibold text-gray-900">
                    €{contract.price_eur_kg}
                  </td>
                  <td className="py-3 px-4 text-sm text-gray-600">{contract.pricingBasis}</td>
                  <td className="py-3 px-4 text-sm text-gray-600">
                    {contract.startDate} → {contract.endDate}<br />
                    <span className="text-xs text-gray-500">({contract.tenor_years} years)</span>
                  </td>
                  <td className="py-3 px-4 text-center">
                    <span className={`inline-block px-2 py-1 text-xs font-bold rounded ${
                      contract.creditRating.startsWith('A') ? 'bg-green-100 text-green-700' :
                      contract.creditRating.startsWith('BBB') ? 'bg-yellow-100 text-yellow-700' :
                      'bg-red-100 text-red-700'
                    }`}>
                      {contract.creditRating}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-center">
                    <span className={`inline-block px-2 py-1 text-xs font-bold rounded ${
                      contract.status === 'active' ? 'bg-green-100 text-green-700' :
                      contract.status === 'negotiating' ? 'bg-yellow-100 text-yellow-700' :
                      'bg-gray-100 text-gray-500'
                    }`}>
                      {contract.status.toUpperCase()}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Counterparty Concentration */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="text-lg font-bold text-gray-900 mb-4">Counterparty Concentration Risk</h2>
        
        <div className="space-y-4">
          {contracts
            .filter(c => c.status === 'active')
            .sort((a, b) => b.volume_mtpd - a.volume_mtpd)
            .map((contract, idx) => {
              const concentrationPct = (contract.volume_mtpd / contractedVolume) * 100
              
              return (
                <div key={contract.id}>
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <span className="font-semibold text-gray-900">{contract.counterparty}</span>
                      <span className="text-sm text-gray-500 ml-2">({contract.creditRating})</span>
                    </div>
                    <span className="text-sm font-bold text-gray-900">{concentrationPct.toFixed(1)}%</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div 
                      className={`h-2 rounded-full ${
                        concentrationPct > 40 ? 'bg-red-500' :
                        concentrationPct > 25 ? 'bg-yellow-500' :
                        'bg-green-500'
                      }`}
                      style={{ width: `${concentrationPct}%` }}
                    />
                  </div>
                </div>
              )
            })}
        </div>

        <div className="mt-4 p-4 bg-blue-50 rounded-lg">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-blue-700 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-blue-900">
              <span className="font-semibold">Concentration Assessment:</span> Largest offtaker represents {
                ((Math.max(...contracts.filter(c => c.status === 'active').map(c => c.volume_mtpd)) / contractedVolume) * 100).toFixed(0)
              }% of contracted volume. Recommend diversifying to reduce single-counterparty exposure below 30%.
            </div>
          </div>
        </div>
      </div>

      {/* Revenue Forecast */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="text-lg font-bold text-gray-900 mb-4">Annual Revenue Forecast</h2>
        
        <div className="grid grid-cols-5 gap-4">
          {[2027, 2028, 2029, 2030, 2031].map((year) => {
            const revenue = contractedVolume * 365 * weightedAvgPrice / 1000 // Convert to millions
            
            return (
              <div key={year} className="text-center">
                <div className="text-xs font-bold text-gray-500 mb-2">{year}</div>
                <div className="text-2xl font-black text-gray-900">€{revenue.toFixed(1)}M</div>
                <div className="text-xs text-gray-500 mt-1">annual revenue</div>
              </div>
            )
          })}
        </div>

        <div className="mt-6 p-4 bg-gray-50 rounded-lg">
          <div className="text-sm text-gray-700">
            <span className="font-semibold">Assumptions:</span> Full capacity utilization, fixed pricing (no escalation), 
            no additional contracts beyond current stack.
          </div>
        </div>
      </div>
    </div>
  )
}
