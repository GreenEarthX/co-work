/**
 * ClientCISODashboard — one company's CISO workspace.
 *
 * Route: /ciso/client/:companyId
 *
 * Real data only (2026-10-25). Until then every tab fell back to invented
 * people, approvals, SoD violations, barriers, residency rows, commitments and
 * compliance statuses for five sample companies whenever a call failed — and the
 * calls sent no company the server could trust. Now each tab shows what the
 * server returns, says what is not recorded, and shows a refusal as a refusal.
 * GEX staff may open any company (x-ciso-company); a client CISO only its own.
 *
 *  monitoring   overview from accounts + sign-ins, sign-in history, OT gateways
 *  wae          approval requests + platform approval policies
 *  users        account attributes and project roles (edited on Identity & Access)
 *  sod          conflict pairs (violations are not recorded)
 *  barriers     information barriers (alembic 070)
 *  residency    recorded residency policies (storage location is not measured)
 *  commitments  commitment records on the company's projects
 *  compliance   not recorded
 */

import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Shield, ArrowLeft, AlertTriangle, Activity, CheckCircle, XCircle, Users, Lock, Eye,
  Workflow, Split, Columns, MapPin, Fingerprint, FileCheck, UserCog, Wifi, WifiOff,
  Plus, ChevronDown, ChevronUp, FileSignature, Hash, Pencil, Save,
} from 'lucide-react'
import { cisoCall, NOT_RECORDED } from './cisoApi'

const DATA_CATEGORIES = [
  'PERSONAL', 'CONTRACT', 'FINANCIAL_MODEL', 'CERTIFICATION',
  'COMMS_METADATA', 'PLANT_DATA', 'AUDIT_LOG',
]
const ALWAYS_EU = new Set(['AUDIT_LOG', 'COMMS_METADATA'])

type TabKey = 'monitoring' | 'wae' | 'users' | 'sod' | 'barriers' | 'residency' | 'commitments' | 'compliance'

const when = (ts?: string) => ts
  ? new Date(ts).toLocaleString('en-GB', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  : '—'

function Kpi({ label, value, sub, accent, Icon }: { label: string; value: string | number; sub?: string; accent?: string; Icon?: any }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5 shadow-card">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">{label}</span>
        {Icon && <Icon className="w-3 h-3 text-[var(--text-muted)]" />}
      </div>
      <div className={`mt-0.5 font-display text-xl font-extrabold leading-none ${accent ?? 'text-[var(--text-primary)]'}`}>{value}</div>
      {sub && <div className="text-[10px] text-[var(--text-muted)] mt-0.5">{sub}</div>}
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    PENDING_APPROVAL: 'gex-badge gex-badge-amber', APPROVED: 'gex-badge gex-badge-green',
    REJECTED: 'gex-badge gex-badge-red', EXPIRED: 'gex-badge gex-badge-default',
    FULLY_SIGNED: 'gex-badge gex-badge-green', PENDING_COUNTERSIGN: 'gex-badge gex-badge-amber',
    ONLINE: 'gex-badge gex-badge-green', OFFLINE: 'gex-badge gex-badge-red',
  }
  return <span className={map[status] ?? 'gex-badge gex-badge-default'}>{status.replace(/_/g, ' ')}</span>
}

function Panel({ title, Icon, note, action, children }: { title: string; Icon?: any; note?: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
      <div className="flex items-center justify-between gap-3 border-b border-[var(--border)] px-5 py-3.5">
        <div>
          <h2 className="text-sm font-bold text-[var(--text-primary)] flex items-center gap-2">
            {Icon && <Icon className="w-4 h-4 text-[var(--text-muted)]" />} {title}
          </h2>
          {note && <p className="text-xs text-[var(--text-muted)] mt-0.5">{note}</p>}
        </div>
        {action}
      </div>
      {children}
    </div>
  )
}

const Empty = ({ children }: { children: React.ReactNode }) =>
  <p className="px-5 py-4 text-sm text-[var(--text-muted)]">{children}</p>

const Refusal = ({ message }: { message: string }) => (
  <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800/40 dark:bg-amber-900/10 dark:text-amber-300">
    {message}
  </div>
)

export function ClientCISODashboard() {
  const { companyId = '' } = useParams<{ companyId: string }>()
  const navigate = useNavigate()
  const call = useCallback(<T = any,>(path: string, init?: RequestInit) => cisoCall<T>(path, companyId, init), [companyId])

  const [tab, setTab] = useState<TabKey>('monitoring')
  const [data, setData] = useState<Partial<Record<TabKey, any>>>({})
  const [errors, setErrors] = useState<Partial<Record<TabKey, string>>>({})
  const [overview, setOverview] = useState<any>(null)

  const [showBarrierForm, setShowBarrierForm] = useState(false)
  const [barrierForm, setBarrierForm] = useState({ side_a: '', side_b: '', barrier_type: 'HARD', applies_to_data: [] as string[], description: '' })
  const [barrierError, setBarrierError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [resEditing, setResEditing] = useState<string | null>(null)
  const [resForm, setResForm] = useState({ required_jurisdiction: 'EU', storage_zone: 'eu-west-1' })
  const [resError, setResError] = useState<string | null>(null)

  const loaders: Record<TabKey, () => Promise<any>> = {
    monitoring: async () => {
      const [log, gw] = await Promise.all([
        call('/ciso/access-log?limit=30'),
        call('/ciso/gateways').catch(e => ({ gateways: [], unavailable: e.message })),
      ])
      return { log, gw }
    },
    wae: async () => {
      const [pend, pol] = await Promise.all([
        call(`/approvals/pending`),
        call('/approvals/policies/list'),
      ])
      return { approvals: pend.items ?? [], policies: pol.policies ?? [] }
    },
    users: () => call('/ciso/users'),
    sod: () => call('/approvals/sod/pairs'),
    barriers: () => call('/ciso/barriers'),
    residency: async () => {
      const [pols, audit] = await Promise.all([call('/ciso/residency/policies'), call('/ciso/residency/audit')])
      return { policies: pols.policies ?? [], audit }
    },
    commitments: async () => {
      const { projects } = await call('/ciso/users')
      const lists = await Promise.all((projects ?? []).map((p: any) => call(`/commitments/project/${p.id}`)))
      return { projects: projects ?? [], commitments: lists.flatMap((r: any) => r.commitments ?? []) }
    },
    compliance: () => call('/ciso/compliance'),
  }

  const load = useCallback((key: TabKey) => {
    setErrors(e => ({ ...e, [key]: undefined }))
    loaders[key]()
      .then(d => setData(prev => ({ ...prev, [key]: d })))
      .catch(e => setErrors(prev => ({ ...prev, [key]: e.message })))
  }, [companyId])  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setData({}); setErrors({}); setOverview(null)
    call('/ciso/overview').then(setOverview).catch(e => setErrors(prev => ({ ...prev, monitoring: e.message })))
  }, [companyId, call])

  useEffect(() => { if (!(tab in data)) load(tab) }, [tab, data, load])

  const tabs: { key: TabKey; label: string; Icon: any }[] = [
    { key: 'monitoring',  label: 'Monitoring',    Icon: Activity },
    { key: 'wae',         label: 'WAE Approvals', Icon: Workflow },
    { key: 'users',       label: 'Users',         Icon: UserCog },
    { key: 'sod',         label: 'SoD',           Icon: Split },
    { key: 'barriers',    label: 'Barriers',      Icon: Columns },
    { key: 'residency',   label: 'Residency',     Icon: MapPin },
    { key: 'commitments', label: 'Commitments',   Icon: Fingerprint },
    { key: 'compliance',  label: 'Compliance',    Icon: FileCheck },
  ]
  const name = overview?.company_name ?? companyId
  const d = data[tab]
  const err = errors[tab]

  return (
    <div className="animate-fade-in">
      <div className="flex flex-wrap items-center gap-4 mb-5">
        <button
          onClick={() => navigate('/ciso-dashboard')}
          className="flex items-center justify-center h-8 w-8 rounded-lg border border-[var(--border)] bg-[var(--surface)] hover:bg-[var(--surface-hover)] transition-colors"
        >
          <ArrowLeft className="w-4 h-4 text-[var(--text-muted)]" />
        </button>
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-100 dark:bg-indigo-900/30">
            <Shield className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
          </div>
          <div>
            <h1 className="font-display font-bold text-lg text-[var(--text-primary)]">{name} — CISO Dashboard</h1>
            <p className="text-xs text-[var(--text-muted)] font-mono">{companyId}</p>
          </div>
        </div>
        {overview?.alerts?.some((a: any) => a.severity === 'high') && (
          <span className="ml-auto gex-badge gex-badge-red">
            <AlertTriangle className="w-3 h-3 mr-1 inline" /> Active Alert
          </span>
        )}
      </div>

      <div className="flex gap-1 overflow-x-auto pb-1 mb-5">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg whitespace-nowrap transition-colors ${
              tab === t.key ? 'bg-[var(--brand)] text-white' : 'text-[var(--text-muted)] hover:bg-[var(--surface-hover)]'
            }`}
          >
            <t.Icon className="w-3.5 h-3.5" /> {t.label}
          </button>
        ))}
      </div>

      {err && <Refusal message={err} />}
      {!err && !d && tab !== 'monitoring' && <p className="text-sm text-[var(--text-muted)]">Loading…</p>}

      {tab === 'monitoring' && !err && (
        <div className="space-y-5">
          {overview?.alerts?.map((a: any) => (
            <div key={a.id} className={`flex items-start gap-3 rounded-lg border px-4 py-3 ${
              a.severity === 'high' ? 'border-red-200 bg-red-50 dark:border-red-800/40 dark:bg-red-900/10'
              : 'border-amber-200 bg-amber-50 dark:border-amber-800/40 dark:bg-amber-900/10'
            }`}>
              <AlertTriangle className={`w-4 h-4 mt-0.5 shrink-0 ${a.severity === 'high' ? 'text-red-600' : 'text-amber-500'}`} />
              <p className="flex-1 text-sm text-[var(--text-primary)]">{a.message}</p>
              <span className={a.severity === 'high' ? 'gex-badge gex-badge-red' : 'gex-badge gex-badge-amber'}>{a.severity}</span>
            </div>
          ))}
          {overview && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Kpi label="Accounts" value={overview.kpis.total_users} Icon={Users} />
              <Kpi label="MFA Adoption" value={overview.kpis.mfa_enabled_pct ?? NOT_RECORDED} accent="text-[var(--text-muted)]" Icon={Lock} />
              <Kpi label="KYC Verified" value={overview.kpis.kyc_verified} sub={`${overview.kpis.kyc_pending} not verified`} accent="text-[var(--brand)]" Icon={CheckCircle} />
              <Kpi label="Project roles" value={overview.kpis.abac_assigned} sub={`${overview.kpis.abac_unassigned} without one`} accent="text-[var(--brand)]" Icon={Shield} />
              <Kpi label="Sign-ins (24 h)" value={overview.events_24h.total} sub={`${overview.events_24h.allow} accepted / ${overview.events_24h.deny} refused`} Icon={Activity} />
              <Kpi label="ABAC phase" value={overview.abac_phase.current} sub="platform setting" Icon={XCircle} />
            </div>
          )}
          <Panel title="Sign-in history" Icon={Eye} note={d?.log?.note}>
            {(d?.log?.events ?? []).length === 0 ? <Empty>No sign-ins recorded for this company's accounts.</Empty> : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-[var(--border)] text-[var(--text-muted)]">
                      {['Time', 'User', 'Event', 'Result', 'Address'].map(h => <th key={h} className="text-left py-2 px-3 font-medium">{h}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {d.log.events.map((e: any) => (
                      <tr key={e.id} className="border-b border-[var(--border)]/40 hover:bg-[var(--surface-hover)]">
                        <td className="py-1.5 px-3 text-[var(--text-muted)] whitespace-nowrap">{when(e.timestamp)}</td>
                        <td className="py-1.5 px-3 font-medium text-[var(--text-primary)]">{e.user_name}</td>
                        <td className="py-1.5 px-3"><span className="gex-badge gex-badge-default">{e.action}</span></td>
                        <td className="py-1.5 px-3"><span className={e.decision === 'ALLOW' ? 'gex-badge gex-badge-green' : 'gex-badge gex-badge-red'}>{e.decision === 'ALLOW' ? 'accepted' : 'refused'}</span></td>
                        <td className="py-1.5 px-3 text-[var(--text-muted)] font-mono">{e.ip_address ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
          <Panel title="OT Gateways" Icon={Wifi} note={d?.gw?.unavailable}>
            {(d?.gw?.gateways ?? []).length === 0 ? <Empty>No gateway is registered on this company's projects.</Empty> : (
              <div className="divide-y divide-[var(--border)]">
                {d.gw.gateways.map((gw: any) => (
                  <div key={gw.id} className="flex items-center gap-3 px-5 py-3">
                    {gw.active ? <Wifi className="w-4 h-4 text-emerald-500 shrink-0" /> : <WifiOff className="w-4 h-4 text-red-500 shrink-0" />}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-[var(--text-primary)]">{gw.gateway_name}</p>
                      <p className="text-xs text-[var(--text-muted)]">{gw.project_id} · last seen {when(gw.last_seen)}</p>
                    </div>
                    <StatusBadge status={gw.active ? 'ONLINE' : 'OFFLINE'} />
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>
      )}

      {tab === 'wae' && d && (
        <div className="space-y-5">
          <Panel title={`Approval requests — ${name}`} Icon={Workflow}>
            {d.approvals.length === 0 ? <Empty>No approval requests recorded.</Empty> : (
              <div className="divide-y divide-[var(--border)]">
                {d.approvals.map((req: any) => (
                  <div key={req.request_id} className="px-5 py-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-semibold text-[var(--text-primary)]">{(req.action_type ?? '').replace(/_/g, ' ')}</span>
                          <StatusBadge status={req.status} />
                        </div>
                        <p className="text-xs text-[var(--text-muted)] mt-0.5">{req.payload?.description}</p>
                      </div>
                      <div className="text-right shrink-0">
                        {req.amount != null && <p className="text-sm font-bold text-[var(--text-primary)]">€{Number(req.amount).toLocaleString()}</p>}
                        <p className="text-[10px] text-[var(--text-muted)]">{req.project_id}</p>
                      </div>
                    </div>
                    <p className="text-[10px] text-[var(--text-muted)] mt-1">By {req.initiator_user_id} · expires {when(req.expires_at)}</p>
                  </div>
                ))}
              </div>
            )}
          </Panel>
          <Panel title="Platform approval policies">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-[var(--border)] text-[var(--text-muted)]">
                    {['Action Type', 'Threshold', 'Required Approvers'].map(h => <th key={h} className="text-left py-2 px-4 font-medium">{h}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {d.policies.map((p: any) => (
                    <tr key={p.action_type} className="border-b border-[var(--border)]/40">
                      <td className="py-1.5 px-4 font-mono text-[10px] text-[var(--text-primary)]">{p.action_type}</td>
                      <td className="py-1.5 px-4 text-[var(--text-muted)]">{p.threshold_amount ? `> €${(p.threshold_amount / 1000).toFixed(0)}K` : 'Any'}</td>
                      <td className="py-1.5 px-4">{(p.required_roles ?? []).join(', ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      )}

      {tab === 'users' && d && (
        <Panel title={`Accounts — ${name}`} Icon={UserCog}
          note="Attributes are administered by GEX staff on Identity & Access. Project roles come from appointments.">
          {d.users.length === 0 ? <Empty>No accounts are registered for this company.</Empty> : (
            <div className="divide-y divide-[var(--border)]">
              {d.users.map((u: any) => (
                <div key={u.user_id} className="px-5 py-3.5">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold text-[var(--text-primary)]">{u.name}</span>
                    <span className="text-xs text-[var(--text-muted)]">{u.email}</span>
                    <span className={u.account_state === 'ACTIVE' ? 'gex-badge gex-badge-green' : 'gex-badge gex-badge-amber'}>{u.account_state}</span>
                    <span className={u.kyc_status === 'VERIFIED' ? 'gex-badge gex-badge-green' : 'gex-badge gex-badge-amber'}>KYC {u.kyc_status ?? NOT_RECORDED}</span>
                    <span className="gex-badge gex-badge-default"><Lock className="w-2.5 h-2.5 mr-1 inline" />{u.clearance_level ?? NOT_RECORDED}</span>
                    <span className="gex-badge gex-badge-default">MFA {NOT_RECORDED.toLowerCase()}</span>
                  </div>
                  <p className="text-xs text-[var(--text-muted)] mt-1">
                    {Object.keys(u.actor_type_per_project).length === 0 ? 'No project role.'
                      : Object.entries(u.actor_type_per_project).map(([pid, roles]) => `${pid}: ${(roles as string[]).join(', ')}`).join(' · ')}
                  </p>
                </div>
              ))}
            </div>
          )}
        </Panel>
      )}

      {tab === 'sod' && d && (
        <Panel title="Separation-of-duties conflict pairs" Icon={Split}
          note="The platform refuses a conflicting action (HTTP 409). Refusals are not recorded per company yet.">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[var(--border)] text-[var(--text-muted)]">
                  {['ID', 'Action A', 'Action B', 'Scope', 'Description'].map(h => <th key={h} className="text-left py-2 px-4 font-medium">{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {(d.pairs ?? []).map((p: any) => (
                  <tr key={p.id} className="border-b border-[var(--border)]/40">
                    <td className="py-1.5 px-4 font-mono text-[10px]">{p.id}</td>
                    <td className="py-1.5 px-4 font-mono text-[10px]">{p.action_a}</td>
                    <td className="py-1.5 px-4 font-mono text-[10px]">{p.action_b}</td>
                    <td className="py-1.5 px-4"><span className="gex-badge gex-badge-default">{p.resource_scope}</span></td>
                    <td className="py-1.5 px-4 text-[var(--text-muted)]">{p.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      {tab === 'barriers' && d && (
        <Panel title={`Information barriers — ${name}`} Icon={Columns}
          note="Recorded barriers. Breaches are not recorded yet."
          action={
            <button onClick={() => setShowBarrierForm(v => !v)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-[var(--brand)] text-white hover:opacity-90">
              <Plus className="w-3 h-3" /> New Barrier
            </button>
          }>
          {showBarrierForm && (
            <div className="px-5 py-4 border-b border-[var(--border)] bg-[var(--surface-hover)] space-y-3">
              <div className="grid grid-cols-2 gap-3">
                {(['side_a', 'side_b'] as const).map((k, i) => (
                  <label key={k} className="text-[10px] font-medium text-[var(--text-muted)]">
                    Side {i ? 'B' : 'A'}
                    <input className="mt-1 w-full h-8 text-xs rounded border border-[var(--border)] bg-[var(--surface)] px-2 text-[var(--text-primary)]"
                      value={barrierForm[k]} onChange={e => setBarrierForm(f => ({ ...f, [k]: e.target.value }))} />
                  </label>
                ))}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <label className="text-[10px] font-medium text-[var(--text-muted)]">
                  Barrier type
                  <select value={barrierForm.barrier_type} onChange={e => setBarrierForm(f => ({ ...f, barrier_type: e.target.value }))}
                    className="mt-1 w-full h-8 text-xs rounded border border-[var(--border)] bg-[var(--surface)] px-2 text-[var(--text-primary)]">
                    {['HARD', 'SOFT', 'CHINESE_WALL'].map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </label>
                <div>
                  <p className="text-[10px] font-medium text-[var(--text-muted)] mb-1">Applies to data</p>
                  <div className="flex flex-wrap gap-1">
                    {DATA_CATEGORIES.map(cat => (
                      <button key={cat}
                        onClick={() => setBarrierForm(f => ({ ...f, applies_to_data: f.applies_to_data.includes(cat)
                          ? f.applies_to_data.filter(c => c !== cat) : [...f.applies_to_data, cat] }))}
                        className={`text-[9px] px-2 py-0.5 rounded border ${barrierForm.applies_to_data.includes(cat)
                          ? 'bg-[var(--brand)] text-white border-[var(--brand)]' : 'border-[var(--border)] text-[var(--text-muted)]'}`}
                      >{cat}</button>
                    ))}
                  </div>
                </div>
              </div>
              <input className="w-full h-8 text-xs rounded border border-[var(--border)] bg-[var(--surface)] px-2 text-[var(--text-primary)]"
                placeholder="Description" value={barrierForm.description}
                onChange={e => setBarrierForm(f => ({ ...f, description: e.target.value }))} />
              {barrierError && <p className="text-xs text-red-600">{barrierError}</p>}
              <div className="flex gap-2">
                <button
                  onClick={async () => {
                    try {
                      await call('/ciso/barriers', { method: 'POST', body: JSON.stringify(barrierForm) })
                      setShowBarrierForm(false); setBarrierError(null)
                      setBarrierForm({ side_a: '', side_b: '', barrier_type: 'HARD', applies_to_data: [], description: '' })
                      load('barriers')
                    } catch (e) { setBarrierError((e as Error).message) }
                  }}
                  className="px-4 py-1.5 text-xs bg-[var(--brand)] text-white rounded-lg hover:opacity-90"
                >Create</button>
                <button onClick={() => setShowBarrierForm(false)} className="px-4 py-1.5 text-xs border border-[var(--border)] rounded-lg text-[var(--text-secondary)]">Cancel</button>
              </div>
            </div>
          )}
          {d.barriers.length === 0 ? <Empty>No information barrier is recorded.</Empty> : (
            <div className="divide-y divide-[var(--border)]">
              {d.barriers.map((b: any) => (
                <div key={b.id}>
                  <div className="flex items-center justify-between px-5 py-4 cursor-pointer hover:bg-[var(--surface-hover)]"
                    onClick={() => setExpanded(expanded === b.id ? null : b.id)}>
                    <div className="flex items-center gap-3 min-w-0">
                      <span className={`gex-badge ${b.barrier_type === 'SOFT' ? 'gex-badge-amber' : 'gex-badge-red'}`}>{b.barrier_type}</span>
                      <span className="text-sm font-mono font-semibold text-[var(--text-primary)]">{b.side_a}</span>
                      <span className="text-xs text-[var(--text-muted)]">⇔</span>
                      <span className="text-sm font-mono font-semibold text-[var(--text-primary)]">{b.side_b}</span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className={b.active ? 'gex-badge gex-badge-green' : 'gex-badge gex-badge-default'}>{b.active ? 'Active' : 'Inactive'}</span>
                      {expanded === b.id ? <ChevronUp className="w-4 h-4 text-[var(--text-muted)]" /> : <ChevronDown className="w-4 h-4 text-[var(--text-muted)]" />}
                    </div>
                  </div>
                  {expanded === b.id && (
                    <div className="bg-[var(--surface-hover)] border-t border-[var(--border)] px-5 py-3 space-y-2">
                      <p className="text-xs text-[var(--text-muted)]">{b.description || 'No description'} · created by {b.created_by}, {when(b.created_at)}</p>
                      <div className="flex flex-wrap gap-1">
                        {b.applies_to_data.map((x: string) => <span key={x} className="gex-badge gex-badge-default text-[9px]">{x}</span>)}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </Panel>
      )}

      {tab === 'residency' && d && (
        <Panel title={`Data residency — ${name}`} Icon={MapPin}
          note="Required jurisdiction per data category, as recorded. Where the data is actually stored is not measured.">
          {resError && <p className="px-5 pt-3 text-xs text-red-600">{resError}</p>}
          <div className="divide-y divide-[var(--border)]">
            {DATA_CATEGORIES.map(cat => {
              const rec = d.audit?.categories?.[cat]
              const pol = d.policies.find((p: any) => p.data_category === cat)
              return (
                <div key={cat} className="flex items-center justify-between px-5 py-3">
                  <div className="flex items-center gap-3">
                    <span className="gex-badge gex-badge-default font-mono text-[9px]">{cat}</span>
                    <span className="text-sm text-[var(--text-primary)]">
                      Required: <strong>{rec?.required_jurisdiction ?? NOT_RECORDED}</strong>
                      {pol?.storage_zone && <span className="text-xs text-[var(--text-muted)]"> · zone {pol.storage_zone}</span>}
                    </span>
                    {ALWAYS_EU.has(cat) && <Lock className="w-3 h-3 text-[var(--text-muted)]" />}
                  </div>
                  {!ALWAYS_EU.has(cat) && (resEditing === cat ? (
                    <div className="flex items-center gap-2">
                      <select value={resForm.required_jurisdiction} onChange={e => setResForm(f => ({ ...f, required_jurisdiction: e.target.value }))}
                        className="h-7 text-xs rounded border border-[var(--border)] bg-[var(--surface)] px-1 text-[var(--text-primary)]">
                        {['EU', 'GB', 'CH', 'US'].map(j => <option key={j} value={j}>{j}</option>)}
                      </select>
                      <select value={resForm.storage_zone} onChange={e => setResForm(f => ({ ...f, storage_zone: e.target.value }))}
                        className="h-7 text-xs rounded border border-[var(--border)] bg-[var(--surface)] px-1 text-[var(--text-primary)]">
                        {['eu-west-1', 'ch-zurich-1', 'gb-london-1'].map(z => <option key={z} value={z}>{z}</option>)}
                      </select>
                      <button className="px-2 py-1 text-[10px] bg-[var(--brand)] text-white rounded"
                        onClick={async () => {
                          try {
                            await call('/ciso/residency/policies', { method: 'POST', body: JSON.stringify({ data_category: cat, ...resForm }) })
                            setResEditing(null); setResError(null); load('residency')
                          } catch (e) { setResError((e as Error).message) }
                        }}><Save className="w-3 h-3" /></button>
                      <button onClick={() => setResEditing(null)}><XCircle className="w-3.5 h-3.5 text-[var(--text-muted)]" /></button>
                    </div>
                  ) : (
                    <button className="text-[var(--text-muted)] hover:text-[var(--brand)]"
                      onClick={() => { setResEditing(cat); setResForm({ required_jurisdiction: rec?.required_jurisdiction ?? 'EU', storage_zone: pol?.storage_zone ?? 'eu-west-1' }) }}>
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                  ))}
                </div>
              )
            })}
          </div>
        </Panel>
      )}

      {tab === 'commitments' && d && (
        <Panel title={`Commitment records — ${name}`} Icon={Fingerprint}
          note={`On ${d.projects.length} project(s) this company is a stakeholder in. Append-only.`}>
          {d.commitments.length === 0 ? <Empty>No commitment record on this company's projects.</Empty> : (
            <div className="divide-y divide-[var(--border)]">
              {d.commitments.map((c: any) => (
                <div key={c.commitment_id ?? c.id} className="px-5 py-4">
                  <div className="flex items-center gap-2 flex-wrap">
                    <FileSignature className="w-4 h-4 text-[var(--brand)]" />
                    <span className="text-sm font-semibold text-[var(--text-primary)]">{(c.action_type ?? '').replace(/_/g, ' ')}</span>
                    {c.status && <StatusBadge status={c.status} />}
                    <span className="text-xs text-[var(--text-muted)]">{c.project_id}</span>
                  </div>
                  <div className="flex items-center gap-4 mt-2">
                    {[['Payload', c.payload_hash], ['Record', c.record_hash]].filter(([, v]) => v).map(([label, hash]) => (
                      <span key={label} className="flex items-center gap-1 text-[9px] text-[var(--text-muted)] font-mono">
                        <Hash className="w-3 h-3" /> {label}: {String(hash).slice(0, 16)}…
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>
      )}

      {tab === 'compliance' && d && (
        <Panel title={`Compliance — ${name}`} Icon={FileCheck}>
          <Empty>{d.note}</Empty>
        </Panel>
      )}
    </div>
  )
}
