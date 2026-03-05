import { useState, useEffect } from 'react'
import { Coins, Plus, RefreshCw, ArrowRight, CheckCircle2, AlertCircle } from 'lucide-react'
import { capacitiesAPI, tokensAPI } from '@/lib/api'

interface Capacity {
  id: string
  project_name: string
  molecule: string
  capacity_mtpd: number
  location: string
}

interface Token {
  id: string
  capacity_id: string
  project_name: string
  molecule: string
  tokenised_mtpd: number
  delivery_start: string
  delivery_end: string
  compliance_certifications: string[]
  created_at: string
}

interface CapacityWithTokens extends Capacity {
  total_tokenised: number
  available: number
  tokens: Token[]
}

export function TokenisationPage() {
  const [capacitiesWithTokens, setCapacitiesWithTokens] = useState<CapacityWithTokens[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [selectedCapacity, setSelectedCapacity] = useState<Capacity | null>(null)
  const [formData, setFormData] = useState({
    tokenised_mtpd: '',
    delivery_start: '',
    delivery_end: '',
    compliance_certifications: [] as string[],
  })

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [capResponse, tokenResponse] = await Promise.all([
        capacitiesAPI.list(),
        tokensAPI.list(),
      ])

      const capacities = capResponse.capacities || []
      const tokens = tokenResponse.tokens || []

      // Calculate tokenised amount per capacity
      const capacitiesMap = new Map<string, CapacityWithTokens>()

      capacities.forEach((cap: Capacity) => {
        capacitiesMap.set(cap.id, {
          ...cap,
          total_tokenised: 0,
          available: cap.capacity_mtpd,
          tokens: [],
        })
      })

      tokens.forEach((token: Token) => {
        const cap = capacitiesMap.get(token.capacity_id)
        if (cap) {
          cap.total_tokenised += token.tokenised_mtpd
          cap.available = cap.capacity_mtpd - cap.total_tokenised
          cap.tokens.push(token)
        }
      })

      setCapacitiesWithTokens(Array.from(capacitiesMap.values()))
    } catch (error) {
      console.error('Failed to load data:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleTokenise = (capacity: Capacity) => {
    setSelectedCapacity(capacity)
    setShowForm(true)
    setFormData({
      tokenised_mtpd: '',
      delivery_start: '',
      delivery_end: '',
      compliance_certifications: [],
    })
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedCapacity) return

    try {
      await tokensAPI.create({
        capacity_id: selectedCapacity.id,
        tokenised_mtpd: parseFloat(formData.tokenised_mtpd),
        delivery_start: formData.delivery_start,
        delivery_end: formData.delivery_end,
        compliance_certifications: formData.compliance_certifications,
      })

      setShowForm(false)
      setSelectedCapacity(null)
      loadData()
    } catch (error: any) {
      alert(error.message || 'Failed to create token')
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

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black text-gray-900">Tokenisation</h1>
          <p className="text-sm text-gray-500 mt-1">
            Convert production capacity into tradeable digital tokens
          </p>
        </div>
        <button
          onClick={loadData}
          className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Empty State */}
      {capacitiesWithTokens.length === 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <Coins className="w-12 h-12 text-gray-400 mx-auto mb-4" />
          <p className="text-gray-500 mb-4">No capacities available. Create a capacity first!</p>
          <button
            onClick={() => window.location.href = '/capacity'}
            className="px-6 py-3 bg-brand text-white rounded-lg hover:bg-brand-dark font-semibold"
          >
            Create Capacity
          </button>
        </div>
      )}

      {/* Capacities List */}
      {capacitiesWithTokens.map((capacity) => (
        <div key={capacity.id} className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h3 className="text-lg font-bold text-gray-900">{capacity.project_name}</h3>
              <div className="flex items-center gap-3 mt-2">
                <span className="px-3 py-1 bg-brand/10 text-brand text-xs font-bold rounded-full">
                  {capacity.molecule}
                </span>
                <span className="text-sm text-gray-500">{capacity.location}</span>
              </div>
            </div>
            <button
              onClick={() => handleTokenise(capacity)}
              disabled={capacity.available <= 0}
              className="flex items-center gap-2 px-4 py-2 bg-brand text-white rounded-lg hover:bg-brand-dark disabled:bg-gray-300 disabled:cursor-not-allowed font-semibold"
            >
              <Plus className="w-4 h-4" />
              Tokenise
            </button>
          </div>

          {/* Capacity Bar */}
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-gray-600">Capacity Utilization</span>
              <span className="font-bold text-gray-900">
                {capacity.total_tokenised.toFixed(1)} / {capacity.capacity_mtpd.toFixed(1)} MTPD
              </span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-3">
              <div
                className={`h-3 rounded-full ${
                  capacity.available > 0 ? 'bg-emerald-500' : 'bg-yellow-500'
                }`}
                style={{ width: `${(capacity.total_tokenised / capacity.capacity_mtpd) * 100}%` }}
              />
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-gray-500">
                Available: <span className="font-semibold text-gray-900">{capacity.available.toFixed(1)} MTPD</span>
              </span>
              <span className="text-gray-500">
                {((capacity.total_tokenised / capacity.capacity_mtpd) * 100).toFixed(0)}% tokenised
              </span>
            </div>
          </div>

          {/* Tokens List */}
          {capacity.tokens.length > 0 && (
            <div className="mt-4 pt-4 border-t border-gray-200">
              <h4 className="text-sm font-semibold text-gray-700 mb-3">Tokens ({capacity.tokens.length})</h4>
              <div className="space-y-2">
                {capacity.tokens.map((token) => (
                  <div key={token.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                    <div className="flex items-center gap-3">
                      <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                      <div>
                        <div className="text-sm font-semibold text-gray-900">
                          {token.tokenised_mtpd} MTPD
                        </div>
                        <div className="text-xs text-gray-500">
                          {token.delivery_start} → {token.delivery_end}
                        </div>
                      </div>
                    </div>
                    {token.compliance_certifications && token.compliance_certifications.length > 0 && (
                      <div className="flex gap-1">
                        {token.compliance_certifications.map((cert, idx) => (
                          <span key={idx} className="px-2 py-1 bg-blue-100 text-blue-700 text-xs font-medium rounded">
                            {cert}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ))}

      {/* Tokenisation Form Modal */}
      {showForm && selectedCapacity && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-bold text-gray-900">Tokenise Capacity</h2>
              <button
                onClick={() => setShowForm(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                ✕
              </button>
            </div>

            <div className="mb-6 p-4 bg-blue-50 rounded-lg">
              <div className="text-sm font-semibold text-blue-900">{selectedCapacity.project_name}</div>
              <div className="text-xs text-blue-700 mt-1">
                Available: {
                  (capacitiesWithTokens.find(c => c.id === selectedCapacity.id)?.available || 0).toFixed(1)
                } MTPD
              </div>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Volume to Tokenise (MTPD)
                </label>
                <input
                  type="number"
                  step="0.1"
                  required
                  value={formData.tokenised_mtpd}
                  onChange={(e) => setFormData({ ...formData, tokenised_mtpd: e.target.value })}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand focus:border-transparent"
                  placeholder="e.g., 25.5"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Delivery Start
                  </label>
                  <input
                    type="date"
                    required
                    value={formData.delivery_start}
                    onChange={(e) => setFormData({ ...formData, delivery_start: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand focus:border-transparent"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Delivery End
                  </label>
                  <input
                    type="date"
                    required
                    value={formData.delivery_end}
                    onChange={(e) => setFormData({ ...formData, delivery_end: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand focus:border-transparent"
                  />
                </div>
              </div>

              <div className="flex gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setShowForm(false)}
                  className="flex-1 px-6 py-3 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="flex-1 px-6 py-3 bg-brand text-white rounded-lg hover:bg-brand-dark font-semibold"
                >
                  Create Token
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
