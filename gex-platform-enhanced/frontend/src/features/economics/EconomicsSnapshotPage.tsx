// Screen: Techno-Economic Assessment (/economics/:projectId)
//
// Increment 2 of docs/tea-report-scope.md. These figures have existed on :8002
// and in the claim ledger for months with no way to look at them.
//
// The screen shows the APPROVED base case or says why it cannot. It never
// renders a provisional figure — the backend refuses to send one, and this
// makes the refusal legible instead of an empty page. Every figure is stamped
// with the claim and the cost-basis hash that produced it, and the provisional
// disclaimer travels with them.
//
// Doctrine: slate-only, square corners, mono labels, colour = state.
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

import {
  fetchEconomicsSnapshot,
  type EconomicsSnapshot,
  type EconomicsSnapshotState,
  type GhgClaim,
} from '@/lib/economicsApi'

const eur = (v: number | null | undefined): string =>
  typeof v === 'number'
    ? new Intl.NumberFormat('en-GB', {
        style: 'currency', currency: 'EUR', maximumFractionDigits: 0,
      }).format(v)
    : '—'

function Label({ children }: { children: React.ReactNode }) {
  return (
    <div className="font-mono text-[10px] uppercase tracking-wider text-slate-500">
      {children}
    </div>
  )
}

function Figure({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="border border-slate-200 bg-white p-4">
      <Label>{label}</Label>
      <div className="mt-1 text-2xl font-semibold text-slate-900">{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
    </div>
  )
}

function GhgRow({ name, claim }: { name: string; claim?: GhgClaim | null }) {
  if (!claim) {
    return (
      <div className="flex items-baseline justify-between border-b border-slate-100 py-2">
        <span className="text-sm text-slate-700">{name}</span>
        <span className="text-xs text-slate-400">not computed</span>
      </div>
    )
  }
  return (
    <div className="flex items-baseline justify-between border-b border-slate-100 py-2">
      <span className="text-sm text-slate-700">
        {name}
        {claim.method && <span className="ml-2 text-xs text-slate-400">{claim.method}</span>}
      </span>
      {claim.approved ? (
        <span className="font-mono text-sm text-slate-900">
          {claim.value} {claim.unit}
        </span>
      ) : (
        // The claim's own approval rule, shown rather than silently dropped.
        <span className="font-mono text-xs uppercase text-amber-700">
          awaiting approval · {claim.state}
        </span>
      )}
    </div>
  )
}

function Approved({ data }: { data: EconomicsSnapshot }) {
  const { claim, basis, economics, lca, integrity, not_available: missing } = data
  return (
    <div className="space-y-6">
      <div className="border-l-2 border-amber-500 bg-amber-50 px-4 py-3">
        <Label>Provisional — ascertained: false</Label>
        <p className="mt-1 text-sm text-amber-900">{integrity.note}</p>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <Figure label="LCOP" value={economics.lcop != null ? `€ ${economics.lcop}` : '—'}
                sub={economics.lcop_basis} />
        <Figure label="CAPEX" value={eur(economics.capex_eur)} />
        <Figure label="OPEX / year" value={eur(economics.opex_eur_per_year)} />
      </div>

      <div className="border border-slate-200 bg-white p-4">
        <Label>Approved claim</Label>
        <dl className="mt-2 grid grid-cols-1 gap-x-8 gap-y-1 text-sm sm:grid-cols-2">
          <div className="flex justify-between gap-4">
            <dt className="text-slate-500">Approved by</dt>
            <dd className="text-slate-900">{claim.approved_by ?? '—'}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-slate-500">Claim</dt>
            <dd className="font-mono text-xs text-slate-900">{claim.claim_id}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-slate-500">Cost-basis hash</dt>
            <dd className="font-mono text-xs text-slate-900">{basis.cost_basis_hash}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-slate-500">Engine</dt>
            <dd className="text-slate-900">{basis.engine ?? '—'}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-slate-500">Nameplate</dt>
            <dd className="text-slate-900">
              {basis.nameplate_capacity ?? '—'} {basis.nameplate_unit ?? ''}
            </dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-slate-500">Pathway</dt>
            <dd className="text-slate-900">{claim.pathway_id ?? '—'}</dd>
          </div>
        </dl>
      </div>

      <div className="border border-slate-200 bg-white p-4">
        <Label>Lifecycle emissions</Label>
        <div className="mt-2">
          <GhgRow name="GHG intensity" claim={lca.g_co2e_per_mj} />
          <GhgRow name="GHG saving" claim={lca.ghg_saving} />
        </div>
        {lca.method_note && (
          <p className="mt-3 text-xs text-slate-500">{lca.method_note}</p>
        )}
      </div>

      <div className="border border-slate-200 bg-slate-50 p-4">
        <Label>Not shown, and why</Label>
        <ul className="mt-2 space-y-1 text-xs text-slate-600">
          {Object.entries(missing)
            .filter(([k]) => k !== 'why')
            .map(([k, reason]) => (
              <li key={k}>
                <span className="font-mono text-slate-700">{k}</span> — {reason}
              </li>
            ))}
        </ul>
        {missing.why && <p className="mt-2 text-xs text-slate-500">{missing.why}</p>}
      </div>
    </div>
  )
}

function Notice({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border border-slate-200 bg-white p-6">
      <Label>{title}</Label>
      <div className="mt-2 text-sm text-slate-700">{children}</div>
    </div>
  )
}

export default function EconomicsSnapshotPage() {
  const { projectId = '' } = useParams()
  const [state, setState] = useState<EconomicsSnapshotState | null>(null)

  useEffect(() => {
    let live = true
    setState(null)
    fetchEconomicsSnapshot(projectId).then((s) => { if (live) setState(s) })
    return () => { live = false }
  }, [projectId])

  return (
    <div className="mx-auto max-w-5xl p-6">
      <header className="mb-6">
        <Label>Techno-Economic Assessment</Label>
        <h1 className="mt-1 text-xl font-semibold text-slate-900">{projectId}</h1>
      </header>

      {state === null && <Notice title="Loading">Reading the approved base case…</Notice>}

      {state?.kind === 'approved' && <Approved data={state.data} />}

      {state?.kind === 'not-approved' && (
        <Notice title="Not approved">
          <p>{state.message}</p>
          <p className="mt-2 font-mono text-xs text-amber-700">
            claim {state.claimId ?? '—'} · state {state.state ?? 'unknown'}
          </p>
          <p className="mt-2 text-xs text-slate-500">
            Figures are withheld until IE/CFO approval: a provisional run is not the
            basis anyone should read as this project's economics.
          </p>
        </Notice>
      )}

      {state?.kind === 'none' && (
        <Notice title="Nothing computed">
          No base case exists for this project yet. Run a techno-economic assessment
          first; this screen shows the approved result, it does not compute one.
        </Notice>
      )}

      {state?.kind === 'forbidden' && (
        <Notice title="No access">
          You do not have a finance entitlement for this project.
        </Notice>
      )}

      {state?.kind === 'error' && (
        <Notice title="Unavailable">{state.message}</Notice>
      )}
    </div>
  )
}
