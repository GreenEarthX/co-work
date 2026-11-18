// Screen: DEVEX Brief — all pre-FID spend (/finance/devex-brief: the owner's full brief, or the sections shared with the reader; /finance/devex-shared redirects here)
/**
 * One page a CFO can read and print: what is being spent before FID, on what,
 * funded by whom, how far each package has progressed, and the return the
 * spend is risked for.
 *
 *  - DEVEX here is ALL pre-FID spend: every development package in phases
 *    FEL 1, FEL 2 and FEED, whatever its type.
 *  - The brief is assembled by the backend (GET /api/v1/devex-brief/{id}) and
 *    this screen draws only the sections it is sent. The owner's finance and
 *    executives are sent everything. Anyone else (a bank, a DFI, an adviser,
 *    an associated company) is sent the sections the owner shared with that
 *    user for this project, read-only, and nothing otherwise. Access to
 *    Returns does not open this screen. Records that cannot be read give an
 *    error, never an empty brief.
 *  - The owner's finance or executive function shares and revokes sections in
 *    the panel at the foot of the page. Each share is audited and may expire.
 *  - The return case is the PF engine's, with its governance stamp, and is
 *    shown to the producer side only. Opened from the Returns screen it uses
 *    the inputs entered there; opened directly it uses ILLUSTRATIVE values.
 */
import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Lock, Printer, ShieldCheck } from 'lucide-react'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'
import { getAuthHeader } from '@/lib/authToken'
import {
  fetchReturns, fmtEur, fmtPct, hurdleLine, illustrativeInputs, preFidByYear, useDevexBrief,
  type DevexBriefData, type ReturnsAnswer, type ReturnsInputs,
} from './returnsModel'

const card = 'rounded border border-[var(--border)] bg-[var(--surface)]'
const th = 'px-2 py-1.5 text-left text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]'
const td = 'px-2 py-1.5 align-top text-[var(--text-primary)]'
const num = `${td} text-right font-mono`
const field = 'rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-sm text-[var(--text-primary)]'
const label = (s: string) => s.replace(/_/g, ' ')

function Tile({ label: l, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className={`${card} px-3 py-2.5`}>
      <div className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">{l}</div>
      <div className="mt-0.5 font-mono text-lg text-[var(--text-primary)]">{value}</div>
      {sub && <div className="text-xs text-[var(--text-secondary)]">{sub}</div>}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className={`${card} p-4`}>
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">{title}</h2>
      {children}
    </section>
  )
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { ...init, headers: { 'Content-Type': 'application/json', ...getAuthHeader() } })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const d = body?.detail
    throw new Error(typeof d === 'string' ? d : d?.reason ?? `The server answered ${res.status}.`)
  }
  return body as T
}

// ── Sharing (owner finance / executive only) ─────────────────────────────────

interface ShareRow {
  entitlement_id: string; user_id: string; section: string; granted_by: string
  granted_at: string; expires_at: string | null; status: string; reason: string | null
}

function SharesPanel({ projectId, labels }: { projectId: string; labels: Record<string, string> }) {
  const base = `/api/v1/devex-brief/${encodeURIComponent(projectId)}/shares`
  const shares = useQuery<{ shares: ShareRow[] }>({ queryKey: ['devex-shares', projectId], queryFn: () => api(base) })
  const [userId, setUserId] = useState('')
  const [picked, setPicked] = useState<string[]>([])
  const [expires, setExpires] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    setError(null)
    try {
      await action()
      await shares.refetch()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const share = () => run(async () => {
    await api(base, { method: 'POST', body: JSON.stringify({
      user_id: userId.trim(), sections: picked, expires_at: expires || null, reason: reason.trim() || null }) })
    setUserId(''); setPicked([]); setReason('')
  })
  const toggle = (s: string) => setPicked(p => (p.includes(s) ? p.filter(x => x !== s) : [...p, s]))
  const rows = shares.data?.shares ?? []

  return (
    <section className={`${card} p-4 print:hidden`}>
      <h2 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">Sharing</h2>
      <p className="mb-3 text-sm text-[var(--text-secondary)]">
        By default only your finance and executive functions see this brief. You may share selected sections,
        read-only, with a named user outside your company for this project: a bank, a DFI, an adviser or an
        associated company. No lender mandate is needed. Each section opens only itself, here and on the
        matching data screen: the totals do not open the package list or the spend wave. Every share and every
        read is audited. Revoking a share closes those paths at once; it cannot recall what was already seen.
      </p>

      {rows.length > 0 && (
        <table className="mb-3 w-full text-sm">
          <thead><tr>
            <th className={th}>User</th><th className={th}>Section</th><th className={th}>Shared by</th>
            <th className={th}>Expires</th><th className={th}>Status</th><th className={th} />
          </tr></thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.entitlement_id} className="border-t border-[var(--border)]">
                <td className={`${td} font-mono text-xs`}>{r.user_id}</td>
                <td className={td}>{label(r.section)}</td>
                <td className={`${td} text-xs`}>{r.granted_by} · {new Date(r.granted_at).toLocaleDateString('en-GB')}</td>
                <td className={`${td} text-xs`}>{r.expires_at ? new Date(r.expires_at).toLocaleDateString('en-GB') : 'no expiry'}</td>
                <td className={`${td} text-xs`}>{r.status}</td>
                <td className={`${td} text-right`}>
                  {r.status === 'active' && (
                    <button type="button" disabled={busy} className="text-xs text-red-700 hover:underline dark:text-red-300"
                      onClick={() => run(() => api(`${base}/${encodeURIComponent(r.entitlement_id)}`, { method: 'DELETE' }))}>
                      Revoke
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="grid gap-3 md:grid-cols-3">
        <label className="block text-xs text-[var(--text-secondary)]">
          User ID of the person
          <input type="text" className={`${field} mt-1 w-full`} value={userId} onChange={e => setUserId(e.target.value)} />
        </label>
        <label className="block text-xs text-[var(--text-secondary)]">
          Expires (optional)
          <input type="date" className={`${field} mt-1 w-full`} value={expires} onChange={e => setExpires(e.target.value)} />
        </label>
        <label className="block text-xs text-[var(--text-secondary)]">
          Reason (optional, kept in the audit record)
          <input type="text" className={`${field} mt-1 w-full`} value={reason} onChange={e => setReason(e.target.value)} />
        </label>
      </div>
      <div className="mt-3 space-y-1">
        {Object.entries(labels).map(([s, text]) => (
          <label key={s} className="flex items-center gap-2 text-sm text-[var(--text-primary)]">
            <input type="checkbox" checked={picked.includes(s)} onChange={() => toggle(s)} />
            <span className="font-mono text-xs">{s}</span>
            <span className="text-[var(--text-secondary)]">{text}</span>
          </label>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-3">
        <button type="button" onClick={share} disabled={busy || !userId.trim() || picked.length === 0}
          className="rounded bg-[var(--brand)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60">
          Share selected sections
        </button>
        {error && <span className="text-sm text-red-700 dark:text-red-300">{error}</span>}
        {shares.isError && <span className="text-sm text-red-700 dark:text-red-300">{(shares.error as Error).message}</span>}
      </div>
    </section>
  )
}

// ── The return case (producer side only) ─────────────────────────────────────

function ReturnCase({ brief, fci, passed }: { brief: DevexBriefData; fci: number; passed: ReturnsInputs | null }) {
  const preFid = preFidByYear(brief)
  const spendKey = preFid.eur.join(',')
  const [answer, setAnswer] = useState<ReturnsAnswer | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setAnswer(null)
    setError(null)
    if (fci <= 0) return
    fetchReturns(passed ?? illustrativeInputs(fci, preFid.eur))
      .then(a => { if (!cancelled) setAnswer(a) })
      .catch(e => { if (!cancelled) setError((e as Error).message) })
    return () => { cancelled = true }
  }, [brief.project_id, fci, spendKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const r = answer?.returns
  return (
    <Section title="The return this spend is risked for">
      <p className="mb-3 text-sm text-[var(--text-secondary)]">
        Pre-FID spend is equity at first loss. If the project does not reach FID it is not recovered.
      </p>
      {!r ? (
        <p className="text-sm text-[var(--text-secondary)]">
          {error ?? (fci > 0 ? 'Computing…' : 'No CAPEX is recorded for this project, so no return case can be computed. Enter the FCI on the Returns screen.')}
        </p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Tile label="FCI" value={fmtEur(r.fci_eur)}
              sub={r.first_operating_period > 1 ? 'Fixed Capital Investment, by construction year' : 'Fixed Capital Investment, in full at year 0'} />
            <Tile label="Total investment" value={fmtEur(r.total_investment_eur)} sub={`FCI + DEVEX ${fmtEur(r.devex_eur)}`} />
            <Tile label="DEVEX / equity invested" value={r.equity_invested_eur > 0 ? fmtPct(r.devex_eur / r.equity_invested_eur, 0) : '—'} sub={`equity invested ${fmtEur(r.equity_invested_eur)}`} />
            <Tile label="Payback" value={r.payback_years == null ? 'not reached' : `${r.payback_years.toFixed(1)} yr`} sub="project, from FID, undiscounted" />
            <Tile label="Unlevered IRR" value={fmtPct(r.unlevered_irr)} sub={hurdleLine(r.hurdle_test.unlevered)} />
            <Tile label="Levered IRR" value={fmtPct(r.levered_irr)} sub={hurdleLine(r.hurdle_test.levered)} />
            <Tile label="NPV, unlevered" value={fmtEur(r.npv_unlevered_eur)} sub={`at project hurdle ${fmtPct(r.hurdle.project_hurdle)}`} />
            <Tile label="ROI · ROE" value={`${fmtPct(r.roi_avg_annual)} · ${fmtPct(r.roe_avg_annual)}`} sub="average per year" />
          </div>
          <div className="mt-3 text-xs text-[var(--text-muted)]">
            {r.case === 'SCHEDULED' ? 'Scheduled case. ' : 'Screening case: FCI in full at year 0, no construction period. '}
            {passed ? 'Inputs as entered on the Returns screen.' : 'ILLUSTRATIVE inputs, not this project’s agreed terms.'}{' '}
            {answer?.governance && <>Governance: {answer.governance.basis} · inputs {answer.governance.input_sha}. </>}
            <Link to="/finance/returns" className="text-[var(--brand)] hover:underline print:hidden">Change the inputs</Link>
          </div>
        </>
      )}
    </Section>
  )
}

// ── The brief ────────────────────────────────────────────────────────────────

export function DevexBrief() {
  const { selectedProjectId } = useSelectedProject()
  const { projects } = useVisibleProjects()
  const project = projects.find(p => p.id === selectedProjectId)
  const passed = (useLocation().state as { inputs?: ReturnsInputs } | null)?.inputs ?? null
  const brief = useDevexBrief(selectedProjectId)

  if (!selectedProjectId || selectedProjectId === 'all') {
    return <div className="p-6 text-sm text-[var(--text-muted)]">Select a single project to see its DEVEX brief.</div>
  }
  if (brief.loading) return <div className="p-6 text-sm text-[var(--text-muted)]">Loading the DEVEX brief…</div>
  if (brief.denied) {
    return (
      <div className={`${card} mx-auto mt-6 flex max-w-xl items-start gap-2 p-4 text-sm text-[var(--text-secondary)]`}>
        <Lock className="mt-0.5 h-4 w-4 shrink-0" />
        <span>
          {brief.denied} Access to Returns and other finance screens does not include pre-FID data.
        </span>
      </div>
    )
  }
  if (brief.error || !brief.data) {
    return <div className="p-6 text-sm text-red-700 dark:text-red-300">{brief.error ?? 'The DEVEX brief could not be loaded.'}</div>
  }

  const d = brief.data
  const fci = passed?.fci_eur ?? project?.capex_eur ?? 0
  const phases = d.pre_fid_phases
  const s = d.summary
  const f = d.funding

  return (
    <div className="mx-auto max-w-6xl space-y-4 pb-8">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[var(--text-primary)]">DEVEX brief: pre-FID spend</h1>
          <p className="text-sm text-[var(--text-secondary)]">
            {d.project_name} · as of {new Date(d.as_of).toLocaleDateString('en-GB')} ·
            all development packages in phases {phases.map(label).join(', ')}
          </p>
        </div>
        <button type="button" onClick={() => window.print()}
          className="inline-flex items-center gap-2 rounded border border-[var(--border)] px-3 py-1.5 text-sm text-[var(--text-primary)] print:hidden">
          <Printer className="h-4 w-4" /> Print
        </button>
      </div>

      {d.read_only && (
        <div className={`${card} flex items-start gap-2 px-3 py-2 text-sm text-[var(--text-secondary)]`}>
          <Lock className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            Shared with you by the project&apos;s owner, read-only. You are shown {d.sections.map(label).join(', ').toLowerCase()};
            other sections of the brief are not shared. Each read is recorded.
          </span>
        </div>
      )}

      {s && (s.package_count === 0 ? (
        <div className={`${card} p-4 text-sm text-[var(--text-secondary)]`}>
          No pre-FID spend is recorded for this project.
          {!d.read_only && <> Add development packages in phases FEL 1, FEL 2 or FEED in the{' '}
            <Link to="/finance-package" className="text-[var(--brand)] hover:underline">package register</Link>.</>}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <Tile label="Pre-FID spend" value={fmtEur(s.pre_fid_spend_eur)} sub={`${s.package_count} packages`} />
          <Tile label="Share of FCI" value={fci > 0 ? fmtPct(s.pre_fid_spend_eur / fci) : '—'} sub={fci > 0 ? `FCI ${fmtEur(fci)}` : 'no CAPEX recorded'} />
          <Tile label="Drawn" value={fmtEur(s.drawn_eur)} sub={`${fmtEur(s.to_draw_eur)} still to draw`} />
          <Tile label="Evidenced" value={fmtPct(s.evidenced_share, 0)} sub="of spend, by package state" />
          <Tile label="FID-grade estimate" value={fmtPct(s.fid_grade_share, 0)} sub="of spend at AACE Class 3 or tighter" />
        </div>
      ))}

      {d.breakdown && d.breakdown.rows.length > 0 && (
        <Section title="Spend by type and phase">
          <table className="w-full text-sm">
            <thead><tr>
              <th className={th}>Type</th>
              {phases.map(ph => <th key={ph} className={`${th} text-right`}>{label(ph)}</th>)}
              <th className={`${th} text-right`}>Total</th>
            </tr></thead>
            <tbody>
              {d.breakdown.rows.map(row => (
                <tr key={row.package_type} className="border-t border-[var(--border)]">
                  <td className={td}>{label(row.package_type)}</td>
                  {phases.map(ph => <td key={ph} className={num}>{fmtEur(row.by_phase[ph] ?? 0)}</td>)}
                  <td className={num}>{fmtEur(row.total_eur)}</td>
                </tr>
              ))}
              <tr className="border-t border-[var(--border)] font-semibold">
                <td className={td}>Total</td>
                {phases.map(ph => <td key={ph} className={num}>{fmtEur(d.breakdown?.phase_totals[ph] ?? 0)}</td>)}
                <td className={num}>{fmtEur(d.breakdown.total_eur)}</td>
              </tr>
            </tbody>
          </table>
        </Section>
      )}

      {f !== undefined && (
        <Section title="Funding by year and capital layer">
          {!f ? (
            <p className="text-sm text-[var(--text-secondary)]">No spend wave is recorded for this project, so the funding of pre-FID spend by year cannot be shown.</p>
          ) : (
            <>
              <table className="w-full text-sm">
                <thead><tr>
                  <th className={th}>Year</th>
                  {f.layers.map(l => <th key={l} className={`${th} text-right`}>{label(l)}</th>)}
                  <th className={`${th} text-right`}>Total</th>
                </tr></thead>
                <tbody>
                  {f.years.map(y => (
                    <tr key={y.year} className="border-t border-[var(--border)]">
                      <td className={td}>{y.year}</td>
                      {f.layers.map(l => <td key={l} className={num}>{fmtEur(y.layers[l] ?? 0)}</td>)}
                      <td className={num}>{fmtEur(f.layers.reduce((sum, l) => sum + (y.layers[l] ?? 0), 0))}</td>
                    </tr>
                  ))}
                  <tr className="border-t border-[var(--border)] font-semibold">
                    <td className={td}>Total</td>
                    {f.layers.map(l => <td key={l} className={num}>{fmtEur(f.layer_totals_eur[l])}</td>)}
                    <td className={num}>{fmtEur(f.total_eur)}</td>
                  </tr>
                </tbody>
              </table>
              <div className="mt-2 space-y-1 text-xs">
                {f.drawn_before_fid.length > 0 ? (
                  <div className="flex items-center gap-1.5 text-red-700 dark:text-red-300">
                    <AlertTriangle className="h-3.5 w-3.5" /> {f.drawn_before_fid.map(label).join(', ')} is drawn before FID. Pre-FID spend should be carried by equity, grants or bridge.
                  </div>
                ) : (
                  <div className="flex items-center gap-1.5 text-[var(--text-secondary)]">
                    <ShieldCheck className="h-3.5 w-3.5" /> No senior or ECA debt is drawn before FID: equity absorbs first loss.
                  </div>
                )}
                {s && f.register_gap_eur != null && Math.abs(f.register_gap_eur) > 0.005 * s.pre_fid_spend_eur && (
                  <div className="flex items-center gap-1.5 text-amber-700 dark:text-amber-300">
                    <AlertTriangle className="h-3.5 w-3.5" /> The spend wave ({fmtEur(f.total_eur)}) and the package register ({fmtEur(s.pre_fid_spend_eur)}) differ by {fmtEur(Math.abs(f.register_gap_eur))}. Reconcile them before this brief is relied on.
                  </div>
                )}
                {f.verification_state && f.verification_state !== 'VERIFIED' && (
                  <div className="text-[var(--text-muted)]">Spend wave verification state: {f.verification_state}.</div>
                )}
              </div>
            </>
          )}
        </Section>
      )}

      {d.packages && d.packages.length > 0 && (
        <Section title="What the spend buys">
          <table className="w-full text-sm">
            <thead><tr>
              <th className={th}>Package</th><th className={th}>Type · phase</th>
              <th className={`${th} text-right`}>Cost</th><th className={th}>Estimate</th>
              <th className={th}>State</th><th className={th}>Funded by</th>
              <th className={th}>Risk removed</th><th className={th}>Unlocks</th>
            </tr></thead>
            <tbody>
              {d.packages.map(p => (
                <tr key={p.package_id} className="border-t border-[var(--border)]">
                  <td className={td}>{p.package_name}</td>
                  <td className={`${td} text-xs`}>{label(p.package_type)} · {label(p.phase_required)}</td>
                  <td className={num}>
                    {fmtEur(p.cost_amount)}
                    {p.cost_p10 != null && p.cost_p90 != null && (
                      <div className="text-[11px] text-[var(--text-muted)]">{fmtEur(p.cost_p10)} – {fmtEur(p.cost_p90)}</div>
                    )}
                  </td>
                  <td className={`${td} text-xs`}>{label(p.estimate_class)}</td>
                  <td className={`${td} text-xs`}>{p.workflow_state}</td>
                  <td className={`${td} text-xs`}>{(p.capital_eligible ?? []).map(label).join(', ') || '—'}</td>
                  <td className={`${td} text-xs`}>{(p.risk_removed ?? []).map(label).join(', ') || '—'}</td>
                  <td className={`${td} text-xs`}>
                    {[p.gex_gate, ...(p.unlock_condition ?? [])].filter(Boolean).join(' · ') || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      )}

      {!d.read_only && <ReturnCase brief={d} fci={fci} passed={passed} />}
      {d.can_manage_shares && <SharesPanel projectId={d.project_id} labels={d.section_labels} />}
    </div>
  )
}
