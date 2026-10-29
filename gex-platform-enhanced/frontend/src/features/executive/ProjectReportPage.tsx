// Screen: Project report (/project-report)
/**
 * One project as the GEX engine sees it, for a CEO or project manager
 * (JML, 2026-10-28): where the project stands, everything still open — side by
 * side, because evidence, contracts and checks move in parallel — and what
 * changed since the last look.
 *
 * Data: GET /api/v1/projects/{id}/report (the engine's snapshot, scoped to the
 * caller's role) and GET /api/v1/bankability-updates (the notifications pushed
 * to designated executives on every re-evaluation that moves something).
 * Nothing on this page is typed by hand.
 */
import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Bell, CheckCircle2, CircleDashed, FileWarning, Split, Users } from 'lucide-react'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { getAuthHeader } from '@/lib/authToken'
import { PremisesPanel } from './PremisesPanel'
import { ContractTokensPanel } from './ContractTokensPanel'

interface OpenItem {
  gate_id: string
  gate_name: string
  determination: string
  holds_back: string | null
  kind: 'evidence' | 'commitment' | 'contradiction' | 'missing_data' | 'trigger'
  what: string
  severity?: string
  status?: string
  maturity?: { required: string | null; declared: string | null; status: string }
  owner_function?: string
  assignee?: string | null
  due_date?: string | null
  overdue?: boolean
  action?: string
}

interface Report {
  project_id: string
  project_name: string
  bankability: {
    evaluated: boolean
    state: string | null
    state_label: string | null
    next_state?: string | null
    overall_completion: number | null
    rules_version: string | null
    evaluated_at: string | null
    scope: { persona: string; visible_gates: number; total_gates: number; note?: string | null }
    gates: { id: string; name: string; determination: string; completion_pct: number }[]
  }
  open_items: {
    evaluated: boolean
    items: OpenItem[]
    summary: { open: number; by_kind: Record<string, number>; deal_killers: number; unassigned: number;
               overdue: number; without_due_date: number }
  }
  recipients: string[]
}

interface Update {
  id: number; project_id: string; created_at: string; reason: string
  from_state: string | null; to_state: string | null
  gate_changes: { gate_name: string; from: string | null; to: string | null }[]; read_at: string | null
}

const KIND: Record<OpenItem['kind'], { label: string; Icon: any; cls: string }> = {
  evidence:      { label: 'Evidence to verify', Icon: CircleDashed, cls: 'text-gray-600' },
  commitment:    { label: 'Commitment not reached', Icon: CircleDashed, cls: 'text-amber-700' },
  contradiction: { label: 'Contracts disagree', Icon: Split, cls: 'text-red-600' },
  missing_data:  { label: 'Data missing',       Icon: FileWarning, cls: 'text-amber-600' },
  trigger:       { label: 'Event undermines',   Icon: AlertTriangle, cls: 'text-red-600' },
}

const DETERMINATION_CLS: Record<string, string> = {
  SATISFIED: 'bg-emerald-100 text-emerald-800', WAIVED: 'bg-gray-100 text-gray-600',
  BLOCKED: 'bg-red-100 text-red-800', UNRESOLVED: 'bg-amber-100 text-amber-800',
  INCOMPLETE: 'bg-gray-100 text-gray-700',
}

const text = (s?: string | null) => (s ?? '—').replace(/_/g, ' ')

export function ProjectReportPage() {
  const { selectedProjectId } = useSelectedProject()
  const [report, setReport] = useState<Report | null>(null)
  const [updates, setUpdates] = useState<Update[]>([])
  const [error, setError] = useState<string | null>(null)
  const [kind, setKind] = useState<'ALL' | OpenItem['kind']>('ALL')

  const [reloadKey, setReloadKey] = useState(0)
  useEffect(() => {
    if (!selectedProjectId) { setReport(null); return }
    setReport(null); setError(null)
    fetch(`/api/v1/projects/${encodeURIComponent(selectedProjectId)}/report`, { headers: getAuthHeader() })
      .then(async r => { if (!r.ok) throw new Error(`The server answered ${r.status}.`); return r.json() })
      .then(setReport)
      .catch(e => setError(e.message))
    fetch('/api/v1/bankability-updates', { headers: getAuthHeader() })
      .then(r => (r.ok ? r.json() : { items: [] }))
      .then(d => setUpdates((d.items ?? []).filter((u: Update) => u.project_id === selectedProjectId)))
      .catch(() => setUpdates([]))
  }, [selectedProjectId, reloadKey])

  const markRead = (id: number) =>
    fetch(`/api/v1/bankability-updates/${id}/read`, { method: 'POST', headers: getAuthHeader() })
      .then(() => setUpdates(us => us.map(u => (u.id === id ? { ...u, read_at: new Date().toISOString() } : u))))

  const items = useMemo(() => (report?.open_items.items ?? []).filter(i => kind === 'ALL' || i.kind === kind),
    [report, kind])

  if (!selectedProjectId) return <p className="p-6 text-sm text-gray-500">Select a project.</p>
  if (error) return <p className="m-6 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">Report unavailable: {error}</p>
  if (!report) return <p className="p-6 text-sm text-gray-400">Loading…</p>

  const b = report.bankability
  const s = report.open_items.summary
  return (
    <div className="mx-auto max-w-6xl space-y-5 p-6">
      <div className="rounded-2xl border border-gray-200 bg-white p-5">
        <p className="text-xs font-bold uppercase tracking-widest text-gray-400">Project report</p>
        <h1 className="text-2xl font-black text-gray-900">{report.project_name}</h1>
        {!b.evaluated ? (
          <p className="mt-2 text-sm text-amber-700">Not yet evaluated by the GEX engine.</p>
        ) : (
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <span className="rounded-lg bg-gray-900 px-3 py-1.5 text-sm font-black text-white">{text(b.state)}</span>
            <span className="text-sm text-gray-600">{b.state_label}</span>
            {b.next_state && <span className="text-sm text-gray-500">→ next: <strong>{text(b.next_state)}</strong></span>}
            <span className="text-sm text-gray-600"><strong>{Math.round(b.overall_completion ?? 0)}%</strong> of required evidence verified</span>
          </div>
        )}
        <p className="mt-2 font-mono text-[11px] text-gray-400">
          GEX engine{b.rules_version ? ` · rules ${b.rules_version}` : ''}{b.evaluated_at ? ` · evaluated ${new Date(b.evaluated_at).toLocaleString('en-GB')}` : ''}
          {b.scope?.note ? ` · ${b.scope.note}` : ''}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {[
          ['Open items', s?.open ?? 0, ''],
          ['Deal-killers', s?.deal_killers ?? 0, 'text-red-600'],
          ['Contracts disagree', s?.by_kind?.contradiction ?? 0, 'text-red-600'],
          ['Data missing', s?.by_kind?.missing_data ?? 0, 'text-amber-600'],
          ['Overdue / no due date', `${s?.overdue ?? 0} / ${s?.without_due_date ?? 0}`, 'text-amber-600'],
        ].map(([label, value, cls]) => (
          <div key={label as string} className="rounded-xl border border-gray-200 bg-white px-4 py-3">
            <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400">{label}</div>
            <div className={`text-2xl font-black ${cls || 'text-gray-900'}`}>{value}</div>
          </div>
        ))}
      </div>

      <div className="rounded-2xl border border-gray-200 bg-white">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-100 px-5 py-3">
          <h2 className="text-sm font-bold text-gray-900">Everything still open — all gates at once</h2>
          <div className="flex gap-1">
            {(['ALL', 'evidence', 'commitment', 'contradiction', 'missing_data', 'trigger'] as const).map(k => (
              <button key={k} onClick={() => setKind(k)}
                className={`rounded-md px-2.5 py-1 text-xs font-semibold ${kind === k ? 'bg-gray-900 text-white' : 'text-gray-500 hover:bg-gray-100'}`}>
                {k === 'ALL' ? 'All' : KIND[k].label}
              </button>
            ))}
          </div>
        </div>
        {items.length === 0 ? (
          <p className="px-5 py-4 text-sm text-gray-500">{report.open_items.evaluated ? 'Nothing open here.' : 'Not yet evaluated.'}</p>
        ) : (
          <div className="divide-y divide-gray-100">
            {items.map((i, n) => {
              const k = KIND[i.kind]
              return (
                <div key={`${i.gate_id}-${n}`} className="grid grid-cols-12 gap-3 px-5 py-3 text-sm">
                  <div className="col-span-3">
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${DETERMINATION_CLS[i.determination] ?? 'bg-gray-100'}`}>{i.determination}</span>
                    <div className="mt-1 font-semibold text-gray-800">{i.gate_name}</div>
                    {i.holds_back && <div className="text-[11px] text-gray-400">holds back {text(i.holds_back)}</div>}
                  </div>
                  <div className="col-span-5">
                    <div className={`flex items-center gap-1.5 text-[11px] font-bold ${k.cls}`}><k.Icon className="h-3.5 w-3.5" /> {k.label}
                      {i.severity === 'deal_killer' && <span className="text-red-600">· deal-killer</span>}</div>
                    <div className="text-gray-800">{i.what}</div>
                    {i.maturity?.required && (
                      <div className="text-[11px] text-gray-500">maturity required {i.maturity.required}; declared {i.maturity.declared ?? 'none'}</div>
                    )}
                  </div>
                  <div className="col-span-2 text-xs text-gray-600">
                    <div className="flex items-center gap-1"><Users className="h-3 w-3" /> {i.assignee ?? text(i.owner_function)}</div>
                    <div className={i.overdue ? 'font-bold text-red-600' : ''}>{i.due_date ? `due ${i.due_date}` : 'no due date'}</div>
                  </div>
                  <div className="col-span-2 text-xs text-gray-500">{i.action}</div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <PremisesPanel projectId={selectedProjectId} onChanged={() => setReloadKey(k => k + 1)} />
      <ContractTokensPanel projectId={selectedProjectId} onChanged={() => setReloadKey(k => k + 1)} />

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-2xl border border-gray-200 bg-white">
          <h2 className="flex items-center gap-2 border-b border-gray-100 px-5 py-3 text-sm font-bold text-gray-900">
            <Bell className="h-4 w-4" /> What changed
          </h2>
          {updates.length === 0 ? (
            <p className="px-5 py-4 text-sm text-gray-500">No change reported to you for this project.</p>
          ) : updates.map(u => (
            <div key={u.id} className={`border-b border-gray-50 px-5 py-3 text-sm ${u.read_at ? 'opacity-60' : ''}`}>
              <div className="flex items-center justify-between">
                <span className="font-semibold">{u.from_state !== u.to_state ? `${text(u.from_state)} → ${text(u.to_state)}` : 'Gate change'}</span>
                {!u.read_at && <button onClick={() => markRead(u.id)} className="text-xs text-teal-700 underline">mark read</button>}
              </div>
              <div className="text-xs text-gray-500">{new Date(u.created_at).toLocaleString('en-GB')} · {u.reason}</div>
              {u.gate_changes.map(g => (
                <div key={g.gate_name} className="text-xs text-gray-600">{g.gate_name}: {text(g.from)} → {text(g.to)}</div>
              ))}
            </div>
          ))}
        </div>
        <div className="rounded-2xl border border-gray-200 bg-white">
          <h2 className="flex items-center gap-2 border-b border-gray-100 px-5 py-3 text-sm font-bold text-gray-900">
            <CheckCircle2 className="h-4 w-4" /> Gates
          </h2>
          {b.gates.map(g => (
            <div key={g.id} className="flex items-center justify-between border-b border-gray-50 px-5 py-2 text-sm">
              <span>{g.name}</span>
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${DETERMINATION_CLS[g.determination] ?? 'bg-gray-100'}`}>{g.determination}</span>
            </div>
          ))}
          <p className="px-5 py-3 text-xs text-gray-500">Reports go to: {report.recipients.join(', ') || 'nobody designated'}</p>
        </div>
      </div>
    </div>
  )
}
