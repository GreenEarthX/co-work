// Screen: Gabillon parameters, GEX administrators (/gex-console/gabillon)
/**
 * What the Gabillon two-factor model runs on (JML, 20 Nov 2026), read only:
 *   · the parameters per molecule, as the PF engine holds them (GET /api/v1/pricing/params/{m});
 *   · the CEPCI forward rows (the Gabillon P-forward of the cost index) with their state.
 * Nothing is edited here. A CEPCI forward row is approved on the GEX console's
 * "Reference values awaiting approval"; a calibration is made on Pricing Curves (Gabillon).
 * Reads GET /api/v1/gex-console/gabillon (GEX staff only, 403 otherwise).
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { cisoCall } from '@/features/ciso/cisoApi'
import { foot, label, nf, statusLine, td, tdr, th, thr } from '@/lib/houseStyle'

/* eslint-disable @typescript-eslint/no-explicit-any */
const PARAMS: [string, string, string, number][] = [
  ['alpha', 'α, spot mean reversion', '1/yr', 2], ['mu_equilibrium_eur_t', 'e^μ, long-run level', 'unit', 0],
  ['sigma_s', 'σS, spot volatility', '1/√yr', 2], ['kappa', 'κ, convenience-yield reversion', '1/yr', 2],
  ['theta_0', 'θ0, convenience yield', '1/yr', 2], ['sigma_delta', 'σδ, convenience-yield volatility', '1/√yr', 2],
  ['rho', 'ρ, factor correlation', '', 2], ['season_a1', 'a1, seasonal', '', 2], ['season_a2', 'a2, seasonal', '', 2],
  ['learning_rate', 'Learning rate', '', 2], ['capex_floor_eur_t', 'Capex floor', 'unit', 0],
  ['regulatory_premium_base', 'Regulatory premium', 'unit', 0], ['n_observations', 'Market observations', 'n', 0],
]

export function GabillonParametersPage() {
  const [d, setD] = useState<any>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { cisoCall('/gex-console/gabillon').then(setD).catch(e => setErr(e.message)) }, [])
  if (err) return <div className="p-6 text-sm text-red-800" data-testid="gabillon-error">{err}</div>
  if (!d) return <div className="p-6 text-xs text-slate-500">Reading the PF engine…</div>
  const mols: any[] = d.molecules ?? []
  return (
    <div className="mx-auto max-w-[1400px] space-y-4 p-6" data-testid="gabillon-parameters">
      <div>
        <h1 className="text-base font-semibold text-slate-900">Gabillon parameters</h1>
        <div className={statusLine}>
          <span>PF engine</span><span>·</span><span>{mols.length} molecules</span><span>·</span>
          <span>{mols.filter(x => x.calibration_status === 'SEED').length} SEED</span><span>·</span>
          <span>{(d.cepci_forward ?? []).filter((r: any) => r.state === 'approved').length} CEPCI forward rows approved</span><span>·</span>
          <span>read only</span>
          <span className="ml-auto font-sans"><Link className="underline" to="/gex-console">GEX console</Link> · <Link className="underline" to="/ciso-pricing">Calibrate (Pricing Curves)</Link></span>
        </div>
      </div>
      {d.engine_error && <p className="text-xs text-red-800">The PF engine did not answer: {d.engine_error}</p>}
      <section>
        <div className={label}>Parameters by molecule</div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead><tr><th className={th}>Parameter</th><th className={th}>Unit</th>
              {mols.map(x => <th key={x.key} className={thr}>{x.label ?? x.key}</th>)}</tr></thead>
            <tbody>
              <tr><td className={td}>Standing</td><td className={td} />{mols.map(x => <td key={x.key} className={`${tdr} text-[10px]`}>{x.calibration_status}</td>)}</tr>
              <tr><td className={td}>Price unit</td><td className={td} />{mols.map(x => <td key={x.key} className={`${tdr} text-[10px]`}>{x.unit}</td>)}</tr>
              {PARAMS.map(([k, name, unit, dp]) => <tr key={k}><td className={td}>{name}</td><td className={td}>{unit === 'unit' ? 'price unit' : unit}</td>
                {mols.map(x => <td key={x.key} className={tdr}>{nf(x.params?.[k], dp)}</td>)}</tr>)}
              <tr><td className={td}>Last calibrated</td><td className={td} />{mols.map(x => <td key={x.key} className={tdr}>{x.params?.last_calibrated ?? '—'}</td>)}</tr>
            </tbody>
          </table>
        </div>
      </section>
      <section>
        <div className={label}>CEPCI forward · Gabillon P-forward of the cost index (reference registry)</div>
        <table className="w-full text-xs" data-testid="cepci-forward-rows">
          <thead><tr><th className={th}>Key</th><th className={thr}>5%</th><th className={thr}>Expected</th><th className={thr}>95%</th>
            <th className={th}>State</th><th className={th}>Proposed</th><th className={th}>Approved</th><th className={th}>Source</th><th className={th}>Row</th></tr></thead>
          <tbody>{(d.cepci_forward ?? []).map((r: any) => <tr key={r.ref_id}>
            <td className={td}>{r.parameter_key}</td><td className={tdr}>{nf(r.value_low, 1)}</td><td className={tdr}>{nf(r.value_base, 1)}</td><td className={tdr}>{nf(r.value_high, 1)}</td>
            <td className={`${td} font-mono text-[10px] uppercase`}>{r.state}</td>
            <td className={td}>{r.proposed_by} {String(r.proposed_at ?? '').slice(0, 10)}</td>
            <td className={td}>{r.approved_by ? `${r.approved_by} ${String(r.approved_at ?? '').slice(0, 10)}` : '—'}</td>
            <td className={td}>{r.source_name}</td><td className={`${td} font-mono`}>{String(r.ref_id).slice(0, 8)}</td></tr>)}</tbody>
        </table>
      </section>
      <ul className={`${foot} list-disc pl-4`}>{(d.notes ?? []).map((n: string) => <li key={n}>{n}</li>)}</ul>
    </div>
  )
}

export default GabillonParametersPage
