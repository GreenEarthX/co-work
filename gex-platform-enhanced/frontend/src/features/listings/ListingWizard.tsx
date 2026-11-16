// Screen: List supply (/listings/new?project=…)
/**
 * The listing wizard (discovery Phase 1, R8). One guided path from a project to an open listing,
 * replacing the loop Capacity → Marketplace → Tokenisation → Capacity (review F15, F17):
 *
 *   1 Source       pick the project's capacity, or declare one
 *   2 Product      pick an available token, or mint one; optionally record carbon intensity,
 *                  quality and certificates (each says what it is: claimed or submitted)
 *   3 Terms        volume, price, delivery basis, minimum parcel, validity, firm or indicative
 *   4 Preview      exactly what an anonymous member will see (the market's own summary), then
 *                  save as a draft or publish
 *
 * Each step's result is a record as soon as it is made, so a wizard left half-way resumes: the
 * capacity and the token are offered again next time. Who may do each step is the server's rule
 * (core/market_policy, D-B), read through useMarketPolicy: a step the server would refuse is not
 * offered, and says who does it instead.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { capacitiesAPI, offersAPI, productsAPI, tokensAPI, type ListingProduct } from '@/api'
import { useUserRole } from '@/contexts/UserRoleContext'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'
import { useMarketPolicy } from '@/lib/marketPolicy'
import { CarbonCell, EvidenceCell, ProductCell } from '@/features/trader/ListingParts'

interface Capacity {
  id: string; project_id: string; molecule: string; capacity_mtpd: number; location?: string | null
  production_start?: string | null; production_end?: string | null; status?: string
}
interface Draft {
  id: string; token_id: string; capacity_project_id?: string; listing_state: string; volume_mtpd: number
  price_eur_kg: number; delivery_start: string; delivery_end: string
}
interface Token {
  id: string; capacity_id: string; tokenised_mtpd: number; delivery_start: string; delivery_end: string
  lifecycle_state: string; production_pathway?: string | null; physical_form?: string | null
  specification_standard?: string | null
}

// The typed delivery clause's vocabulary (backend trading_book/clauses.INCOTERMS, C_TERMS).
export const INCOTERMS = ['EXW', 'FCA', 'CPT', 'CIP', 'DAP', 'DPU', 'DDP', 'FAS', 'FOB', 'CFR', 'CIF']
export const C_TERMS = ['CPT', 'CIP', 'CFR', 'CIF']
const FORMS = [['gas', 'Gas'], ['compressed_gas', 'Compressed gas'], ['liquid', 'Liquid'], ['liquefied_gas', 'Liquefied gas']]
const STEPS = ['Source', 'Product & evidence', 'Commercial terms', 'Preview & publish']

const input = 'w-full rounded-md border border-gray-300 px-3 py-2 text-sm'
const primary = 'rounded-md bg-gray-900 px-4 py-2 text-sm font-semibold text-white hover:bg-gray-800 disabled:opacity-40'
const secondary = 'rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-semibold text-gray-800 hover:bg-gray-50 disabled:opacity-40'

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-gray-700">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-gray-500">{hint}</span>}
    </label>
  )
}

function Refusal({ who }: { who: string }) {
  return <p className="rounded-md bg-gray-50 p-3 text-sm text-gray-600">{who}</p>
}

export interface Terms {
  volume_mtpd: string; price_eur_kg: string; price_basis: string; delivery_start: string; delivery_end: string
  incoterm: string; named_place: string; shipment_point: string; min_parcel_t: string; valid_until: string
  offer_type: 'firm' | 'indicative'
}

/** The offer the API receives, from the terms as typed (exported for the tests). */
export function buildOffer(tokenId: string, t: Terms, publish: boolean) {
  const offer: Record<string, unknown> = {
    token_id: tokenId, volume_mtpd: Number(t.volume_mtpd), price_eur_kg: Number(t.price_eur_kg),
    delivery_start: t.delivery_start, delivery_end: t.delivery_end, offer_type: t.offer_type,
    listing_state: publish ? 'OPEN' : 'DRAFT',
  }
  if (t.price_basis) offer.price_basis = t.price_basis
  if (t.incoterm) {
    offer.incoterm = t.incoterm
    if (t.named_place.trim()) offer.named_place = t.named_place.trim()
    if (C_TERMS.includes(t.incoterm) && t.shipment_point.trim()) offer.shipment_point = t.shipment_point.trim()
  }
  if (t.min_parcel_t) offer.min_order_kg = Number(t.min_parcel_t) * 1000
  if (t.valid_until) offer.valid_until = t.valid_until
  return offer
}

/** Why these terms cannot be sent yet (empty: they can). The server checks again. */
export function termsProblems(t: Terms, token?: Token): string[] {
  const out: string[] = []
  const v = Number(t.volume_mtpd), p = Number(t.price_eur_kg)
  if (!(v > 0)) out.push('State the volume.')
  else if (token && v > token.tokenised_mtpd) out.push(`The token holds ${token.tokenised_mtpd} MTPD; offer at most that.`)
  if (!(p > 0)) out.push('State the price.')
  if (!t.delivery_start || !t.delivery_end || t.delivery_end < t.delivery_start) out.push('State the delivery window.')
  else if (token && (t.delivery_start < token.delivery_start || t.delivery_end > token.delivery_end))
    out.push(`The token runs ${token.delivery_start} to ${token.delivery_end}; deliver inside it.`)
  if (t.incoterm && !t.named_place.trim()) out.push(`Name the place for ${t.incoterm}.`)
  if (C_TERMS.includes(t.incoterm) && !t.shipment_point.trim()) out.push(`${t.incoterm} needs the point of shipment (where risk passes).`)
  if (t.valid_until && t.delivery_end && t.valid_until > t.delivery_end) out.push('The offer cannot stay valid after its delivery window ends.')
  return out
}

export default function ListingWizard() {
  const [params] = useSearchParams()
  const { role } = useUserRole()
  const { projects, isLoading } = useVisibleProjects()
  const policy = useMarketPolicy()
  const owned = useMemo(() => projects.filter(p => p.owner_company === role.company_name), [projects, role.company_name])

  const [step, setStep] = useState(0)
  const [projectId, setProjectId] = useState(params.get('project') ?? '')
  const project = owned.find(p => p.id === projectId)
  const [capacities, setCapacities] = useState<Capacity[]>([])
  const [capacityId, setCapacityId] = useState('')
  const [tokens, setTokens] = useState<Token[]>([])
  const [tokenId, setTokenId] = useState('')
  const [preview, setPreview] = useState<ListingProduct | null>(null)
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState<{ state: string } | null>(null)
  // One key per record a form creates: a double click replays the first, never makes two.
  const keys = useRef({ capacity: crypto.randomUUID(), token: crypto.randomUUID(), offer: crypto.randomUUID() })

  const capacity = capacities.find(c => c.id === capacityId)
  const token = tokens.find(t => t.id === tokenId)

  useEffect(() => { if (!projectId && owned.length === 1) setProjectId(owned[0].id) }, [owned, projectId])
  const loadDrafts = () => offersAPI.list({ listing_state: 'DRAFT' })
    .then(r => setDrafts((r.offers ?? []).filter((o: Draft) => o.capacity_project_id === projectId)))
    .catch(() => setDrafts([]))
  useEffect(() => {
    setCapacities([]); setCapacityId(''); setDrafts([])
    if (!projectId) return
    capacitiesAPI.list({ project_id: projectId }).then(r => setCapacities(r.capacities ?? [])).catch(() => setCapacities([]))
    loadDrafts()
  }, [projectId])   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    setTokens([]); setTokenId('')
    if (!capacityId) return
    tokensAPI.list({ capacity_id: capacityId })
      .then(r => setTokens((r.tokens ?? []).filter((t: Token) => t.lifecycle_state === 'MINTED'
                                                    && !drafts.some(d => d.token_id === t.id))))
      .catch(() => setTokens([]))
  }, [capacityId, drafts])
  const refreshPreview = (id = tokenId) => {
    if (!id) { setPreview(null); return }
    productsAPI.listingPreview(id).then(r => setPreview(r.product)).catch(() => setPreview(null))
  }
  useEffect(() => { refreshPreview() }, [tokenId])   // eslint-disable-line react-hooks/exhaustive-deps

  async function act<T>(f: () => Promise<T>): Promise<T | undefined> {
    setBusy(true); setError('')
    try { return await f() } catch (e) { setError(e instanceof Error ? e.message : String(e)); return undefined }
    finally { setBusy(false) }
  }

  // ── step 1: capacity ───────────────────────────────────────────────────────
  const [cap, setCap] = useState({ capacity_mtpd: '', production_start: '', production_end: '', location: '' })
  async function declareCapacity() {
    if (!project) return
    const c = await act(() => capacitiesAPI.create({
      project_id: project.id, project_name: project.name, molecule: project.molecule,
      capacity_mtpd: Number(cap.capacity_mtpd), production_start: cap.production_start || undefined,
      production_end: cap.production_end || undefined, location: cap.location || undefined,
    }, keys.current.capacity))
    if (c) { setCapacities(cs => [c, ...cs]); setCapacityId(c.id); keys.current.capacity = crypto.randomUUID() }
  }

  // ── step 2: token and evidence ─────────────────────────────────────────────
  const [mint, setMint] = useState({ tokenised_mtpd: '', delivery_start: '', delivery_end: '', production_pathway: '',
                                     physical_form: '', specification_standard: '' })
  useEffect(() => {
    if (capacity) setMint(m => ({ ...m, delivery_start: m.delivery_start || capacity.production_start || '',
                                  delivery_end: m.delivery_end || capacity.production_end || '' }))
  }, [capacity])
  async function mintToken() {
    const t = await act(() => tokensAPI.create({
      capacity_id: capacityId, tokenised_mtpd: Number(mint.tokenised_mtpd), delivery_start: mint.delivery_start,
      delivery_end: mint.delivery_end, production_pathway: mint.production_pathway || undefined,
      physical_form: mint.physical_form || undefined, specification_standard: mint.specification_standard || undefined,
    }, keys.current.token))
    if (t) {
      const row: Token = { ...mint, ...t, tokenised_mtpd: Number(t.tokenised_mtpd ?? mint.tokenised_mtpd), lifecycle_state: 'MINTED' }
      setTokens(ts => [row, ...ts]); setTokenId(row.id); keys.current.token = crypto.randomUUID()
    }
  }
  const [ci, setCi] = useState({ value_gco2e_mj: '', method: '', system_boundary: '', calculation_date: '', basis: 'calculated' })
  const [q, setQ] = useState({ parameter: '', value: '', basis: 'declared' })
  const [cert, setCert] = useState({ scheme: '', body: '', reference: '', scope: 'site', valid_from: '', valid_until: '' })
  const [parameters, setParameters] = useState<{ parameter: string; unit: string; label: string }[]>([])
  useEffect(() => { if (step === 1) productsAPI.parameters().then(r => setParameters(r.parameters)).catch(() => {}) }, [step])
  async function record(f: () => Promise<unknown>, reset: () => void) {
    if ((await act(f)) !== undefined) { reset(); refreshPreview() }
  }

  // ── step 3: terms ──────────────────────────────────────────────────────────
  const [terms, setTerms] = useState<Terms>({ volume_mtpd: '', price_eur_kg: '', price_basis: 'FIXED', delivery_start: '',
    delivery_end: '', incoterm: '', named_place: '', shipment_point: '', min_parcel_t: '', valid_until: '', offer_type: 'firm' })
  useEffect(() => {
    if (token) setTerms(t => ({ ...t, volume_mtpd: String(token.tokenised_mtpd), delivery_start: token.delivery_start,
                                delivery_end: token.delivery_end }))
  }, [tokenId])   // eslint-disable-line react-hooks/exhaustive-deps
  const problems = termsProblems(terms, token)
  const set = (k: keyof Terms) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setTerms(t => ({ ...t, [k]: e.target.value }))

  async function moveDraft(id: string, to: 'OPEN' | 'WITHDRAWN') {
    if (await act(() => offersAPI.transition(id, to))) { if (to === 'OPEN') setDone({ state: 'OPEN' }); else loadDrafts() }
  }

  async function submit(publish: boolean) {
    const r = await act(() => offersAPI.create(buildOffer(tokenId, terms, publish), keys.current.offer))
    if (r) setDone({ state: publish ? 'OPEN' : 'DRAFT' })
  }

  // ── gates ──────────────────────────────────────────────────────────────────
  if (!policy.ready || isLoading) return <div className="p-6 text-sm text-gray-500">Loading…</div>
  if (!policy.can('listing.create')) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <h1 className="mb-3 text-xl font-bold text-gray-900">List supply</h1>
        <Refusal who="Supply is listed by your company's Commercial function. Your role can read the market (Market Discovery) but not list on it." />
      </div>
    )
  }
  if (done) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <h1 className="mb-3 text-xl font-bold text-gray-900">{done.state === 'OPEN' ? 'Listing published' : 'Draft saved'}</h1>
        <p className="mb-4 text-sm text-gray-700">
          {done.state === 'OPEN'
            ? 'Members now see it on Market Discovery, without your company, project or site. The token\'s volume is reserved for it.'
            : 'Nothing is shown to the market yet. Come back to List supply and publish it from the project\'s saved drafts.'}
        </p>
        <div className="flex gap-3">
          <Link className={primary} to="/market-discovery?side=supply">Open Market Discovery</Link>
          <Link className={secondary} to="/capacity">Capacity & Logistics</Link>
        </div>
      </div>
    )
  }

  const canNext = [!!capacityId, !!tokenId, problems.length === 0][step] ?? false

  return (
    <div className="mx-auto max-w-4xl p-6">
      <h1 className="mb-1 text-xl font-bold text-gray-900">List supply</h1>
      <p className="mb-5 text-sm text-gray-600">Four steps. Each one is saved as you go, so you can stop and come back.</p>

      <ol className="mb-6 flex flex-wrap gap-2" aria-label="Steps">
        {STEPS.map((s, i) => (
          <li key={s} aria-current={i === step ? 'step' : undefined}
              className={`rounded-full px-3 py-1 text-xs font-semibold ${i === step ? 'bg-gray-900 text-white'
                : i < step ? 'bg-emerald-50 text-emerald-800' : 'bg-gray-100 text-gray-500'}`}>
            {i + 1}. {s}
          </li>
        ))}
      </ol>

      {error && <p role="alert" className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p>}

      {step === 0 && (
        <section className="space-y-5">
          {owned.length === 0 ? (
            <Refusal who="Your company owns no project yet. A listing starts from a project you own." />
          ) : (
            <Field label="Project">
              <select className={input} value={projectId} onChange={e => setProjectId(e.target.value)} aria-label="Project">
                <option value="">Choose a project</option>
                {owned.map(p => <option key={p.id} value={p.id}>{p.name} · {p.molecule}</option>)}
              </select>
            </Field>
          )}
          {project && drafts.length > 0 && (
            <fieldset className="rounded-md border border-amber-200 bg-amber-50/40 p-4">
              <legend className="px-1 text-sm font-semibold text-gray-800">Saved drafts</legend>
              {drafts.map(d => (
                <div key={d.id} className="mb-1 flex flex-wrap items-center gap-3 text-sm">
                  <span>{d.volume_mtpd} MTPD · €{d.price_eur_kg}/kg · {d.delivery_start} to {d.delivery_end}</span>
                  {policy.can('listing.open') &&
                    <button className={primary} disabled={busy} onClick={() => moveDraft(d.id, 'OPEN')}>Publish</button>}
                  {policy.can('listing.withdraw') &&
                    <button className={secondary} disabled={busy} onClick={() => moveDraft(d.id, 'WITHDRAWN')}>Withdraw</button>}
                </div>
              ))}
            </fieldset>
          )}
          {project && (
            <>
              <fieldset>
                <legend className="mb-2 text-sm font-semibold text-gray-800">Production capacity</legend>
                {capacities.length === 0 && <p className="text-sm text-gray-500">No capacity declared for this project yet.</p>}
                {capacities.map(c => (
                  <label key={c.id} className="mb-1 flex items-center gap-2 text-sm">
                    <input type="radio" name="capacity" checked={capacityId === c.id} onChange={() => setCapacityId(c.id)} />
                    {c.molecule} · {c.capacity_mtpd} MTPD{c.production_start ? ` · ${c.production_start} to ${c.production_end ?? '…'}` : ''}
                  </label>
                ))}
              </fieldset>
              {policy.can('capacity.create') ? (
                <fieldset className="rounded-md border border-gray-200 p-4">
                  <legend className="px-1 text-sm font-semibold text-gray-800">Declare a capacity</legend>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="Capacity (MTPD)"><input className={input} type="number" min="0" value={cap.capacity_mtpd}
                      onChange={e => setCap({ ...cap, capacity_mtpd: e.target.value })} /></Field>
                    <Field label="Location" hint="Not shown to buyers."><input className={input} value={cap.location}
                      onChange={e => setCap({ ...cap, location: e.target.value })} /></Field>
                    <Field label="Production start"><input className={input} type="date" value={cap.production_start}
                      onChange={e => setCap({ ...cap, production_start: e.target.value })} /></Field>
                    <Field label="Production end"><input className={input} type="date" value={cap.production_end}
                      onChange={e => setCap({ ...cap, production_end: e.target.value })} /></Field>
                  </div>
                  <button className={`${secondary} mt-3`} disabled={busy || !(Number(cap.capacity_mtpd) > 0)} onClick={declareCapacity}>
                    Declare capacity
                  </button>
                </fieldset>
              ) : (
                <Refusal who="Capacity is declared by Commercial or Operations." />
              )}
            </>
          )}
        </section>
      )}

      {step === 1 && (
        <section className="space-y-5">
          <fieldset>
            <legend className="mb-2 text-sm font-semibold text-gray-800">Production token</legend>
            {tokens.length === 0 && <p className="text-sm text-gray-500">No available token on this capacity.</p>}
            {tokens.map(t => (
              <label key={t.id} className="mb-1 flex items-center gap-2 text-sm">
                <input type="radio" name="token" checked={tokenId === t.id} onChange={() => setTokenId(t.id)} />
                {t.tokenised_mtpd} MTPD · {t.delivery_start} to {t.delivery_end}
                {t.production_pathway ? ` · ${t.production_pathway}` : ''}
              </label>
            ))}
          </fieldset>
          {policy.can('token.mint') && (
            <fieldset className="rounded-md border border-gray-200 p-4">
              <legend className="px-1 text-sm font-semibold text-gray-800">Mint a token</legend>
              <p className="mb-3 text-xs text-gray-500">A token is a rate over a window, inside the capacity. It is unverified when minted.</p>
              <div className="grid gap-3 sm:grid-cols-3">
                <Field label="Rate (MTPD)"><input className={input} type="number" min="0" value={mint.tokenised_mtpd}
                  onChange={e => setMint({ ...mint, tokenised_mtpd: e.target.value })} /></Field>
                <Field label="From"><input className={input} type="date" value={mint.delivery_start}
                  onChange={e => setMint({ ...mint, delivery_start: e.target.value })} /></Field>
                <Field label="To"><input className={input} type="date" value={mint.delivery_end}
                  onChange={e => setMint({ ...mint, delivery_end: e.target.value })} /></Field>
                <Field label="Production pathway"><input className={input} value={mint.production_pathway} placeholder="e.g. PEM electrolysis + DAC synthesis"
                  onChange={e => setMint({ ...mint, production_pathway: e.target.value })} /></Field>
                <Field label="Physical form">
                  <select className={input} value={mint.physical_form} onChange={e => setMint({ ...mint, physical_form: e.target.value })}>
                    <option value="">Not stated</option>
                    {FORMS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </Field>
                <Field label="Specification standard"><input className={input} value={mint.specification_standard} placeholder="e.g. IMPCA, ISO 14687"
                  onChange={e => setMint({ ...mint, specification_standard: e.target.value })} /></Field>
              </div>
              <button className={`${secondary} mt-3`} onClick={mintToken}
                      disabled={busy || !(Number(mint.tokenised_mtpd) > 0) || !mint.delivery_start || !mint.delivery_end}>
                Mint token
              </button>
            </fieldset>
          )}

          {tokenId && (policy.can('product.declare') ? (
            <fieldset className="space-y-4 rounded-md border border-gray-200 p-4">
              <legend className="px-1 text-sm font-semibold text-gray-800">Evidence (optional)</legend>
              <p className="text-xs text-gray-500">
                Recorded as you state it. Buyers see each claim with its status: a certificate without a document on file
                reads <em>Claimed</em>. Only an appointed independent reviewer can mark one <em>Verified</em>.
              </p>
              <div className="grid gap-3 sm:grid-cols-5">
                <Field label="Carbon intensity (gCO₂e/MJ)"><input className={input} type="number" min="0" value={ci.value_gco2e_mj}
                  onChange={e => setCi({ ...ci, value_gco2e_mj: e.target.value })} /></Field>
                <Field label="Method"><input className={input} value={ci.method} placeholder="e.g. DA 2023/1185"
                  onChange={e => setCi({ ...ci, method: e.target.value })} /></Field>
                <Field label="System boundary"><input className={input} value={ci.system_boundary} placeholder="e.g. WtW"
                  onChange={e => setCi({ ...ci, system_boundary: e.target.value })} /></Field>
                <Field label="Calculated on"><input className={input} type="date" value={ci.calculation_date}
                  onChange={e => setCi({ ...ci, calculation_date: e.target.value })} /></Field>
                <Field label="Basis">
                  <select className={input} value={ci.basis} onChange={e => setCi({ ...ci, basis: e.target.value })}>
                    <option value="estimate">Estimate</option><option value="calculated">Calculated</option><option value="measured">Measured</option>
                  </select>
                </Field>
              </div>
              <button className={secondary} disabled={busy || ci.value_gco2e_mj === '' || !ci.method || !ci.system_boundary || !ci.calculation_date}
                onClick={() => record(() => productsAPI.addCarbonIntensity(tokenId, { ...ci, value_gco2e_mj: Number(ci.value_gco2e_mj) }),
                                      () => setCi({ ...ci, value_gco2e_mj: '' }))}>
                Record carbon intensity
              </button>

              <div className="grid gap-3 sm:grid-cols-3">
                <Field label="Quality parameter">
                  <select className={input} value={q.parameter} onChange={e => setQ({ ...q, parameter: e.target.value })}>
                    <option value="">Choose</option>
                    {parameters.map(p => <option key={p.parameter} value={p.parameter}>{p.label} ({p.unit})</option>)}
                  </select>
                </Field>
                <Field label="Value"><input className={input} type="number" value={q.value} onChange={e => setQ({ ...q, value: e.target.value })} /></Field>
                <Field label="Quality basis">
                  <select className={input} value={q.basis} onChange={e => setQ({ ...q, basis: e.target.value })}>
                    <option value="declared">Declared</option><option value="measured">Measured</option>
                  </select>
                </Field>
              </div>
              <button className={secondary} disabled={busy || !q.parameter || q.value === ''}
                onClick={() => record(() => productsAPI.addQuality(tokenId, { ...q, value: Number(q.value) }),
                                      () => setQ({ ...q, parameter: '', value: '' }))}>
                Record quality value
              </button>

              <div className="grid gap-3 sm:grid-cols-3">
                <Field label="Certificate scheme"><input className={input} value={cert.scheme} placeholder="e.g. ISCC EU, CertifHy"
                  onChange={e => setCert({ ...cert, scheme: e.target.value })} /></Field>
                <Field label="Issuing body"><input className={input} value={cert.body} onChange={e => setCert({ ...cert, body: e.target.value })} /></Field>
                <Field label="Reference" hint="Not shown to buyers."><input className={input} value={cert.reference}
                  onChange={e => setCert({ ...cert, reference: e.target.value })} /></Field>
                <Field label="Covers">
                  <select className={input} value={cert.scope} onChange={e => setCert({ ...cert, scope: e.target.value })}>
                    <option value="organisation">The organisation</option><option value="site">The site</option>
                    <option value="batch">This quantity (this token)</option>
                  </select>
                </Field>
                <Field label="Valid from"><input className={input} type="date" value={cert.valid_from}
                  onChange={e => setCert({ ...cert, valid_from: e.target.value })} /></Field>
                <Field label="Valid until"><input className={input} type="date" value={cert.valid_until}
                  onChange={e => setCert({ ...cert, valid_until: e.target.value })} /></Field>
              </div>
              <button className={secondary} disabled={busy || !cert.scheme || !cert.body || !cert.reference || !cert.valid_from}
                onClick={() => record(() => productsAPI.submitCertificate({
                  project_id: projectId, kind: 'certificate', scheme: cert.scheme, body: cert.body, reference: cert.reference,
                  scope: cert.scope, valid_from: cert.valid_from, valid_until: cert.valid_until || undefined,
                  covers: cert.scope === 'batch' ? [{ token_id: tokenId }] : undefined,
                }), () => setCert({ ...cert, scheme: '', body: '', reference: '' }))}>
                Record certificate
              </button>
            </fieldset>
          ) : <Refusal who="Evidence is recorded by Commercial, Operations, Engineering or Compliance." />)}
        </section>
      )}

      {step === 2 && (
        <section className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Volume (MTPD)" hint={token ? `Up to ${token.tokenised_mtpd} MTPD; the rest stays available.` : undefined}>
              <input className={input} type="number" min="0" value={terms.volume_mtpd} onChange={set('volume_mtpd')} /></Field>
            <Field label="Price (€/kg)" hint={Number(terms.price_eur_kg) > 0 ? `= € ${(Number(terms.price_eur_kg) * 1000).toLocaleString()} per tonne` : undefined}>
              <input className={input} type="number" min="0" step="0.01" value={terms.price_eur_kg} onChange={set('price_eur_kg')} /></Field>
            <Field label="Price basis">
              <select className={input} value={terms.price_basis} onChange={set('price_basis')}>
                <option value="FIXED">Fixed</option><option value="INDEX_LINKED">Index-linked</option>
              </select>
            </Field>
            <Field label="Delivery from"><input className={input} type="date" value={terms.delivery_start} onChange={set('delivery_start')} /></Field>
            <Field label="Delivery to"><input className={input} type="date" value={terms.delivery_end} onChange={set('delivery_end')} /></Field>
            <Field label="Minimum parcel (t)" hint="Optional."><input className={input} type="number" min="0" value={terms.min_parcel_t} onChange={set('min_parcel_t')} /></Field>
            <Field label="Incoterm" hint="Where risk passes to the buyer.">
              <select className={input} value={terms.incoterm} onChange={set('incoterm')}>
                <option value="">Not stated</option>
                {INCOTERMS.map(i => <option key={i} value={i}>{i}</option>)}
              </select>
            </Field>
            {terms.incoterm && <Field label="Named place"><input className={input} value={terms.named_place} placeholder="e.g. Rotterdam" onChange={set('named_place')} /></Field>}
            {C_TERMS.includes(terms.incoterm) && (
              <Field label="Point of shipment"><input className={input} value={terms.shipment_point} onChange={set('shipment_point')} /></Field>)}
            <Field label="Valid until" hint="Optional; at most the end of delivery."><input className={input} type="date" value={terms.valid_until} onChange={set('valid_until')} /></Field>
          </div>
          <fieldset>
            <legend className="mb-1 text-sm font-semibold text-gray-800">Offer type</legend>
            <label className="mr-6 text-sm"><input type="radio" name="offer_type" checked={terms.offer_type === 'firm'}
              onChange={() => setTerms({ ...terms, offer_type: 'firm' })} /> Firm: a buyer who accepts has a deal at these terms</label>
            <label className="text-sm"><input type="radio" name="offer_type" checked={terms.offer_type === 'indicative'}
              onChange={() => setTerms({ ...terms, offer_type: 'indicative' })} /> Indicative: an invitation to negotiate</label>
          </fieldset>
          {problems.length > 0 && <ul className="list-disc pl-5 text-sm text-amber-800">{problems.map(p => <li key={p}>{p}</li>)}</ul>}
        </section>
      )}

      {step === 3 && (
        <section className="space-y-4">
          <p className="text-sm text-gray-700">This is what members see on Market Discovery. Your company, project, site and certificate references are not shown.</p>
          <div className="overflow-x-auto rounded-md border border-gray-200">
            <table className="w-full text-left text-sm">
              <thead className="bg-gray-50 text-xs uppercase text-gray-500"><tr>
                {['Molecule', 'Product', 'Carbon intensity', 'Evidence', 'Volume', 'Price', 'Delivery', 'Window', 'Offer'].map(h =>
                  <th key={h} className="px-3 py-2">{h}</th>)}
              </tr></thead>
              <tbody><tr className="border-t border-gray-100" data-testid="preview-row">
                <td className="px-3 py-2">{capacity?.molecule}</td>
                <td className="px-3 py-2"><ProductCell product={preview ?? undefined} /></td>
                <td className="px-3 py-2"><CarbonCell product={preview ?? undefined} /></td>
                <td className="px-3 py-2"><EvidenceCell product={preview ?? undefined} /></td>
                <td className="px-3 py-2">{terms.volume_mtpd} MTPD</td>
                <td className="px-3 py-2">€{terms.price_eur_kg}/kg</td>
                <td className="px-3 py-2">{terms.incoterm ? `${terms.incoterm} ${terms.named_place}`.trim() : 'not stated'}</td>
                <td className="px-3 py-2">{terms.delivery_start} to {terms.delivery_end}</td>
                <td className="px-3 py-2">{terms.offer_type === 'firm' ? 'Firm' : 'Indicative'}{terms.valid_until ? ` · valid to ${terms.valid_until}` : ''}</td>
              </tr></tbody>
            </table>
          </div>
          <div className="flex gap-3">
            <button className={secondary} disabled={busy} onClick={() => submit(false)}>Save as draft</button>
            {policy.can('listing.open')
              ? <button className={primary} disabled={busy} onClick={() => submit(true)}>Publish listing</button>
              : <span className="self-center text-xs text-gray-500">Publishing is done by Commercial.</span>}
          </div>
        </section>
      )}

      <div className="mt-8 flex justify-between border-t border-gray-100 pt-4">
        <button className={secondary} disabled={step === 0 || busy} onClick={() => setStep(s => s - 1)}>Back</button>
        {step < 3 && <button className={primary} disabled={!canNext || busy} onClick={() => setStep(s => s + 1)}>Continue</button>}
      </div>
    </div>
  )
}
