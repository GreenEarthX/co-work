// Screen: Barrier management screen (/ciso-barriers)
/**
 * BarrierManagement — CISO view for Domain 3: Information Barriers.
 * Shows configured Chinese Walls / HARD/SOFT barriers between desks.
 * Allows creating new barriers.
 *
 * Backend: GET /api/v1/ciso/barriers
 *          POST /api/v1/ciso/barriers
 */
import { useState, useEffect } from 'react'
import { Shield, AlertTriangle, Plus, ChevronDown, ChevronUp } from 'lucide-react'
import { cisoSecurityAPI } from '@/api'

interface Barrier {
  id: string
  company_id: string
  side_a: string
  side_b: string
  barrier_type: 'HARD' | 'SOFT' | 'CHINESE_WALL'
  applies_to_data: string[]
  description?: string
  active: boolean
  created_at: string
  recent_violations?: any[]
}

const TYPE_COLORS = {
  HARD: 'bg-red-100 text-red-700',
  SOFT: 'bg-yellow-100 text-yellow-700',
  CHINESE_WALL: 'bg-blue-100 text-blue-700',
}

const DATA_CATEGORY_LABELS: Record<string, string> = {
  PERSONAL: 'Personal Data',
  CONTRACT: 'Contracts',
  FINANCIAL_MODEL: 'Financial Models',
  CERTIFICATION: 'Certifications',
  COMMS_METADATA: 'Comms Metadata',
  PLANT_DATA: 'Plant Telemetry',
  AUDIT_LOG: 'Audit Logs',
}

export function BarrierManagement() {
  const [barriers, setBarriers] = useState<Barrier[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({
    side_a: '',
    side_b: '',
    barrier_type: 'HARD',
    applies_to_data: [] as string[],
    description: '',
  })

  useEffect(() => {
    cisoSecurityAPI.listBarriers()
      .then((data) => {
        setBarriers(data.barriers || [])
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const handleCreate = async () => {
    try {
      const result = await cisoSecurityAPI.createBarrier(form)
      if (result.barrier) {
        setBarriers((prev) => [...prev, result.barrier])
        setShowForm(false)
        setForm({ side_a: '', side_b: '', barrier_type: 'HARD', applies_to_data: [], description: '' })
      }
    } catch (e) {
      // ignore in demo
    }
  }

  const toggleCategory = (cat: string) => {
    setForm((prev) => ({
      ...prev,
      applies_to_data: prev.applies_to_data.includes(cat)
        ? prev.applies_to_data.filter((c) => c !== cat)
        : [...prev.applies_to_data, cat],
    }))
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Shield size={22} className="text-blue-600" />
            Information Barriers
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Domain 3 — Chinese Walls and desk segregation rules.
            Prevents information flow across regulated boundaries within your organisation.
          </p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-1.5 px-3 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700"
        >
          <Plus size={14} />
          New Barrier
        </button>
      </div>

      {/* Create form */}
      {showForm && (
        <div className="border border-blue-200 bg-blue-50 rounded-lg p-4 mb-6 space-y-3">
          <h3 className="text-sm font-semibold text-blue-800">New Information Barrier</h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-600 block mb-1">Side A (desk / role)</label>
              <input
                className="w-full border border-gray-200 rounded px-2 py-1.5 text-sm"
                placeholder="e.g. TRADING"
                value={form.side_a}
                onChange={(e) => setForm({ ...form, side_a: e.target.value })}
              />
            </div>
            <div>
              <label className="text-xs text-gray-600 block mb-1">Side B (desk / role)</label>
              <input
                className="w-full border border-gray-200 rounded px-2 py-1.5 text-sm"
                placeholder="e.g. ORIGINATION"
                value={form.side_b}
                onChange={(e) => setForm({ ...form, side_b: e.target.value })}
              />
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-600 block mb-1">Barrier Type</label>
            <select
              className="border border-gray-200 rounded px-2 py-1.5 text-sm"
              value={form.barrier_type}
              onChange={(e) => setForm({ ...form, barrier_type: e.target.value })}
            >
              <option value="HARD">HARD — Block access entirely</option>
              <option value="SOFT">SOFT — Log and warn</option>
              <option value="CHINESE_WALL">CHINESE_WALL — Log only</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-600 block mb-1">Data Categories</label>
            <div className="flex flex-wrap gap-2">
              {Object.entries(DATA_CATEGORY_LABELS).map(([cat, label]) => (
                <button
                  key={cat}
                  onClick={() => toggleCategory(cat)}
                  className={`text-xs px-2 py-1 rounded border transition-colors ${
                    form.applies_to_data.includes(cat)
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white text-gray-600 border-gray-200 hover:border-blue-400'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <input
            className="w-full border border-gray-200 rounded px-2 py-1.5 text-sm"
            placeholder="Description (optional)"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <div className="flex gap-2">
            <button
              onClick={handleCreate}
              className="px-4 py-1.5 bg-blue-600 text-white text-sm rounded hover:bg-blue-700"
            >
              Create
            </button>
            <button
              onClick={() => setShowForm(false)}
              className="px-4 py-1.5 text-gray-600 text-sm rounded border border-gray-200 hover:bg-gray-50"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-center py-12 text-gray-400">Loading barriers…</div>
      ) : barriers.length === 0 ? (
        <div className="text-center py-12 border-2 border-dashed border-gray-200 rounded-lg">
          <Shield size={32} className="mx-auto text-gray-300 mb-3" />
          <p className="text-gray-400">No information barriers configured</p>
        </div>
      ) : (
        <div className="space-y-3">
          {barriers.map((barrier) => (
            <div key={barrier.id} className="border rounded-lg bg-white">
              <div
                className="flex items-center gap-4 p-4 cursor-pointer"
                onClick={() => setExpanded(expanded === barrier.id ? null : barrier.id)}
              >
                <div className={`shrink-0 w-1.5 h-1.5 rounded-full ${barrier.active ? 'bg-green-500' : 'bg-gray-300'}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-sm text-gray-900">
                      {barrier.side_a}
                    </span>
                    <span className="text-gray-400 text-sm">↔</span>
                    <span className="font-medium text-sm text-gray-900">
                      {barrier.side_b}
                    </span>
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${TYPE_COLORS[barrier.barrier_type]}`}>
                      {barrier.barrier_type}
                    </span>
                    <span className="text-xs text-gray-400">
                      {barrier.id}
                    </span>
                  </div>
                  {barrier.description && (
                    <p className="text-xs text-gray-500 mt-0.5">{barrier.description}</p>
                  )}
                </div>
                {barrier.recent_violations && barrier.recent_violations.length > 0 && (
                  <div className="flex items-center gap-1 text-xs text-red-600 shrink-0">
                    <AlertTriangle size={12} />
                    {barrier.recent_violations.length} violation{barrier.recent_violations.length > 1 ? 's' : ''}
                  </div>
                )}
                <div className="text-gray-400 shrink-0">
                  {expanded === barrier.id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                </div>
              </div>

              {expanded === barrier.id && (
                <div className="border-t border-gray-100 p-4 space-y-3">
                  <div>
                    <div className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
                      Data Categories Covered
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {barrier.applies_to_data.length > 0 ? (
                        barrier.applies_to_data.map((cat) => (
                          <span key={cat} className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded">
                            {DATA_CATEGORY_LABELS[cat] || cat}
                          </span>
                        ))
                      ) : (
                        <span className="text-xs text-gray-400 italic">All data categories</span>
                      )}
                    </div>
                  </div>
                  {barrier.recent_violations && barrier.recent_violations.length > 0 && (
                    <div>
                      <div className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
                        Recent Violations
                      </div>
                      <div className="space-y-1">
                        {barrier.recent_violations.map((v: any) => (
                          <div key={v.id} className="text-xs bg-red-50 border border-red-100 rounded p-2">
                            <span className="text-red-700 font-medium">{v.user_name || v.user_id}</span>
                            {' attempted access to '}<code>{v.resource_id}</code>
                            {' — '}<span className="text-red-600">{v.outcome}</span>
                            <span className="text-gray-400 ml-2">{new Date(v.attempted_at).toLocaleString()}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className="text-xs text-gray-400">
                    Created: {new Date(barrier.created_at).toLocaleString()}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="mt-6 text-xs text-gray-400 border-t pt-4">
        Domain 3 — Information Barriers · ISO 27001 A.9.4 ·
        HARD barriers block at ABAC evaluation; violations are logged to the immutable audit trail
      </div>
    </div>
  )
}
