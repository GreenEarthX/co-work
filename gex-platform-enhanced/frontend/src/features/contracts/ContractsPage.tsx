import { useState, useEffect } from 'react'
import { RefreshCw, Filter, FileText, ChevronRight } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { contractsAPI } from '@/lib/api'

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-600',
  pending: 'bg-yellow-100 text-yellow-700',
  active: 'bg-green-100 text-green-700',
  executed: 'bg-blue-100 text-blue-700',
  expired: 'bg-red-100 text-red-600',
  terminated: 'bg-red-100 text-red-600',
}

export function ContractsPage() {
  const navigate = useNavigate()
  const [contracts, setContracts] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [filterStatus, setFilterStatus] = useState('all')
  const [filterMolecule, setFilterMolecule] = useState('all')
  const [searchTerm, setSearchTerm] = useState('')

  useEffect(() => { loadContracts() }, [])

  const loadContracts = async () => {
    setLoading(true)
    try {
      const res = await contractsAPI.list()
      setContracts(res.contracts || res.data || (Array.isArray(res) ? res : []))
    } catch (e) {
      console.error('Failed to load contracts:', e)
    } finally {
      setLoading(false)
    }
  }

  const filtered = contracts.filter(c => {
    if (filterStatus !== 'all' && c.status !== filterStatus) return false
    if (filterMolecule !== 'all' && (c.molecule || c.product) !== filterMolecule) return false
    if (searchTerm) {
      const term = searchTerm.toLowerCase()
      const searchable = `${c.counterparty || ''} ${c.buyer || ''} ${c.seller || ''} ${c.project || ''} ${c.id || ''}`.toLowerCase()
      if (!searchable.includes(term)) return false
    }
    return true
  })

  const statuses = [...new Set(contracts.map(c => c.status).filter(Boolean))]
  const molecules = [...new Set(contracts.map(c => c.molecule || c.product).filter(Boolean))]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black text-gray-900">Contracts</h1>
          <p className="text-sm text-gray-600 mt-1">{contracts.length} contract{contracts.length !== 1 ? 's' : ''} in system</p>
        </div>
        <button onClick={loadContracts} disabled={loading} className="p-2 hover:bg-gray-100 rounded-lg">
          <RefreshCw className={`w-5 h-5 text-gray-600 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap bg-white rounded-xl border border-gray-200 p-4">
        <Filter className="w-4 h-4 text-gray-400" />
        <input
          type="text"
          placeholder="Search counterparty, project, ID..."
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
          className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm w-56"
        />
        <select value={filterMolecule} onChange={e => setFilterMolecule(e.target.value)} className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm">
          <option value="all">All Molecules</option>
          {molecules.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)} className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm">
          <option value="all">All Statuses</option>
          {statuses.map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
        </select>
        <span className="ml-auto text-xs text-gray-500">{filtered.length} result{filtered.length !== 1 ? 's' : ''}</span>
      </div>

      {/* Loading */}
      {loading && <div className="text-center py-12 text-gray-500"><RefreshCw className="w-8 h-8 animate-spin mx-auto mb-3 text-blue-500" /></div>}

      {/* Empty */}
      {!loading && filtered.length === 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <FileText className="w-12 h-12 text-gray-300 mx-auto mb-3" />
          <h3 className="text-lg font-bold text-gray-900 mb-2">{contracts.length === 0 ? 'No Contracts Yet' : 'No Matching Contracts'}</h3>
          <p className="text-gray-600">{contracts.length === 0 ? 'Contracts are created when matches are accepted.' : 'Adjust your filters to see results.'}</p>
        </div>
      )}

      {/* Contract Cards */}
      {!loading && filtered.length > 0 && (
        <div className="space-y-3">
          {filtered.map(contract => (
            <div key={contract.id} className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm hover:shadow-md transition-shadow">
              <div className="px-6 py-4 flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
                    <FileText className="w-5 h-5 text-blue-600" />
                  </div>
                  <div>
                    <div className="font-bold text-gray-900">
                      {contract.counterparty || contract.buyer || contract.seller || 'Counterparty'}
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs font-bold px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">{contract.molecule || contract.product || 'H2'}</span>
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded ${STATUS_COLORS[contract.status] || STATUS_COLORS.draft}`}>{contract.status || 'draft'}</span>
                      <span className="text-xs text-gray-400">{contract.id?.slice(0, 8)}</span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-6">
                  <div className="text-right">
                    <div className="text-sm font-bold text-gray-900">{contract.volume || contract.volume_mt || '—'} MT</div>
                    <div className="text-xs text-gray-400">{contract.price ? `€${contract.price}/kg` : ''}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-xs text-gray-500">{contract.delivery_start || contract.start_date || '—'}</div>
                    <div className="text-xs text-gray-400">to {contract.delivery_end || contract.end_date || '—'}</div>
                  </div>
                  <button onClick={() => navigate(`/settlement?contract=${contract.id}`)} className="p-2 hover:bg-gray-100 rounded-lg" title="Go to settlement">
                    <ChevronRight className="w-5 h-5 text-gray-400" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
