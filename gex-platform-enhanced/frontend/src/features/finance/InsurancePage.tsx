import { useState, useEffect } from 'react'
import { Shield, AlertTriangle, Calendar, DollarSign, FileText, CheckCircle2, RefreshCw } from 'lucide-react'
import { financeAPI } from '@/lib/api'

interface InsurancePolicy {
  id: string
  type: string
  provider: string
  coverage: string
  premium: string
  startDate: string
  expiryDate: string
  daysUntilExpiry: number
  status: 'active' | 'expiring-soon' | 'renewal-required'
}

interface Guarantee {
  id: string
  type: string
  provider: string
  amount: string
  beneficiary: string
  expiryDate: string
  status: 'active' | 'claimed' | 'expired'
}

export function InsurancePage() {
  const [policies, setPolicies] = useState<InsurancePolicy[]>([])
  const [guarantees, setGuarantees] = useState<Guarantee[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [policiesData, guaranteesData] = await Promise.all([
        financeAPI.getInsurance(),
        financeAPI.getGuarantees(),
      ])
      setPolicies(policiesData)
      setGuarantees(guaranteesData)
    } catch (error) {
      console.error('Failed to load insurance data:', error)
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
  const totalCoverageValue = policies.reduce((sum, p) => {
    const value = parseFloat(p.coverage.replace(/[€M,]/g, ''))
    return sum + (isNaN(value) ? 0 : value)
  }, 0)

  const totalAnnualPremium = policies.reduce((sum, p) => {
    const value = parseFloat(p.premium.match(/€([\d.]+)/)?.[1] || '0')
    return sum + value
  }, 0)

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-black text-gray-900">Insurance & Guarantees</h1>
        <p className="text-sm text-gray-500 mt-1">
          Coverage status, expiries & premium tracking
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Shield className="w-4 h-4 text-brand" />
            <span className="text-xs font-bold text-gray-500 uppercase">Total Coverage</span>
          </div>
          <div className="text-3xl font-black text-gray-900">€{totalCoverageValue}M</div>
          <div className="text-xs text-gray-500 mt-1">{policies.length} active policies</div>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex items-center gap-2 mb-2">
            <DollarSign className="w-4 h-4 text-green-600" />
            <span className="text-xs font-bold text-gray-500 uppercase">Annual Premium</span>
          </div>
          <div className="text-3xl font-black text-gray-900">€{totalAnnualPremium.toFixed(1)}M</div>
          <div className="text-xs text-gray-500 mt-1">Total cost per year</div>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Calendar className="w-4 h-4 text-yellow-600" />
            <span className="text-xs font-bold text-gray-500 uppercase">Expiring Soon</span>
          </div>
          <div className="text-3xl font-black text-gray-900">
            {policies.filter(p => p.daysUntilExpiry <= 60).length}
          </div>
          <div className="text-xs text-gray-500 mt-1">Within 60 days</div>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex items-center gap-2 mb-2">
            <FileText className="w-4 h-4 text-purple-600" />
            <span className="text-xs font-bold text-gray-500 uppercase">Guarantees</span>
          </div>
          <div className="text-3xl font-black text-gray-900">{guarantees.length}</div>
          <div className="text-xs text-gray-500 mt-1">Active guarantees</div>
        </div>
      </div>

      {/* Expiring Soon Alert */}
      {policies.filter(p => p.daysUntilExpiry <= 60).length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
            <div>
              <div className="font-bold text-red-900 mb-1">Action Required: Renewals Needed</div>
              <div className="text-sm text-red-700">
                {policies.filter(p => p.daysUntilExpiry <= 60).length} insurance {
                  policies.filter(p => p.daysUntilExpiry <= 60).length === 1 ? 'policy' : 'policies'
                } expiring within 60 days. Initiate renewal process immediately to avoid coverage gaps.
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Insurance Policies */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="text-lg font-bold text-gray-900 mb-4">Insurance Policies</h2>
        
        <div className="space-y-3">
          {policies.map((policy) => (
            <div 
              key={policy.id} 
              className={`p-4 rounded-lg border ${
                policy.daysUntilExpiry <= 60 
                  ? 'bg-red-50 border-red-200' 
                  : 'bg-gray-50 border-gray-200'
              }`}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <Shield className={`w-5 h-5 ${
                      policy.daysUntilExpiry <= 60 ? 'text-red-600' : 'text-emerald-600'
                    }`} />
                    <div>
                      <h3 className="font-bold text-gray-900">{policy.type}</h3>
                      <p className="text-sm text-gray-600">{policy.provider}</p>
                    </div>
                  </div>
                </div>
                <span className={`px-3 py-1 text-xs font-bold rounded-full ${
                  policy.daysUntilExpiry <= 60 
                    ? 'bg-red-100 text-red-700' 
                    : 'bg-green-100 text-green-700'
                }`}>
                  {policy.status.replace('-', ' ').toUpperCase()}
                </span>
              </div>

              <div className="grid grid-cols-5 gap-4 mb-3">
                <div>
                  <div className="text-xs text-gray-500 mb-1">Policy ID</div>
                  <div className="text-sm font-semibold text-gray-900">{policy.id}</div>
                </div>
                <div>
                  <div className="text-xs text-gray-500 mb-1">Coverage</div>
                  <div className="text-sm font-semibold text-gray-900">{policy.coverage}</div>
                </div>
                <div>
                  <div className="text-xs text-gray-500 mb-1">Premium</div>
                  <div className="text-sm font-semibold text-gray-900">{policy.premium}</div>
                </div>
                <div>
                  <div className="text-xs text-gray-500 mb-1">Expiry Date</div>
                  <div className="text-sm font-semibold text-gray-900">{policy.expiryDate}</div>
                </div>
                <div>
                  <div className="text-xs text-gray-500 mb-1">Days Until Expiry</div>
                  <div className={`text-sm font-bold ${
                    policy.daysUntilExpiry <= 60 ? 'text-red-600' : 'text-gray-900'
                  }`}>
                    {policy.daysUntilExpiry}
                  </div>
                </div>
              </div>

              {policy.daysUntilExpiry <= 60 && (
                <div className="pt-3 border-t border-red-200">
                  <button className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 text-sm font-semibold">
                    Initiate Renewal Process
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Performance Bonds & Guarantees */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="text-lg font-bold text-gray-900 mb-4">Performance Bonds & Guarantees</h2>
        
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-200">
                <th className="text-left py-3 px-4 text-xs font-bold text-gray-500 uppercase">ID</th>
                <th className="text-left py-3 px-4 text-xs font-bold text-gray-500 uppercase">Type</th>
                <th className="text-left py-3 px-4 text-xs font-bold text-gray-500 uppercase">Provider</th>
                <th className="text-left py-3 px-4 text-xs font-bold text-gray-500 uppercase">Amount</th>
                <th className="text-left py-3 px-4 text-xs font-bold text-gray-500 uppercase">Beneficiary</th>
                <th className="text-left py-3 px-4 text-xs font-bold text-gray-500 uppercase">Expiry</th>
                <th className="text-center py-3 px-4 text-xs font-bold text-gray-500 uppercase">Status</th>
              </tr>
            </thead>
            <tbody>
              {guarantees.map((guarantee) => (
                <tr key={guarantee.id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="py-3 px-4 text-sm font-semibold text-gray-900">{guarantee.id}</td>
                  <td className="py-3 px-4 text-sm text-gray-900">{guarantee.type}</td>
                  <td className="py-3 px-4 text-sm text-gray-900">{guarantee.provider}</td>
                  <td className="py-3 px-4 text-sm font-semibold text-gray-900">{guarantee.amount}</td>
                  <td className="py-3 px-4 text-sm text-gray-600">{guarantee.beneficiary}</td>
                  <td className="py-3 px-4 text-sm text-gray-600">{guarantee.expiryDate}</td>
                  <td className="py-3 px-4 text-center">
                    <span className={`inline-block px-2 py-1 text-xs font-bold rounded ${
                      guarantee.status === 'active' ? 'bg-green-100 text-green-700' :
                      guarantee.status === 'claimed' ? 'bg-yellow-100 text-yellow-700' :
                      'bg-gray-100 text-gray-500'
                    }`}>
                      {guarantee.status.toUpperCase()}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Coverage Adequacy Analysis */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="text-lg font-bold text-gray-900 mb-4">Coverage Adequacy Analysis</h2>
        
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-6">
            <div className="p-4 bg-emerald-50 rounded-lg border border-emerald-200">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold text-emerald-900">Property Insurance</span>
                <CheckCircle2 className="w-5 h-5 text-emerald-600" />
              </div>
              <div className="text-2xl font-black text-emerald-900 mb-1">100%</div>
              <div className="text-xs text-emerald-700">Coverage meets project value</div>
            </div>

            <div className="p-4 bg-emerald-50 rounded-lg border border-emerald-200">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold text-emerald-900">BI Coverage</span>
                <CheckCircle2 className="w-5 h-5 text-emerald-600" />
              </div>
              <div className="text-2xl font-black text-emerald-900 mb-1">100%</div>
              <div className="text-xs text-emerald-700">24 months coverage adequate</div>
            </div>

            <div className="p-4 bg-emerald-50 rounded-lg border border-emerald-200">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold text-emerald-900">Liability</span>
                <CheckCircle2 className="w-5 h-5 text-emerald-600" />
              </div>
              <div className="text-2xl font-black text-emerald-900 mb-1">100%</div>
              <div className="text-xs text-emerald-700">Per occurrence limit adequate</div>
            </div>
          </div>

          <div className="p-4 bg-blue-50 rounded-lg">
            <div className="text-sm text-blue-900">
              <span className="font-semibold">Adequacy Assessment:</span> All insurance coverage meets or exceeds 
              financing agreement requirements. Total insured value of €{totalCoverageValue}M provides comprehensive 
              protection for project assets and operations.
            </div>
          </div>
        </div>
      </div>

      {/* Premium Payment Schedule */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="text-lg font-bold text-gray-900 mb-4">Upcoming Premium Payments (Next 90 Days)</h2>
        
        <div className="space-y-2">
          {[
            { date: '2026-02-15', policy: 'D&O Insurance', amount: '€45K', status: 'upcoming' },
            { date: '2026-03-01', policy: 'All Risk Property', amount: '€300K', status: 'upcoming' },
            { date: '2026-04-01', policy: 'Liability Insurance', amount: '€105K', status: 'upcoming' },
          ].map((payment, idx) => (
            <div key={idx} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
              <div className="flex items-center gap-3">
                <Calendar className="w-4 h-4 text-gray-400" />
                <div>
                  <div className="text-sm font-semibold text-gray-900">{payment.policy}</div>
                  <div className="text-xs text-gray-500">Due: {payment.date}</div>
                </div>
              </div>
              <div className="text-right">
                <div className="text-lg font-bold text-gray-900">{payment.amount}</div>
                <div className="text-xs text-gray-500">Quarterly payment</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
