// Screen: Panel on the project report (/project-report)
/**
 * The project's premises — financing model and power model — and their
 * changes (JML 2026-10-28; /api/v1/premises). A change that removes evidence
 * waits for its document and a second party; any party may contest one, which
 * restores the protections until GEX staff decide. The server decides who may
 * do what; the buttons only offer what it would accept.
 */
import { useCallback, useEffect, useState } from 'react'
import { FileText, Scale } from 'lucide-react'
import { getAuthHeader } from '@/lib/authToken'

interface PremiseDoc { id: number; role: 'SUPPORT' | 'CONTEST'; sha256: string; filename: string; uploaded_by: string; note: string | null }
interface Change {
  id: number; field: string; from_value: string | null; to_value: string; status: string; applied: boolean
  proposed_by: string; proposed_company: string | null; proposed_at: string
  decided_by: string | null; decision_note: string | null; documents: PremiseDoc[]; undocumented: boolean
}
interface Premises {
  declared: Record<string, string | null>
  in_force_for_the_engine: Record<string, string | null>
  changes: Change[]
  you: { is_owner_executive: boolean; is_gex: boolean; is_project_party: boolean; company_id: string | null }
}

const OPTIONS: Record<string, string[]> = {
  financing_model: ['PROJECT_FINANCE', 'BALANCE_SHEET'],
  power_model: ['GRID_CONNECTED', 'OFF_GRID_BTM', 'HYBRID'],
}
const text = (s?: string | null) => (s ?? 'not declared').replace(/_/g, ' ')

export function PremisesPanel({ projectId, onChanged }: { projectId: string; onChanged: () => void }) {
  const [data, setData] = useState<Premises | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState<{ field: string; to_value: string; file: File | null }>(
    { field: 'financing_model', to_value: 'BALANCE_SHEET', file: null })
  const [contest, setContest] = useState<{ id: number; note: string; file: File | null } | null>(null)

  const load = useCallback(() => {
    fetch(`/api/v1/premises/${encodeURIComponent(projectId)}`, { headers: getAuthHeader() })
      .then(async r => { if (!r.ok) throw new Error(`The server answered ${r.status}.`); return r.json() })
      .then(setData).catch(e => setError(e.message))
  }, [projectId])
  useEffect(load, [load])

  const send = async (path: string, body: FormData) => {
    setError(null)
    const r = await fetch(`/api/v1/premises/${encodeURIComponent(projectId)}${path}`,
      { method: 'POST', headers: getAuthHeader(), body })
    const j = await r.json().catch(() => ({}))
    if (!r.ok) { setError(j?.detail?.message ?? (typeof j?.detail === 'string' ? j.detail : `Refused (${r.status}).`)); return }
    load(); onChanged()
  }
  const fd = (o: Record<string, string | File | null>) => {
    const f = new FormData()
    Object.entries(o).forEach(([k, v]) => { if (v !== null) f.append(k, v) })
    return f
  }

  if (!data) return <p className="px-5 py-4 text-sm text-gray-400">{error ?? 'Loading premises…'}</p>
  const you = data.you
  return (
    <div className="rounded-2xl border border-gray-200 bg-white">
      <h2 className="flex items-center gap-2 border-b border-gray-100 px-5 py-3 text-sm font-bold text-gray-900">
        <Scale className="h-4 w-4" /> Premises — they decide which evidence applies
      </h2>
      <div className="grid grid-cols-2 gap-3 px-5 py-3 text-sm">
        {Object.keys(OPTIONS).map(f => {
          const engine = data.in_force_for_the_engine[f], declared = data.declared[f]
          return (
            <div key={f}>
              <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400">{text(f)}</div>
              <div className="font-semibold">{text(engine)}</div>
              {engine !== declared && (
                <div className="text-xs text-amber-700">declared {text(declared)} — contested, so the protective premise applies</div>
              )}
            </div>
          )
        })}
      </div>
      {error && <p className="mx-5 mb-2 rounded bg-amber-50 px-3 py-2 text-xs text-amber-800">{error}</p>}
      <div className="divide-y divide-gray-100">
        {data.changes.map(c => {
          const open = c.status === 'PENDING' || c.status === 'CONTESTED'
          const mine = you.company_id && you.company_id === c.proposed_company
          return (
            <div key={c.id} className="px-5 py-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold">{text(c.field)}: {text(c.from_value)} → {text(c.to_value)}</span>
                <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-bold">{c.status}</span>
                {c.proposed_by === 'PRE_RULE_DECLARATION' && (
                  <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold text-amber-800">declared before the rule · undocumented</span>
                )}
              </div>
              <div className="text-xs text-gray-500">proposed by {c.proposed_by}{c.decided_by ? ` · decided by ${c.decided_by}` : ''}</div>
              {c.documents.map(d => (
                <div key={d.id} className="flex items-center gap-1 text-xs text-gray-600">
                  <FileText className="h-3 w-3" /> {d.role === 'SUPPORT' ? 'supports' : 'contests'}: {d.filename}
                  <span className="font-mono text-gray-400">{d.sha256.slice(0, 12)}…</span> · {d.uploaded_by}{d.note ? ` — ${d.note}` : ''}
                </div>
              ))}
              <div className="mt-1 flex gap-2">
                {open && (you.is_gex || (c.status === 'PENDING' && you.is_project_party && !mine)) && (
                  <button className="rounded bg-teal-700 px-2 py-1 text-xs font-semibold text-white"
                    onClick={() => send(`/${c.id}/confirm`, fd({}))}>Confirm</button>
                )}
                {(open || c.status === 'CONFIRMED') && (you.is_project_party || you.is_gex) && (
                  <button className="rounded border border-amber-400 px-2 py-1 text-xs font-semibold text-amber-800"
                    onClick={() => setContest({ id: c.id, note: '', file: null })}>Contest</button>
                )}
                {open && (mine || you.is_gex) && (
                  <button className="rounded border border-gray-300 px-2 py-1 text-xs" onClick={() => send(`/${c.id}/withdraw`, fd({}))}>Withdraw</button>
                )}
                {open && you.is_gex && (
                  <button className="rounded border border-red-300 px-2 py-1 text-xs text-red-700"
                    onClick={() => send(`/${c.id}/reject`, fd({ note: 'Rejected by GEX staff' }))}>Reject</button>
                )}
              </div>
              {contest?.id === c.id && (
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <input className="rounded border px-2 py-1 text-xs" placeholder="Why it must not apply"
                    value={contest.note} onChange={e => setContest({ ...contest, note: e.target.value })} />
                  <input type="file" className="text-xs" onChange={e => setContest({ ...contest, file: e.target.files?.[0] ?? null })} />
                  <button className="rounded bg-amber-600 px-2 py-1 text-xs font-semibold text-white"
                    disabled={!contest.note || !contest.file}
                    onClick={() => send(`/${c.id}/contest`, fd({ note: contest.note, file: contest.file })).then(() => setContest(null))}>
                    Register contest
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>
      {(you.is_owner_executive || you.is_gex) && (
        <div className="flex flex-wrap items-center gap-2 border-t border-gray-100 px-5 py-3 text-xs">
          <span className="font-semibold">Propose a change:</span>
          <select className="rounded border px-1 py-1" value={form.field}
            onChange={e => setForm({ ...form, field: e.target.value, to_value: OPTIONS[e.target.value][0] })}>
            {Object.keys(OPTIONS).map(f => <option key={f} value={f}>{text(f)}</option>)}
          </select>
          <select className="rounded border px-1 py-1" value={form.to_value} onChange={e => setForm({ ...form, to_value: e.target.value })}>
            {OPTIONS[form.field].map(v => <option key={v} value={v}>{text(v)}</option>)}
          </select>
          <input type="file" onChange={e => setForm({ ...form, file: e.target.files?.[0] ?? null })} />
          <button className="rounded bg-gray-900 px-2 py-1 font-semibold text-white"
            onClick={() => send('', fd({ field: form.field, to_value: form.to_value, file: form.file }))}>Propose</button>
          <span className="text-gray-500">A change that removes evidence needs its document and waits for a second party.</span>
        </div>
      )}
    </div>
  )
}
