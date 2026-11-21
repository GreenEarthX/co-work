// Screen: TEA parameters, GEX administrators (/gex-console/tea-parameters)
/**
 * What the TEA engine prices with (JML, 20 Nov 2026), read only, in three kinds:
 *   · PUBLISHED: OpenPyTEA's cost correlations (pinned literature constants, never edited),
 *     with the fingerprint each run records and the category names OpenPyTEA has retired;
 *   · GEX's equipment train (tea_equipment_spec, four eyes in the database);
 *   · TEA reference values (reference registry: FX benchmark, LCOP band, CO2 price, …).
 * Nothing is edited here: reference values are approved on the GEX console.
 * Reads GET /api/v1/gex-console/tea-parameters (GEX staff only, 403 otherwise).
 */
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { cisoCall } from '@/features/ciso/cisoApi'
import { foot, label, nf, statusLine, td, tdr, th, thr } from '@/lib/houseStyle'

/* eslint-disable @typescript-eslint/no-explicit-any */
export function TeaParametersPage() {
  const [d, setD] = useState<any>(null)
  const [err, setErr] = useState<string | null>(null)
  const [q, setQ] = useState('')
  const [cat, setCat] = useState('')
  useEffect(() => { cisoCall('/gex-console/tea-parameters').then(setD).catch(e => setErr(e.message)) }, [])
  const rows: any[] = useMemo(() => d?.engine?.correlations ?? [], [d])
  const cats = useMemo(() => [...new Set(rows.map(r => r.category))].sort(), [rows])
  const shown = rows.filter(r => (!cat || r.category === cat)
    && (!q || `${r.key} ${r.type} ${r.source}`.toLowerCase().includes(q.toLowerCase())))
  if (err) return <div className="p-6 text-sm text-red-800" data-testid="tea-parameters-error">{err}</div>
  if (!d) return <div className="p-6 text-xs text-slate-500">Reading the TEA engine…</div>
  const fp = d.engine?.fingerprint ?? {}
  const renamed = Object.entries(d.engine?.renamed_categories ?? {}) as [string, string][]
  return (
    <div className="mx-auto max-w-[1400px] space-y-4 p-6" data-testid="tea-parameters">
      <div>
        <h1 className="text-base font-semibold text-slate-900">TEA parameters</h1>
        <div className={statusLine}>
          <span>OpenPyTEA {fp.openpytea_version ?? '—'}</span><span>·</span>
          <span>{fp.correlations ?? '—'} correlations</span><span>·</span>
          <span>CEPCI {fp.cepci_year_range?.join('–') ?? '—'}</span><span>·</span>
          <span data-testid="set-hash">{fp.hash ?? '—'}</span><span>·</span><span>read only</span>
          <span className="ml-auto font-sans"><Link className="underline" to="/gex-console">GEX console</Link> · <Link className="underline" to="/gex-console/gabillon">Gabillon parameters</Link></span>
        </div>
      </div>
      {d.engine_error && <p className="text-xs text-red-800">{d.engine_error}</p>}

      <section>
        <div className={label}>TEA reference values · reference registry</div>
        <table className="w-full text-xs" data-testid="tea-reference">
          <thead><tr><th className={th}>Key</th><th className={th}>Pathway / region</th><th className={thr}>Low</th><th className={thr}>Base</th><th className={thr}>High</th>
            <th className={th}>Unit</th><th className={th}>State</th><th className={th}>Approved</th><th className={th}>Source</th></tr></thead>
          <tbody>{(d.reference ?? []).map((r: any) => <tr key={r.ref_id}>
            <td className={td}>{r.parameter_key}</td><td className={td}>{[r.pathway, r.region].filter(Boolean).join(' · ') || '—'}</td>
            <td className={tdr}>{nf(r.value_low, 4)}</td><td className={tdr}>{nf(r.value_base, 4)}</td><td className={tdr}>{nf(r.value_high, 4)}</td>
            <td className={td}>{r.unit}{r.currency ? ` ${r.currency}` : ''}</td>
            <td className={`${td} font-mono text-[10px] uppercase`}>{r.state}</td>
            <td className={td}>{r.approved_by ? `${r.approved_by} ${String(r.approved_at ?? '').slice(0, 10)}` : '—'}</td>
            <td className={td}>{r.source_name}</td></tr>)}</tbody>
        </table>
      </section>

      <section>
        <div className={label}>GEX equipment train · tea_equipment_spec (four eyes, enforced in the database)</div>
        <table className="w-full text-xs" data-testid="equipment-spec">
          <thead><tr><th className={th}>Fuel</th><th className={th}>Role</th><th className={th}>Category</th><th className={th}>Type</th><th className={th}>Material</th>
            <th className={thr}>Size at reference</th><th className={th}>Unit</th><th className={thr}>Scale exp.</th><th className={th}>State</th><th className={th}>Proposed / approved</th></tr></thead>
          <tbody>{(d.equipment_spec ?? []).map((r: any) => <tr key={r.spec_id}>
            <td className={td}>{r.fuel_id}</td><td className={td}>{r.role}</td><td className={td}>{r.category}</td><td className={td}>{r.equipment_type}</td>
            <td className={td}>{r.material}</td><td className={tdr}>{nf(r.base_param, 1)}</td><td className={td}>{r.base_param_unit}</td>
            <td className={tdr}>{nf(r.scale_exp, 2)}</td><td className={`${td} font-mono text-[10px] uppercase`}>{r.state}</td>
            <td className={td}>{r.proposed_by} / {r.approved_by ?? '—'}</td></tr>)}</tbody>
        </table>
      </section>

      <section>
        <div className={label}>Correlation sets the platform has seen · tea_correlation_set</div>
        <table className="w-full text-xs" data-testid="correlation-sets">
          <thead><tr><th className={th}>Set</th><th className={th}>OpenPyTEA</th><th className={thr}>Correlations</th><th className={th}>CEPCI</th>
            <th className={th}>State</th><th className={th}>First seen</th><th className={th}>Reviewed</th></tr></thead>
          <tbody>{(d.correlation_sets_seen ?? []).map((r: any) => <tr key={r.set_hash}>
            <td className={`${td} font-mono`}>{r.set_hash}{r.set_hash === fp.hash ? ' (running)' : ''}</td><td className={td}>{r.openpytea_version}</td>
            <td className={tdr}>{nf(r.correlations)}</td><td className={td}>{r.cepci_year_min}–{r.cepci_year_max}</td>
            <td className={`${td} font-mono text-[10px] uppercase`}>{r.state}</td><td className={td}>{String(r.first_seen_at ?? '').slice(0, 10)}</td>
            <td className={td}>{r.reviewed_by ? `${r.reviewed_by} ${String(r.reviewed_at ?? '').slice(0, 10)}` : '—'}</td></tr>)}</tbody>
        </table>
        <p className={foot}>A set is recorded the first time a run is priced on it. A set not yet reviewed is flagged on every run it prices.</p>
      </section>

      <section>
        <div className={label}>Published cost correlations · {shown.length} of {rows.length}</div>
        <div className="mb-1 flex gap-2 text-xs">
          <input aria-label="Search correlations" placeholder="key, type or source" value={q} onChange={e => setQ(e.target.value)}
            className="w-64 border border-slate-300 px-1 py-0.5" />
          <select aria-label="Category" value={cat} onChange={e => setCat(e.target.value)} className="border border-slate-300 px-1 py-0.5">
            <option value="">All categories</option>{cats.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div className="max-h-[480px] overflow-auto">
          <table className="w-full text-xs" data-testid="correlations">
            <thead className="sticky top-0 bg-[var(--surface)]"><tr><th className={th}>Key</th><th className={th}>Category</th><th className={th}>Type</th>
              <th className={th}>Size parameter</th><th className={thr}>Range</th><th className={thr}>Cost year</th><th className={th}>Form</th><th className={th}>Source</th></tr></thead>
            <tbody>{shown.map(r => <tr key={r.key}>
              <td className={`${td} font-mono text-[10px]`}>{r.key}</td><td className={td}>{r.category}</td><td className={td}>{r.type}</td>
              <td className={td}>{r.units}</td><td className={tdr}>{r.s_lower ?? '—'} – {r.s_upper ?? '—'}</td><td className={tdr}>{r.cost_year}</td>
              <td className={td}>{r.form}</td><td className={td}>{r.source}</td></tr>)}</tbody>
          </table>
        </div>
        {renamed.length > 0 && <p className={foot} data-testid="renamed-categories">Retired category names, translated by the engine and listed on each run that uses one: {renamed.map(([o, n]) => `“${o}” → “${n}”`).join('; ')}.</p>}
        <p className={foot}>{d.engine?.note}</p>
      </section>
    </div>
  )
}

export default TeaParametersPage
