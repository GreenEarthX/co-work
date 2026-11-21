/**
 * The Cost Basis and TEA workbook on the calculation chain (19 Nov 2026).
 *
 *   Download   the template, filled from the latest saved cost basis (or blank)
 *   Upload     GEX previews: every entry ACCEPTED / CONVERTED / MISSING / CONFLICTING / UNSUPPORTED,
 *              what changes against the current version, the computed CAPEX and OPEX. Nothing is saved.
 *   Confirm    saves exactly the previewed file (its sha256) as the next cost basis version.
 *
 * Out of GEX: `downloadTeaWorkbook` gives one TEA run as a frozen workbook.
 */
import { useRef, useState } from 'react'
import { getAuthHeader } from '@/lib/authToken'

/* eslint-disable @typescript-eslint/no-explicit-any */
const button = 'rounded border border-[var(--border)] px-2 py-1 text-xs hover:bg-[var(--surface-hover,#f8fafc)] disabled:opacity-40'
const eur = (n: number | null | undefined) => n == null ? 'unknown' : `€${(n / 1e6).toLocaleString('en-GB', { maximumFractionDigits: 1 })}M`
const TONE: Record<string, string> = { ACCEPTED: 'text-emerald-800', CONVERTED: 'text-sky-800', MISSING: 'text-amber-800',
  CONFLICTING: 'text-red-800', UNSUPPORTED: 'text-red-800' }
const ORDER = ['CONFLICTING', 'UNSUPPORTED', 'MISSING', 'CONVERTED', 'ACCEPTED']

async function failure(res: Response): Promise<string> {
  const body = await res.json().catch(() => ({}))
  const d = body?.detail
  return typeof d === 'string' ? d : d?.message ?? `The server answered ${res.status}.`
}

export async function download(path: string, fallbackName: string) {
  const res = await fetch(path, { headers: { ...getAuthHeader() } })
  if (!res.ok) throw new Error(await failure(res))
  const name = /filename="([^"]+)"/.exec(res.headers.get('content-disposition') || '')?.[1] ?? fallbackName
  const url = URL.createObjectURL(await res.blob())
  const a = document.createElement('a')
  a.href = url; a.download = name; a.click()
  URL.revokeObjectURL(url)
}

export function downloadTeaWorkbook(projectId: string, claimId: string) {
  return download(`/api/v1/calculation-chain/${encodeURIComponent(projectId)}/tea/${encodeURIComponent(claimId)}/workbook`,
    `GEX_TEA_${claimId}.xlsx`)
}

async function upload(path: string, file: File, form: Record<string, string> = {}) {
  const fd = new FormData()
  fd.append('file', file)
  Object.entries(form).forEach(([k, v]) => fd.append(k, v))
  const res = await fetch(path, { method: 'POST', body: fd, headers: { ...getAuthHeader() } })
  if (!res.ok) throw new Error(await failure(res))
  return res.json()
}

/** Sources and uses of ONE financing case (core/funding.reconcile). Pipeline shown apart, never counted. */
export function FundingSummary({ f }: { f: any }) {
  if (!f) return null
  const m = (n: number | null | undefined) => n == null ? 'unknown' : `€${(n / 1e6).toLocaleString('en-GB', { maximumFractionDigits: 1 })}M`
  return (
    <div className="space-y-0.5 rounded border border-[var(--border)] p-2" data-testid="funding-summary">
      <div className="font-semibold">Sources and uses of this case</div>
      <div>Uses: {f.uses.map((u: any) => `${u.kind.toLowerCase().replace('_', ' ')}${u.component ? ` (${u.component})` : ''} ${m(u.amount_eur)}${u.origin && u.origin !== 'STATED' ? ` [${u.origin}]` : ''}`).join(' · ')}</div>
      <div className="font-semibold">Total project cost {f.total_is_floor ? 'at least ' : ''}{m(f.total_uses_eur)}
        {f.unknown_uses.length > 0 && <span className="font-normal text-amber-900"> · unknown: {f.unknown_uses.join(', ')}</span>}</div>
      {f.openpytea_working_capital_eur != null && <div className="text-[var(--text-muted)]">OpenPyTEA's own working capital (0.15 × fixed capital): {m(f.openpytea_working_capital_eur)}, shown, not added.</div>}
      <div>Cash received {m(f.received_eur)} · binding and available to draw {m(f.binding_available_eur)} ·{' '}
        <span className="font-semibold">remaining funding need {f.total_is_floor ? 'at least ' : ''}{m(f.remaining_need_eur)}</span></div>
      {f.conditional.length > 0 && <div>Conditional, not counted: {f.conditional.map((c: any) => `${c.name} ${m(c.amount_eur)} (${c.conditions ?? 'conditions not stated'})`).join(' · ')}</div>}
      {f.uncommitted.length > 0 && <div>Indicative or unclassified, not counted: {f.uncommitted.map((c: any) => `${c.name} ${m(c.amount_eur)}`).join(' · ')}</div>}
      {f.pipeline.length > 0 && <div className="text-[var(--text-muted)]">Pipeline, outside this plan: {f.pipeline.map((c: any) => `${c.name} ${m(c.amount_eur)}`).join(' · ')} (total {m(f.pipeline_total_eur)})</div>}
      {f.gearing.map((g: any) => <div key={g.by}>Gearing {(g.ratio * 100).toFixed(1)}% ({g.basis}) vs {(g.threshold * 100).toFixed(0)}% set by {g.by}: <span className="font-semibold">{g.result}</span> · {g.standing}</div>)}
      {f.notes.map((n: string) => <div key={n} className="text-[var(--text-muted)]">{n}</div>)}
    </div>
  )
}

const TAB_NAMES: Record<string, string> = { cost_basis: 'Cost Basis + TEA inputs', financing: 'Financing', offtake: 'Offtake' }
const TAB_WHO: Record<string, string> = { cost_basis: 'engineering, finance or executive', financing: 'finance or executive',
  offtake: 'commercial, finance or executive' }

function TabPreview({ name, t, busy, onSave }: { name: string; t: any; busy: boolean; onSave: () => void }) {
  if (!t.provided) return <div className="text-[var(--text-muted)]" data-testid={`tab-${name}`}>{TAB_NAMES[name]}: left empty, nothing to save.</div>
  const rows: any[] = [...t.report].sort((a, b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status))
  const problems = rows.filter(r => r.status !== 'ACCEPTED')
  const v = t.versus_current
  const unchanged = t.unchanged || v?.unchanged
  const res = t.result_preview
  return (
    <div className="space-y-1 border-t border-[var(--border)] pt-2" data-testid={`tab-${name}`}>
      <div className="flex flex-wrap items-baseline gap-3">
        <span className="font-semibold">{TAB_NAMES[name]}</span>
        {ORDER.map(s => <span key={s} className={TONE[s]}>{s} {t.summary[s]}</span>)}
        <span className="font-semibold">{t.summary.blocking ? `${t.summary.blocking} blocking` : unchanged ? 'no change' : 'nothing blocks'}{t.summary.open_issues ? ` · ${t.summary.open_issues} open issue(s), kept on the draft` : ''}</span>
      </div>
      {v && <div>{v.current_version == null ? 'This would be cost basis v1.' : v.unchanged
        ? `Identical to cost basis v${v.current_version}.`
        : `Against cost basis v${v.current_version}: ${v.changes.length} change(s) — ${v.changes.map((c: any) => c.field).join(', ')}`}</div>}
      {t.would_save_as && <div>Would be saved as <span className="font-semibold">{t.would_save_as}</span>
        {t.would_save_as === 'DRAFT' && name === 'cost_basis' && ': no TEA runs from it until a version without open issues is saved'}
        {t.would_save_as === 'DRAFT' && name === 'financing' && ': it feeds no returns until promoted on an independently reviewed TEA run'}</div>}
      {(t.limitations || []).length > 0 && <ul className="ml-4 list-disc text-amber-900">{t.limitations.map((l: any) => <li key={l.code}>{l.detail}</li>)}</ul>}
      {res && <div>Computed: CAPEX {eur(res.capex.total_capex_eur)} (contingency included) · OPEX {eur(res.opex.total_annual_opex_eur)}/yr
        {!res.opex.opex_complete && <span className="text-amber-800"> · incomplete: {[
          res.opex.annual_om_eur == null && `O&M unknown on ${res.opex.om_unknown_lines.join(', ')}`,
          res.opex.annual_insurance_eur == null && 'insurance unknown'].filter(Boolean).join('; ')} (left out, not zero)</span>}</div>}
      {t.case_preview && <div>Case on {t.tea_claim_id}: fixed capital {eur(t.case_preview.fci_eur)} · debt {eur(t.case_preview.debt_eur)} · {(t.case_preview.interest_rate * 100).toFixed(2)}% · {t.case_preview.debt_tenor_years} yr · grants {eur(t.case_preview.grant_eur)}</div>}
      {(t.capital_sources || []).length > 0 && <div>Capital stack (kept as declared, beside the case): {t.capital_sources.map((c: any) => `${c.name} ${eur(c.amount_eur)} ${c.status ?? ''}`).join(' · ')}</div>}
      {t.funding && <FundingSummary f={t.funding} />}
      {t.card && <div>{t.frame ? `A frame of ${t.card.buyers.length} buyers` : 'A single-counterparty offtake card'}: each counterparty confirms its own terms before the gate engine uses them.</div>}
      {(t.external || []).length > 0 && <div>External results kept as attributed assessments, beside GEX's own: {t.external.map((x: any) => `${x.metric} ${x.value} (${x.author}, ${x.model_and_date})`).join(' · ')}</div>}
      {problems.length > 0 && (
        <table className="w-full"><tbody>{problems.map((r, i) => (
          <tr key={i} className="border-t border-[var(--border)] align-top">
            <td className={`pr-2 font-semibold ${TONE[r.status]}`}>{r.status}{r.blocking ? ' ●' : r.issue ? ' ◐' : ''}</td>
            <td className="pr-2 font-mono">{r.field}</td><td className="pr-2 text-[var(--text-muted)]">{r.where}</td><td>{r.detail}</td>
          </tr>))}</tbody></table>)}
      <details><summary className="cursor-pointer">All {rows.length} entries</summary>
        <ul className="ml-4">{rows.map((r, i) => <li key={i}><span className={TONE[r.status]}>{r.status}</span> <span className="font-mono">{r.field}</span>{r.value != null ? ` = ${r.value}` : ''} {r.detail}</li>)}</ul>
      </details>
      <button type="button" className={button} disabled={busy || !t.can_commit || unchanged} onClick={onSave}>
        Save {TAB_NAMES[name]}</button>
      <span className="ml-2 text-[var(--text-muted)]">saved by the {TAB_WHO[name]} function{!t.can_commit && !unchanged ? ' · fix the entries marked ● and upload again' : ''}</span>
    </div>
  )
}

export function CostWorkbook({ projectId, onSaved }: { projectId: string; onSaved: (msg: string) => void }) {
  const P = encodeURIComponent(projectId)
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function run(fn: () => Promise<void>) {
    setBusy(true); setError(null)
    try { await fn() } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  const reread = (f: File) => run(async () => setPreview(await upload(`/api/v1/cost-basis/${P}/workbook/preview`, f)))
  const pick = (f: File | undefined) => {
    if (!f) return
    setFile(f); setPreview(null)
    reread(f)
  }
  const save = (tab: string) => run(async () => {
    const saved = await upload(`/api/v1/cost-basis/${P}/workbook/commit`, file!, { expected_file_sha256: preview.file_sha256, tab })
    onSaved(tab === 'cost_basis' ? `Cost basis v${saved.version_number} saved from the workbook.`
      : tab === 'financing' ? `Financing case v${saved.version_number} saved from the workbook.`
        : `Offtake card saved from the workbook. ${saved.note ?? ''}`)
    setPreview(await upload(`/api/v1/cost-basis/${P}/workbook/preview`, file!))
  })

  return (
    <div className="space-y-2 rounded border border-[var(--border)] p-2 text-xs" data-testid="cost-workbook">
      <div className="font-semibold">Spreadsheet: Cost Basis, TEA inputs, Financing and Offtake in one Excel workbook</div>
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={button} disabled={busy}
          onClick={() => run(() => download(`/api/v1/cost-basis/${P}/workbook/template`, 'GEX_workbook.xlsx'))}>
          Download workbook (filled from what GEX holds)</button>
        <button type="button" className={button} disabled={busy}
          onClick={() => run(() => download(`/api/v1/cost-basis/${P}/workbook/template?blank=true`, 'GEX_workbook_blank.xlsx'))}>
          Blank template</button>
        <label className={button}>Upload a filled workbook…
          <input ref={input} type="file" aria-label="Upload workbook" className="hidden"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            onChange={e => pick(e.target.files?.[0])} /></label>
        {busy && <span>Working…</span>}
      </div>
      {error && <div role="alert" className="text-red-800">{error}</div>}
      {preview && (
        <div className="space-y-2" data-testid="workbook-preview">
          <div className="font-semibold">Preview of {file?.name}: nothing is saved until you save a tab</div>
          {['cost_basis', 'financing', 'offtake'].map(k => <TabPreview key={k} name={k} t={preview.tabs[k]} busy={busy} onSave={() => save(k)} />)}
          <button type="button" className={button} disabled={busy} onClick={() => { setPreview(null); setFile(null); if (input.current) input.current.value = '' }}>Close the preview</button>
        </div>
      )}
    </div>
  )
}
