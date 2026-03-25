/**
 * CommitmentVerifier — Verify and audit any commitment record.
 * Used by all workspaces. Shows record hash, signature verification, counterparty status.
 * Embeds the CounterpartyAcceptance section for bilateral acts.
 *
 * Backend: GET /api/v1/commitments/{id}/verify
 *          GET /api/v1/commitments/project/{project_id}
 *          POST /api/v1/commitments/{id}/countersign
 */
import { useState, useEffect } from 'react'
import { Shield, CheckCircle, XCircle, Search, Users } from 'lucide-react'
import { commitmentsAPI } from '@/api'

interface Commitment {
  commitment_id: string
  action_type: string
  status: string
  valid: boolean
  record_hash_match: boolean
  initiator_user_id: string
  initiator_timestamp: string
  counterparty_user_id?: string
  approvers: any[]
  algorithm: string
  expected_hash?: string
  stored_hash?: string
}

const STATUS_COLORS: Record<string, string> = {
  SIGNED_BY_INITIATOR: 'bg-amber-100 text-amber-700',
  COUNTERSIGNED: 'bg-green-100 text-green-700',
  DISPUTED: 'bg-red-100 text-red-700',
}

export function CommitmentVerifier({ projectId = 'proj_breizh_saf' }: { projectId?: string }) {
  const [searchId, setSearchId] = useState('')
  const [commitments, setCommitments] = useState<any[]>([])
  const [selected, setSelected] = useState<Commitment | null>(null)
  const [loading, setLoading] = useState(true)
  const [verifying, setVerifying] = useState(false)

  // Countersign form state
  const [csForm, setCsForm] = useState({ user_id: '', company_id: '' })
  const [csLoading, setCsLoading] = useState(false)
  const [csResult, setCsResult] = useState<string | null>(null)

  useEffect(() => {
    commitmentsAPI.listForProject(projectId)
      .then((data) => {
        setCommitments(data.commitments || [])
        setLoading(false)
      })
      .catch(() => {
        setLoading(false)
        // Demo fallback — empty list is fine
      })
  }, [projectId])

  const handleVerify = async (id: string) => {
    setVerifying(true)
    setSelected(null)
    setCsResult(null)
    try {
      const data = await commitmentsAPI.verify(id)
      setSelected(data)
    } catch (e) {
      setSelected(null)
    } finally {
      setVerifying(false)
    }
  }

  const handleCountersign = async () => {
    if (!selected) return
    setCsLoading(true)
    try {
      const result = await commitmentsAPI.countersign(selected.commitment_id, {
        counterparty_user_id: csForm.user_id,
        counterparty_company_id: csForm.company_id,
      })
      setCsResult(result.counterparty_signature || 'Countersigned')
      setSelected({ ...selected, status: 'COUNTERSIGNED', counterparty_user_id: csForm.user_id })
    } catch (e: any) {
      setCsResult(`Error: ${e.message}`)
    } finally {
      setCsLoading(false)
    }
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Shield size={22} className="text-teal-600" />
          Commitment Verifier
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Domain 6 — CSS. Verify record integrity (SHA-256) and signature authenticity.
        </p>
      </div>

      {/* Search by ID */}
      <div className="flex gap-2 mb-6">
        <input
          className="flex-1 border border-gray-200 rounded px-3 py-2 text-sm font-mono"
          placeholder="Enter commitment ID (UUID)…"
          value={searchId}
          onChange={(e) => setSearchId(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && searchId && handleVerify(searchId)}
        />
        <button
          onClick={() => searchId && handleVerify(searchId)}
          disabled={!searchId || verifying}
          className="flex items-center gap-1.5 px-4 py-2 bg-teal-600 text-white text-sm rounded hover:bg-teal-700 disabled:opacity-50"
        >
          <Search size={14} />
          {verifying ? 'Verifying…' : 'Verify'}
        </button>
      </div>

      {/* Verification result */}
      {selected && (
        <div className={`border rounded-lg p-5 mb-6 ${
          selected.valid ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'
        }`}>
          <div className="flex items-center gap-2 mb-4">
            {selected.valid
              ? <CheckCircle size={20} className="text-green-600" />
              : <XCircle size={20} className="text-red-600" />}
            <span className={`font-semibold ${selected.valid ? 'text-green-700' : 'text-red-700'}`}>
              {selected.valid ? 'Integrity verified — record untampered' : 'Integrity check FAILED — record may be tampered'}
            </span>
            <span className={`ml-auto text-xs px-2 py-0.5 rounded font-medium ${STATUS_COLORS[selected.status] || 'bg-gray-100 text-gray-600'}`}>
              {selected.status}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm mb-4">
            <div>
              <span className="text-gray-500">Commitment ID:</span>
              <div className="font-mono text-xs mt-0.5 break-all">{selected.commitment_id}</div>
            </div>
            <div>
              <span className="text-gray-500">Action:</span>
              <div className="font-medium mt-0.5">{selected.action_type}</div>
            </div>
            <div>
              <span className="text-gray-500">Initiator:</span>
              <div className="font-medium mt-0.5">{selected.initiator_user_id}</div>
            </div>
            <div>
              <span className="text-gray-500">Signed at:</span>
              <div className="font-medium mt-0.5">{new Date(selected.initiator_timestamp).toLocaleString()}</div>
            </div>
            {selected.counterparty_user_id && (
              <div>
                <span className="text-gray-500">Counterparty:</span>
                <div className="font-medium mt-0.5 flex items-center gap-1">
                  <Users size={12} />
                  {selected.counterparty_user_id}
                </div>
              </div>
            )}
          </div>

          {/* Hash section */}
          <div className="space-y-2">
            {[
              { label: 'Expected Record Hash', value: selected.expected_hash },
              { label: 'Stored Record Hash', value: selected.stored_hash },
            ].filter((h) => h.value).map(({ label, value }) => (
              <div key={label}>
                <div className="text-xs text-gray-500 mb-1">{label}</div>
                <div className={`text-xs font-mono p-2 rounded break-all ${
                  selected.record_hash_match
                    ? 'bg-green-100 text-green-800'
                    : 'bg-red-100 text-red-800'
                }`}>
                  {value}
                </div>
              </div>
            ))}
          </div>

          <div className="mt-3 text-xs text-gray-500">
            Algorithm: {selected.algorithm}
          </div>

          {/* Countersign section for SIGNED_BY_INITIATOR */}
          {selected.status === 'SIGNED_BY_INITIATOR' && !csResult && (
            <div className="mt-4 pt-4 border-t border-green-200">
              <h4 className="text-sm font-medium text-gray-700 mb-3">Counterparty Acceptance</h4>
              <div className="grid grid-cols-2 gap-3 mb-3">
                <input
                  className="border border-gray-200 rounded px-2 py-1.5 text-sm"
                  placeholder="Counterparty user ID"
                  value={csForm.user_id}
                  onChange={(e) => setCsForm({ ...csForm, user_id: e.target.value })}
                />
                <input
                  className="border border-gray-200 rounded px-2 py-1.5 text-sm"
                  placeholder="Counterparty company ID"
                  value={csForm.company_id}
                  onChange={(e) => setCsForm({ ...csForm, company_id: e.target.value })}
                />
              </div>
              <button
                onClick={handleCountersign}
                disabled={!csForm.user_id || !csForm.company_id || csLoading}
                className="flex items-center gap-1.5 px-4 py-2 bg-teal-600 text-white text-sm rounded hover:bg-teal-700 disabled:opacity-50"
              >
                <Users size={14} />
                {csLoading ? 'Countersigning…' : 'Add Counterparty Signature'}
              </button>
            </div>
          )}
          {csResult && (
            <div className="mt-3 text-xs bg-white border border-green-200 rounded p-2 font-mono break-all text-green-800">
              Countersignature: {csResult}
            </div>
          )}
        </div>
      )}

      {/* Project commitment list */}
      <div>
        <h2 className="text-sm font-semibold text-gray-700 mb-3">
          Project Commitments — {projectId}
        </h2>
        {loading ? (
          <div className="text-sm text-gray-400">Loading…</div>
        ) : commitments.length === 0 ? (
          <div className="text-center py-8 border-2 border-dashed border-gray-200 rounded-lg text-sm text-gray-400">
            No signed commitments yet for this project
          </div>
        ) : (
          <div className="space-y-2">
            {commitments.map((c) => (
              <div
                key={c.commitment_id}
                className="flex items-center gap-3 border rounded p-3 bg-white hover:bg-gray-50 cursor-pointer"
                onClick={() => handleVerify(c.commitment_id)}
              >
                <div className={`w-2 h-2 rounded-full shrink-0 ${
                  c.status === 'COUNTERSIGNED' ? 'bg-green-500'
                  : c.status === 'DISPUTED' ? 'bg-red-500'
                  : 'bg-amber-400'
                }`} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-gray-800">
                    {c.action_type?.replace(/_/g, ' ')}
                  </div>
                  <div className="text-xs text-gray-500 font-mono truncate">
                    {c.commitment_id}
                  </div>
                </div>
                <div className={`text-xs px-2 py-0.5 rounded shrink-0 ${STATUS_COLORS[c.status] || 'bg-gray-100 text-gray-600'}`}>
                  {c.status}
                </div>
                <div className="text-xs text-gray-400 shrink-0">
                  {new Date(c.created_at || c.initiator_timestamp).toLocaleDateString()}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="mt-6 text-xs text-gray-400 border-t pt-4">
        Domain 6 — CSS · eIDAS 910/2014 ·
        SHA-256 record integrity check · Append-only DB · No deletion permitted
      </div>
    </div>
  )
}
