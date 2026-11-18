// Screen parts: how a listing's product, evidence and counterparty, and an RFQ's requirements,
// read on Market Discovery (Phase 1, decision D-C). Labels live here once.
import type { ListingProduct, RfqRequirements } from '@/api';

// The canonical evidence states (backend app/core/vocabulary.py), in the words a person reads.
const EVIDENCE: Record<string, { label: string; cls: string }> = {
  asserted: { label: 'Claimed', cls: 'bg-gray-100 text-gray-700' },
  submitted: { label: 'Submitted', cls: 'bg-amber-50 text-amber-800' },
  verified: { label: 'Verified', cls: 'bg-emerald-50 text-emerald-800' },
  expired: { label: 'Expired', cls: 'bg-red-50 text-red-700' },
  rejected: { label: 'Rejected', cls: 'bg-red-50 text-red-700' },
};
const BASIS: Record<string, string> = {
  estimate: 'estimate', calculated: 'calculated', measured: 'measured', declared: 'declared',
  declared_at_mint: 'stated at mint',
};
const FORM: Record<string, string> = {
  gas: 'gas', compressed_gas: 'compressed gas', liquid: 'liquid', liquefied_gas: 'liquefied gas',
};

export function EvidenceChip({ status, children }: { status: string; children?: React.ReactNode }) {
  const e = EVIDENCE[status] ?? { label: status, cls: 'bg-gray-100 text-gray-700' };
  return (
    <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-semibold ${e.cls}`}>
      {children}{children ? ' · ' : ''}{e.label}
    </span>
  );
}

export function ProductCell({ product }: { product?: ListingProduct }) {
  if (!product || !Object.keys(product).length) return <span className="text-gray-400">not described</span>;
  const id = [product.production_pathway, product.physical_form && FORM[product.physical_form],
    product.specification_standard].filter(Boolean).join(' · ');
  return <span className="text-xs text-gray-700">{id || <span className="text-gray-400">not described</span>}</span>;
}

export function CarbonCell({ product, fallback }: { product?: ListingProduct; fallback?: number | null }) {
  const ci = product?.carbon_intensity;
  if (ci) return <span>{ci.value_gco2e_mj} gCO₂e/MJ <span className="text-xs text-gray-500">({BASIS[ci.basis] ?? ci.basis})</span></span>;
  if (fallback != null) return <span>{fallback} gCO₂e/MJ <span className="text-xs text-gray-500">(no basis)</span></span>;
  return <span className="text-gray-400">—</span>;
}

export function EvidenceCell({ product }: { product?: ListingProduct }) {
  const certs = product?.certificates ?? [];
  if (!certs.length) return <span className="text-xs text-gray-400">no certificate recorded</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {certs.map((c) => (
        <span key={`${c.kind}-${c.scheme}-${c.scope}`}
              title={`${c.body}: ${c.covers}. ${c.valid_from ? `Valid ${c.valid_from} to ${c.valid_until ?? 'no end date'}` : 'No validity dates recorded'}`}>
          <EvidenceChip status={c.status}>{c.scheme}{c.scope === 'batch' ? '' : ` (${c.scope})`}</EvidenceChip>
        </span>
      ))}
    </span>
  );
}

export function CounterpartyBadge({ role, vetting }: { role?: string | null; vetting?: string | null }) {
  const r = role === 'PRODUCER' ? 'Producer' : role === 'OFFTAKER' ? 'Offtaker' : role ? 'Member' : 'Member';
  return (
    <span className="text-xs">
      {r} · {vetting === 'vetted'
        ? <span className="font-semibold text-emerald-700">vetted</span>
        : <span className="text-gray-500">not yet vetted</span>}
    </span>
  );
}

const REQ_LABEL: Record<string, (r: RfqRequirements) => string> = {
  max_ci_gco2e_mj: (r) => `CI ≤ ${r.max_ci_gco2e_mj} gCO₂e/MJ${r.ci_min_basis ? ` (${r.ci_min_basis} or better)` : ''}`,
  regimes: (r) => (r.regimes ?? []).join(', '),
  accepted_schemes: (r) => `schemes: ${(r.accepted_schemes ?? []).join(', ')}`,
  min_evidence_state: (r) => `evidence ${r.min_evidence_state === 'verified' ? 'verified' : 'submitted or better'}`,
  physical_form: (r) => FORM[r.physical_form ?? ''] ?? r.physical_form ?? '',
  quality_limits: (r) => Object.entries(r.quality_limits ?? {}).map(([p, l]) =>
    `${p.replace(/_/g, ' ')}${l.min != null ? ` ≥ ${l.min}` : ''}${l.max != null ? ` ≤ ${l.max}` : ''}`).join('; '),
  incoterms: (r) => `${(r.incoterms ?? []).join('/')}${r.named_place ? ` ${r.named_place}` : ''}`,
  delivery_country: (r) => `to ${r.delivery_country}`,
};

export function RequirementsCell({ req }: { req?: RfqRequirements }) {
  const keys = Object.keys(REQ_LABEL).filter((k) => req && k in req)
  if (!req || !keys.length) return <span className="text-xs text-gray-400">no product requirement stated</span>;
  const mandatory = new Set(req.mandatory ?? []);
  return (
    <span className="flex flex-wrap gap-1">
      {keys.map((k) => (
        <span key={k} className={`rounded px-1.5 py-0.5 text-[11px] ${mandatory.has(k)
          ? 'bg-gray-900 font-semibold text-white' : 'bg-gray-100 text-gray-700'}`}
              title={mandatory.has(k) ? 'Required: a listing that fails this is not eligible' : 'Preferred'}>
          {REQ_LABEL[k](req)}{mandatory.has(k) ? ' · required' : ''}
        </span>
      ))}
    </span>
  );
}
