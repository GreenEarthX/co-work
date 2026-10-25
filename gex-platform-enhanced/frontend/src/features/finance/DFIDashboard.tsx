// Screen: DFI criteria dashboard (/finance/dfi-dashboard)
/**
 * DFIDashboard — per-institution DFI criteria tracking for the selected project.
 *
 * Real data only (2026-10-25). It used to show one invented list — EIB, IFC,
 * KfW … with criteria already marked MET, IRRs with and without DFI money and
 * catalytic ratios — for EVERY project (MOCK_DFI.default). Now it reads the
 * project's recorded criteria (GET /api/v1/dfi-criteria/project/{id}, PostgreSQL)
 * and groups them by institution. The additionality test has no store: it is
 * shown as not recorded.
 */
import { useEffect, useMemo, useState } from 'react'
import { Building2, Lock, CheckCircle, Clock, AlertCircle } from 'lucide-react'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { getAuthHeader } from '@/lib/authToken'

interface Criterion {
  criterion_id: string
  institution: string
  criterion_code: string
  criterion_name: string
  requirement_text: string
  status: string
  evidence_ref: string | null
  responsible_actor: string
  target_date: string | null
  blocks_drawdown: boolean
}

const STATUS_STYLE: Record<string, { cls: string; icon: React.ReactNode }> = {
  MET:         { cls: 'bg-green-100 text-green-700 border-green-300', icon: <CheckCircle className="w-3.5 h-3.5" /> },
  IN_PROGRESS: { cls: 'bg-amber-100 text-amber-700 border-amber-300', icon: <Clock className="w-3.5 h-3.5" /> },
}
const OTHER = { cls: 'bg-gray-100 text-gray-500 border-gray-300', icon: <AlertCircle className="w-3.5 h-3.5" /> }

export function DFIDashboard() {
  const { selectedProjectId } = useSelectedProject()
  const [rows, setRows] = useState<Criterion[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [active, setActive] = useState('')

  useEffect(() => {
    if (!selectedProjectId) { setRows([]); return }
    setRows(null); setError(null)
    fetch(`/api/v1/dfi-criteria/project/${encodeURIComponent(selectedProjectId)}`, { headers: getAuthHeader() })
      .then(async r => { if (!r.ok) throw new Error(`The server answered ${r.status}.`); return r.json() })
      .then((d: Criterion[]) => setRows(d))
      .catch(e => setError(e.message))
  }, [selectedProjectId])

  const byInstitution = useMemo(() => {
    const m = new Map<string, Criterion[]>()
    for (const c of rows ?? []) m.set(c.institution, [...(m.get(c.institution) ?? []), c])
    return m
  }, [rows])
  const institutions = [...byInstitution.keys()]
  const current = byInstitution.get(active) ?? byInstitution.get(institutions[0]) ?? []

  return (
    <div className="space-y-4 max-w-6xl mx-auto pb-8">
      <div className="rounded-2xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        <div className="px-6 py-4 bg-gradient-to-r from-gray-900 to-gray-800">
          <div className="flex items-center gap-2 mb-1">
            <Building2 className="w-4 h-4 text-gray-400" />
            <span className="text-xs font-bold uppercase tracking-widest text-gray-400">DFI Dashboard</span>
          </div>
          <h1 className="text-2xl font-black text-white">Development Finance Institution Criteria</h1>
          <p className="text-sm text-gray-400 mt-0.5">The criteria recorded for this project, by institution</p>
        </div>
      </div>

      {error ? (
        <p className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">DFI criteria unavailable: {error}</p>
      ) : rows === null ? (
        <p className="text-sm text-gray-400">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm text-gray-500">
          No DFI criteria are recorded for this project.
        </p>
      ) : (
        <>
          <div className="flex items-center gap-1 border-b border-gray-200 overflow-x-auto">
            {institutions.map(i => (
              <button key={i} type="button" onClick={() => setActive(i)}
                className={`px-4 py-2.5 text-xs font-bold rounded-t-lg border border-b-0 whitespace-nowrap ${
                  (active || institutions[0]) === i ? 'bg-white border-gray-200 text-gray-900 -mb-px' : 'bg-gray-50 border-transparent text-gray-500'}`}>
                {i} ({byInstitution.get(i)!.filter(c => c.status === 'MET').length}/{byInstitution.get(i)!.length})
              </button>
            ))}
          </div>
          <div className="rounded-xl border border-gray-200 bg-white divide-y divide-gray-100">
            {current.map(c => {
              const st = STATUS_STYLE[c.status] ?? OTHER
              return (
                <div key={c.criterion_id} className="px-5 py-3 flex items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px] text-gray-400">{c.criterion_code}</span>
                      <span className="text-sm font-semibold text-gray-900">{c.criterion_name}</span>
                      {c.blocks_drawdown && <span className="inline-flex items-center gap-1 text-[10px] text-red-600"><Lock className="w-3 h-3" /> blocks drawdown</span>}
                    </div>
                    <p className="text-xs text-gray-500 mt-0.5">{c.requirement_text}</p>
                    <p className="text-[10px] text-gray-400 mt-0.5">{c.responsible_actor}{c.target_date ? ` · target ${c.target_date}` : ''}{c.evidence_ref ? ` · evidence ${c.evidence_ref}` : ''}</p>
                  </div>
                  <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-semibold ${st.cls}`}>{st.icon} {c.status.replace(/_/g, ' ')}</span>
                </div>
              )
            })}
          </div>
        </>
      )}

      <div className="rounded-xl border border-gray-200 bg-white px-5 py-3 text-xs text-gray-500">
        Additionality test (IRR with and without DFI capital, catalytic ratio): not recorded.
      </div>
    </div>
  )
}
