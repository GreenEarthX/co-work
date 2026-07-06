// Screen: Commitment signing screen (/commitment-signing, /finance/commitment-signing)
/**
 * CommitmentSigning — Signing ceremony for binding commercial acts.
 * Used by Trader/Finance to sign commitments AFTER WAE approval quorum.
 * Shows payload hash, record hash, and initiator signature on completion.
 *
 * Backend: POST /api/v1/commitments/sign
 */
import { useState } from 'react'
import { FileSignature, CheckCircle, AlertCircle, Lock } from 'lucide-react'
import { commitmentsAPI } from '@/api'
import { ApprovalBanner } from '@/components/ApprovalBanner'

const ACTION_TYPES = [
  'SAF_FORWARD_SALE',
  'PPA_EXECUTION',
  'FINANCING_DRAWDOWN',
  'INSURANCE_PLACEMENT',
  'EPC_MILESTONE_PAYMENT',
  'CERTIFICATE_APPLICATION',
  'COUNTERPARTY_NDA',
]

interface SignedResult {
  commitment_id: string
  action_type: string
  initiator_signature: string
  payload_hash: string
  record_hash: string
  status: string
  initiator_timestamp: string
}

export function CommitmentSigning() {
  const [form, setForm] = useState({
    action_type: 'SAF_FORWARD_SALE',
    project_id: 'proj_breizh_saf',
    initiator_user_id: 'usr_bp_01',
    initiator_company_id: 'bp_global_energy',
    approval_request_id: '',
    payload: '{\n  "volume_t": 10000,\n  "price_eur_t": 2200,\n  "counterparty": "Air France KLM",\n  "tenor_months": 24\n}',
  })
  const [payloadError, setPayloadError] = useState<string | null>(null)
  const [signing, setSigning] = useState(false)
  const [result, setResult] = useState<SignedResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending] = useState(null)

  const handleSign = async () => {
    setPayloadError(null)
    setError(null)

    let parsedPayload: Record<string, any>
    try {
      parsedPayload = JSON.parse(form.payload)
    } catch {
      setPayloadError('Invalid JSON payload')
      return
    }

    setSigning(true)
    try {
      const res = await commitmentsAPI.sign({
        initiator_user_id: form.initiator_user_id,
        initiator_company_id: form.initiator_company_id,
        action_type: form.action_type,
        project_id: form.project_id,
        payload: parsedPayload,
        approval_request_id: form.approval_request_id || undefined,
      })
      setResult(res)
    } catch (e: any) {
      setError(e.message || 'Signing failed')
    } finally {
      setSigning(false)
    }
  }

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <FileSignature size={22} className="text-indigo-600" />
          Commitment Signing
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Domain 6 — CSS. Create a non-repudiable signed commitment record.
          Must be called after WAE approval quorum is reached.
        </p>
      </div>

      <ApprovalBanner pending={pending} />

      {result ? (
        /* Success: show signed commitment */
        <div className="border border-green-200 bg-green-50 rounded-lg p-6 space-y-4">
          <div className="flex items-center gap-2 text-green-700 font-semibold">
            <CheckCircle size={20} />
            Commitment signed successfully
          </div>
          <div className="space-y-2 text-sm">
            {[
              { label: 'Commitment ID', value: result.commitment_id },
              { label: 'Action Type', value: result.action_type },
              { label: 'Status', value: result.status },
              { label: 'Signed at', value: new Date(result.initiator_timestamp).toLocaleString() },
            ].map(({ label, value }) => (
              <div key={label} className="flex gap-3">
                <span className="text-gray-500 w-36 shrink-0">{label}:</span>
                <span className="font-medium text-gray-900">{value}</span>
              </div>
            ))}
          </div>

          <div className="space-y-2">
            {[
              { label: 'Payload Hash (SHA-256)', value: result.payload_hash },
              { label: 'Record Hash (SHA-256)', value: result.record_hash },
              { label: 'Initiator Signature', value: result.initiator_signature },
            ].map(({ label, value }) => (
              <div key={label}>
                <div className="text-xs text-gray-500 mb-1">{label}</div>
                <div className="bg-white border border-gray-200 rounded p-2 text-xs font-mono text-gray-700 break-all">
                  {value}
                </div>
              </div>
            ))}
          </div>

          <div className="flex items-center gap-2 text-xs text-gray-500 pt-2 border-t border-green-200">
            <Lock size={12} />
            Record is append-only and cannot be deleted.
            eIDAS 910/2014 — legal standing in EU (Tier 4: QTSP-backed RSA/Ed25519).
          </div>

          <button
            onClick={() => setResult(null)}
            className="text-sm text-indigo-600 hover:text-indigo-800 underline"
          >
            Sign another commitment
          </button>
        </div>
      ) : (
        /* Form */
        <div className="border rounded-lg p-6 bg-white space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-gray-600 block mb-1">Action Type</label>
              <select
                className="w-full border border-gray-200 rounded px-2 py-2 text-sm"
                value={form.action_type}
                onChange={(e) => setForm({ ...form, action_type: e.target.value })}
              >
                {ACTION_TYPES.map((at) => (
                  <option key={at} value={at}>{at.replace(/_/g, ' ')}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-600 block mb-1">Project ID</label>
              <input
                className="w-full border border-gray-200 rounded px-2 py-2 text-sm"
                value={form.project_id}
                onChange={(e) => setForm({ ...form, project_id: e.target.value })}
              />
            </div>
            <div>
              <label className="text-xs text-gray-600 block mb-1">Initiator User ID</label>
              <input
                className="w-full border border-gray-200 rounded px-2 py-2 text-sm"
                value={form.initiator_user_id}
                onChange={(e) => setForm({ ...form, initiator_user_id: e.target.value })}
              />
            </div>
            <div>
              <label className="text-xs text-gray-600 block mb-1">Company ID</label>
              <input
                className="w-full border border-gray-200 rounded px-2 py-2 text-sm"
                value={form.initiator_company_id}
                onChange={(e) => setForm({ ...form, initiator_company_id: e.target.value })}
              />
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-600 block mb-1">
              WAE Approval Request ID <span className="text-gray-400">(optional)</span>
            </label>
            <input
              className="w-full border border-gray-200 rounded px-2 py-2 text-sm font-mono"
              placeholder="req-xxxxxxxx-xxxx-xxxx-xxxx"
              value={form.approval_request_id}
              onChange={(e) => setForm({ ...form, approval_request_id: e.target.value })}
            />
          </div>
          <div>
            <label className="text-xs text-gray-600 block mb-1">Payload (JSON)</label>
            <textarea
              className={`w-full border rounded p-3 text-sm font-mono resize-none h-32 ${
                payloadError ? 'border-red-400' : 'border-gray-200'
              }`}
              value={form.payload}
              onChange={(e) => setForm({ ...form, payload: e.target.value })}
              spellCheck={false}
            />
            {payloadError && (
              <p className="text-xs text-red-600 mt-1">{payloadError}</p>
            )}
          </div>

          {error && (
            <div className="flex items-center gap-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded p-3">
              <AlertCircle size={16} />
              {error}
            </div>
          )}

          <div className="flex items-start gap-3 bg-amber-50 border border-amber-200 rounded p-3">
            <AlertCircle size={16} className="text-amber-600 shrink-0 mt-0.5" />
            <p className="text-xs text-amber-800">
              By signing this commitment, you confirm that WAE approval quorum has been met
              and the payload is accurate. This record cannot be deleted.
              Dev mode: HMAC-SHA256. Production: RSA-2048/Ed25519 via HSM/QTSP.
            </p>
          </div>

          <button
            onClick={handleSign}
            disabled={signing}
            className="w-full flex items-center justify-center gap-2 py-2.5 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50 font-medium"
          >
            <Lock size={16} />
            {signing ? 'Signing…' : 'Sign Commitment'}
          </button>
        </div>
      )}

      <div className="mt-6 text-xs text-gray-400 border-t pt-4">
        Domain 6 — CSS · eIDAS Regulation 910/2014 ·
        Chain: ABAC → SoD → DRPL → WAE → [quorum] → CSS → DB
      </div>
    </div>
  )
}
