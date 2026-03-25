/**
 * ResidencyPolicies — CISO view for Domain 5: Data Residency Policy Layer.
 * Shows per-data-category jurisdiction constraints and recent residency checks.
 *
 * Backend: GET /api/v1/ciso/residency/policies
 *          POST /api/v1/ciso/residency/policies
 *          GET /api/v1/ciso/residency/audit
 */
import { useState, useEffect } from 'react'
import { Globe, Lock, CheckCircle, XCircle, AlertCircle } from 'lucide-react'
import { cisoSecurityAPI } from '@/api'

interface ResidencyPolicy {
  id: string
  data_category: string
  required_jurisdiction: string
  storage_zone: string
  note?: string
  active: boolean
}

interface AuditEntry {
  id: string
  data_category: string
  requested_zone: string
  outcome: 'ALLOWED' | 'BLOCKED' | 'NEEDS_CONSENT'
  required_jurisdiction?: string
  reason?: string
  checked_at: string
}

const JURISDICTION_FLAGS: Record<string, string> = {
  EU: '🇪🇺',
  CH: '🇨🇭',
  GB: '🇬🇧',
  US: '🇺🇸',
}

const CATEGORY_LABELS: Record<string, string> = {
  PERSONAL: 'Personal Data',
  CONTRACT: 'Contracts',
  FINANCIAL_MODEL: 'Financial Models',
  CERTIFICATION: 'Certifications',
  COMMS_METADATA: 'Comms Metadata',
  PLANT_DATA: 'Plant Telemetry',
  AUDIT_LOG: 'Audit Logs',
}

const ALWAYS_EU = new Set(['AUDIT_LOG', 'COMMS_METADATA'])

export function ResidencyPolicies() {
  const [policies, setPolicies] = useState<ResidencyPolicy[]>([])
  const [auditData, setAuditData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'policies' | 'audit'>('policies')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState({ required_jurisdiction: '', storage_zone: '' })
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      cisoSecurityAPI.listResidencyPolicies(),
      cisoSecurityAPI.getResidencyAudit(),
    ]).then(([pData, aData]) => {
      setPolicies(pData.policies || [])
      setAuditData(aData)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const handleSavePolicy = async (policy: ResidencyPolicy) => {
    setSaveError(null)
    try {
      await cisoSecurityAPI.upsertResidencyPolicy({
        data_category: policy.data_category,
        required_jurisdiction: editForm.required_jurisdiction || policy.required_jurisdiction,
        storage_zone: editForm.storage_zone || policy.storage_zone,
      })
      setPolicies((prev) =>
        prev.map((p) =>
          p.id === policy.id
            ? {
                ...p,
                required_jurisdiction: editForm.required_jurisdiction || p.required_jurisdiction,
                storage_zone: editForm.storage_zone || p.storage_zone,
              }
            : p
        )
      )
      setEditingId(null)
    } catch (e: any) {
      setSaveError(e.message || 'Failed to update policy')
    }
  }

  if (loading) {
    return <div className="p-6 text-gray-400">Loading residency policies…</div>
  }

  const auditEntries: AuditEntry[] = auditData?.recent_checks || []

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Globe size={22} className="text-emerald-600" />
          Data Residency Policies
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Domain 5 — DRPL. Governs where each data category is stored.
          ALWAYS_EU categories cannot be changed (GDPR Art. 44 / GEX Security Arch §5.3).
        </p>
      </div>

      {/* Stats row */}
      {auditData && (
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="border rounded-lg p-4 bg-white">
            <div className="text-2xl font-bold text-green-600">{auditData.allowed_count_24h ?? 0}</div>
            <div className="text-xs text-gray-500">Allowed checks (24h)</div>
          </div>
          <div className="border rounded-lg p-4 bg-white">
            <div className="text-2xl font-bold text-red-600">{auditData.blocked_count_24h ?? 0}</div>
            <div className="text-xs text-gray-500">Blocked (HTTP 451) (24h)</div>
          </div>
          <div className="border rounded-lg p-4 bg-white">
            <div className="text-2xl font-bold text-blue-600">{policies.length}</div>
            <div className="text-xs text-gray-500">Active policies</div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 mb-4 border-b">
        {(['policies', 'audit'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              activeTab === tab
                ? 'border-emerald-600 text-emerald-700'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab === 'policies' ? 'Policies' : 'Audit Log'}
          </button>
        ))}
      </div>

      {saveError && (
        <div className="flex items-center gap-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded p-3 mb-4">
          <AlertCircle size={16} />
          {saveError}
        </div>
      )}

      {activeTab === 'policies' ? (
        <div className="space-y-2">
          {policies.map((policy) => {
            const locked = ALWAYS_EU.has(policy.data_category)
            const isEditing = editingId === policy.id

            return (
              <div key={policy.id} className={`border rounded-lg p-4 bg-white ${locked ? 'opacity-80' : ''}`}>
                <div className="flex items-center gap-3">
                  <div className="shrink-0 text-lg">
                    {JURISDICTION_FLAGS[policy.required_jurisdiction] || '🌐'}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-sm text-gray-900">
                        {CATEGORY_LABELS[policy.data_category] || policy.data_category}
                      </span>
                      {locked && (
                        <span className="flex items-center gap-0.5 text-xs text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">
                          <Lock size={10} />
                          ALWAYS_EU
                        </span>
                      )}
                    </div>
                    {isEditing ? (
                      <div className="mt-2 flex gap-2 items-center flex-wrap">
                        <select
                          className="border border-gray-200 rounded px-2 py-1 text-sm"
                          value={editForm.required_jurisdiction}
                          onChange={(e) => setEditForm({ ...editForm, required_jurisdiction: e.target.value })}
                        >
                          <option value="EU">EU (GDPR)</option>
                          <option value="CH">CH (FADP 2023)</option>
                          <option value="GB">GB (UK GDPR)</option>
                          <option value="US">US (SOC 2)</option>
                        </select>
                        <input
                          className="border border-gray-200 rounded px-2 py-1 text-sm w-36"
                          placeholder="zone (e.g. eu-west-1)"
                          value={editForm.storage_zone}
                          onChange={(e) => setEditForm({ ...editForm, storage_zone: e.target.value })}
                        />
                        <button
                          onClick={() => handleSavePolicy(policy)}
                          className="text-xs px-3 py-1 bg-emerald-600 text-white rounded hover:bg-emerald-700"
                        >
                          Save
                        </button>
                        <button
                          onClick={() => setEditingId(null)}
                          className="text-xs px-3 py-1 border border-gray-200 text-gray-600 rounded hover:bg-gray-50"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <div className="text-xs text-gray-500 mt-0.5">
                        Jurisdiction: <strong>{policy.required_jurisdiction}</strong> ·
                        Zone: <code>{policy.storage_zone}</code>
                        {policy.note && ` · ${policy.note}`}
                      </div>
                    )}
                  </div>
                  {!locked && !isEditing && (
                    <button
                      onClick={() => {
                        setEditingId(policy.id)
                        setEditForm({
                          required_jurisdiction: policy.required_jurisdiction,
                          storage_zone: policy.storage_zone,
                        })
                        setSaveError(null)
                      }}
                      className="text-xs text-gray-400 hover:text-gray-600 shrink-0"
                    >
                      Edit
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <div className="space-y-2">
          {auditEntries.length === 0 ? (
            <div className="text-center py-8 text-gray-400 text-sm">No audit entries yet</div>
          ) : (
            auditEntries.map((entry) => (
              <div key={entry.id} className="flex items-center gap-3 border rounded p-3 bg-white text-sm">
                <div className="shrink-0">
                  {entry.outcome === 'ALLOWED' ? (
                    <CheckCircle size={16} className="text-green-500" />
                  ) : entry.outcome === 'BLOCKED' ? (
                    <XCircle size={16} className="text-red-500" />
                  ) : (
                    <AlertCircle size={16} className="text-amber-500" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <span className="font-medium text-gray-800">
                    {CATEGORY_LABELS[entry.data_category] || entry.data_category}
                  </span>
                  <span className="text-gray-400 mx-1.5">→</span>
                  <code className="text-xs">{entry.requested_zone}</code>
                  {entry.outcome === 'BLOCKED' && entry.reason && (
                    <div className="text-xs text-red-600 mt-0.5">{entry.reason}</div>
                  )}
                </div>
                <div className="text-xs text-gray-400 shrink-0">
                  {new Date(entry.checked_at).toLocaleString()}
                </div>
                <div className={`text-xs px-2 py-0.5 rounded font-medium shrink-0 ${
                  entry.outcome === 'ALLOWED'
                    ? 'bg-green-100 text-green-700'
                    : entry.outcome === 'BLOCKED'
                    ? 'bg-red-100 text-red-700'
                    : 'bg-amber-100 text-amber-700'
                }`}>
                  {entry.outcome === 'BLOCKED' ? 'HTTP 451' : entry.outcome}
                </div>
              </div>
            ))
          )}
        </div>
      )}

      <div className="mt-6 text-xs text-gray-400 border-t pt-4">
        Domain 5 — DRPL · GDPR Art. 44 / eIDAS 910/2014 ·
        HTTP 451 "Unavailable for Legal Reasons" on blocked zone requests
      </div>
    </div>
  )
}
