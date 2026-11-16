// Screen: Market Discovery (/market-discovery)
// Every open listing and open RFQ on the platform, anonymised: no company,
// project, token or location (JML, 2026-10-23). A company sees its own rows
// flagged "yours". Matching is bilateral (spec decision 2B): a company proposes
// one of its own RFQs to a listing, or one of its own listings to an RFQ; the
// match binds only when both accept, on the RFQ Management desk. GEX pairs no
// one automatically. Replaces a placeholder (gap register G-04).
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Search } from 'lucide-react';
import { marketAPI, type Commodity, type MarketRFQ, type OfferListing, type RFQListing } from '@/api';
import { useMarketPolicy } from '@/lib/marketPolicy';
import { CarbonCell, CounterpartyBadge, EvidenceCell, ProductCell, RequirementsCell } from './ListingParts';
import { EnquiryForm } from '@/features/deals/EnquiryForm';

// The section a Purchase or Sales button named. An outline, because .gex-card's shadow overrides a ring.
const LANDED = { outline: '2px solid var(--brand, #059669)', outlineOffset: '2px' };
const eur = (v: number | null | undefined) => (v == null ? '—' : `€${v.toFixed(2)}/kg`);

export function MarketDiscoveryPage() {
  // D-B: binding proposals are made by Commercial (backend core/market_policy).
  const { can } = useMarketPolicy();
  // ?side=supply|demand&molecule=… — set by the Purchase and Sales buttons (lib/marketLinks).
  const [params, setParams] = useSearchParams();
  const side = params.get('side');
  const [molecule, setMoleculeState] = useState(params.get('molecule') ?? '');
  const [unknownMolecule, setUnknownMolecule] = useState<string | null>(null);
  const supplyRef = useRef<HTMLElement>(null);
  const demandRef = useRef<HTMLElement>(null);
  const setMolecule = (m: string) => {
    setMoleculeState(m);
    setUnknownMolecule(null);
    const next = new URLSearchParams(params);
    if (m) next.set('molecule', m); else next.delete('molecule');
    setParams(next, { replace: true });
  };
  const [offers, setOffers] = useState<OfferListing[]>([]);
  const [rfqs, setRfqs] = useState<RFQListing[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [myRfqs, setMyRfqs] = useState<MarketRFQ[]>([]);
  const [deliveryTerms, setDeliveryTerms] = useState('');
  const [paymentTerms, setPaymentTerms] = useState('');
  const [choice, setChoice] = useState<Record<string, string>>({});
  const [commodities, setCommodities] = useState<Commodity[]>([]);
  // R9: the row being asked about (a non-binding enquiry), if any.
  const [asking, setAsking] = useState<{ kind: 'listing' | 'rfq'; id: string; label: string; molecule: string } | null>(null);

  useEffect(() => {   // tb_commodity in PostgreSQL — no molecule list in code
    marketAPI.commodities().then(({ commodities }) => {
      setCommodities(commodities);
      // A molecule the market does not trade (e.g. a project's own code) would show an empty,
      // misleading list: show every listing instead and say why.
      const asked = params.get('molecule');
      if (asked && !commodities.some((c) => c.market_molecule === asked)) {
        setMoleculeState('');
        setUnknownMolecule(asked);
      }
    }).catch((e) => setError((e as Error).message));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {   // land on the side the button named
    const target = side === 'demand' ? demandRef.current : side === 'supply' ? supplyRef.current : null;
    target?.scrollIntoView?.({ block: 'start' });
  }, [side]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [o, r] = await Promise.all([
        marketAPI.offerListings(molecule || undefined),
        marketAPI.rfqListings(molecule || undefined),
      ]);
      setOffers(o.offers);
      setRfqs(r.rfqs);
      setMyRfqs((await marketAPI.myRFQs()).rfqs.filter((x) => x.status === 'open'));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [molecule]);

  useEffect(() => { load(); }, [load]);

  // My open items that could answer a counterpart row: same molecule.
  const myListingsFor = (molecule: string) => offers.filter((o) => o.mine && o.molecule === molecule);
  const myRfqsFor = (molecule: string) => myRfqs.filter((r) => r.molecule === molecule);

  const propose = async (offerId: string, rfqId: string) => {
    try {
      await marketAPI.proposeMatch(offerId, rfqId, {
        delivery_terms: deliveryTerms.trim() || undefined, payment_terms: paymentTerms.trim() || undefined });
      setNotice('Match proposed — it binds only when both parties accept, on the RFQ Management desk. '
        + 'The contract is made from exactly these terms.');
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  // R9 (D-D): a non-binding question before any proposal; contact only by the other side's consent.
  const Ask = ({ kind, id, molecule, label }: { kind: 'listing' | 'rfq'; id: string; molecule: string; label: string }) =>
    can('enquiry.send') ? (
      <button onClick={() => setAsking({ kind, id, label, molecule })}
              className="rounded border px-2 py-0.5 text-xs font-semibold hover:bg-gray-50">Ask (non-binding)</button>
    ) : null;

  const Propose = ({ rowId, options, pair }: {
    rowId: string; options: { id: string; label: string }[]; pair: (mine: string) => [string, string];
  }) => {
    if (options.length === 0 || !can('proposal.create')) return null;
    const picked = choice[rowId] ?? options[0].id;
    return (
      <span className="inline-flex items-center gap-1">
        {options.length > 1 && (
          <select aria-label="Which of yours" value={picked} className="rounded border px-1 py-0.5 text-xs"
                  onChange={(e) => setChoice({ ...choice, [rowId]: e.target.value })}>
            {options.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
          </select>
        )}
        <button onClick={() => propose(...pair(picked))}
                className="rounded bg-gray-900 px-2 py-0.5 text-xs font-semibold text-white">
          Propose a match
        </button>
      </span>
    );
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6 p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black text-[var(--text-primary)]">Market Discovery</h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Open listings and requests across the platform. Counterparties stay anonymous until a match
            exists. Propose one of yours to a counterpart; it binds only when both of you accept.
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          {can('listing.create') && <Link to="/listings/new"
            className="rounded-md bg-gray-900 px-3 py-2 text-xs font-semibold text-white hover:bg-gray-800">List supply</Link>}
          {can('rfq.create') && <Link to="/rfqs"
            className="rounded-md border px-3 py-2 text-xs font-semibold hover:bg-gray-50">Raise an RFQ</Link>}
        </div>
      </div>

      {can('proposal.create') && <div className="flex flex-wrap items-center gap-2 rounded-lg border p-3 text-xs">
        <span className="font-semibold text-[var(--text-primary)]">Terms you propose with a match:</span>
        <input aria-label="Delivery terms" placeholder="Delivery terms (e.g. FOB Rotterdam, monthly)"
               value={deliveryTerms} onChange={(e) => setDeliveryTerms(e.target.value)}
               className="min-w-[16rem] flex-1 rounded border px-2 py-1" />
        <input aria-label="Payment terms" placeholder="Payment terms (e.g. 30 days from invoice)"
               value={paymentTerms} onChange={(e) => setPaymentTerms(e.target.value)}
               className="min-w-[16rem] flex-1 rounded border px-2 py-1" />
        <span className="text-[var(--text-secondary)]">
          Both parties accept these with the match; nothing is typed after.
        </span>
      </div>}

      {asking && <EnquiryForm key={asking.id} subject={asking} onClose={() => setAsking(null)}
        myRfqs={asking.kind === 'listing' ? myRfqsFor(asking.molecule).map((r) => ({ id: r.id, label: `${r.volume_mtpd} MTPD, ${r.delivery_start} to ${r.delivery_end}` })) : undefined} />}

      <div className="flex items-center gap-2">
        <Search className="h-4 w-4 text-gray-400" />
        <label htmlFor="md-molecule" className="text-sm text-gray-600">Molecule</label>
        <select id="md-molecule" value={molecule} onChange={(e) => setMolecule(e.target.value)}
                className="rounded-lg border px-3 py-1.5 text-sm">
          <option value="">All</option>
          {commodities.filter((c) => c.market_molecule).map((c) => (
            <option key={c.code} value={c.market_molecule!}>{c.name}</option>
          ))}
        </select>
      </div>

      {unknownMolecule && (
        <div role="status" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          The market has no molecule called "{unknownMolecule}". Showing every molecule.
        </div>
      )}
      {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
      {notice && <div role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</div>}

      <section ref={supplyRef} id="md-supply" aria-current={side === 'supply' ? 'true' : undefined}
               className="gex-card rounded-2xl p-5" style={side === 'supply' ? LANDED : undefined}>
        <h2 className="mb-3 text-sm font-black uppercase tracking-widest text-[var(--text-muted)]">
          Supply — open listings ({offers.length})
        </h2>
        {loading ? <p className="text-sm text-gray-500">Loading…</p> : offers.length === 0 ? (
          <p className="text-sm text-gray-500">No open listing{molecule ? ` for ${molecule}` : ''}.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-gray-500">
                <tr><th className="py-2">Molecule</th><th>Product</th><th>Volume</th><th>Price</th><th>Delivery</th>
                  <th>Origin</th><th>Carbon intensity</th><th>Evidence</th><th>Seller</th><th /></tr>
              </thead>
              <tbody className="divide-y">
                {offers.map((o) => (
                  <tr key={o.id}>
                    <td className="py-2 font-semibold">{o.molecule}</td>
                    <td><ProductCell product={o.product} /></td>
                    <td>{o.volume_mtpd} MTPD</td>
                    <td>{eur(o.price_eur_kg)}
                      <div className="text-xs text-gray-500">{o.offer_type === 'indicative' ? 'Indicative' : 'Firm'}
                        {o.valid_until ? ` · valid to ${o.valid_until.slice(0, 10)}` : ''}</div></td>
                    <td>{o.delivery_start} → {o.delivery_end}
                      <div className="text-xs text-gray-500">{o.incoterm
                        ? `${o.incoterm} ${o.named_place ?? ''}`
                        : [o.delivery_type, o.delivery_basis].filter(Boolean).join(' · ') || 'no delivery basis'}</div></td>
                    <td>{o.production_country ?? '—'}</td>
                    <td><CarbonCell product={o.product} fallback={o.carbon_intensity_gco2e_mj} /></td>
                    <td><EvidenceCell product={o.product} /></td>
                    <td><CounterpartyBadge role={o.seller_role} vetting={o.seller_vetting} /></td>
                    <td>{o.mine
                      ? <span className="rounded bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700">yours</span>
                      : <span className="inline-flex flex-wrap items-center gap-1">
                          <Ask kind="listing" id={o.id} molecule={o.molecule} label={`${o.molecule} ${o.volume_mtpd} MTPD at ${eur(o.price_eur_kg)}`} />
                          <Propose rowId={o.id} pair={(mine) => [o.id, mine]}
                            options={myRfqsFor(o.molecule).map((r) => ({ id: r.id, label: `your RFQ ${r.volume_mtpd} MTPD` }))} /></span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section ref={demandRef} id="md-demand" aria-current={side === 'demand' ? 'true' : undefined}
               className="gex-card rounded-2xl p-5" style={side === 'demand' ? LANDED : undefined}>
        <h2 className="mb-3 text-sm font-black uppercase tracking-widest text-[var(--text-muted)]">
          Demand — open RFQs ({rfqs.length})
        </h2>
        {loading ? <p className="text-sm text-gray-500">Loading…</p> : rfqs.length === 0 ? (
          <p className="text-sm text-gray-500">No open RFQ{molecule ? ` for ${molecule}` : ''}.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-gray-500">
                <tr><th className="py-2">Molecule</th><th>Volume</th><th>Max price</th><th>Delivery</th>
                  <th>Requirements</th><th>Buyer</th><th /></tr>
              </thead>
              <tbody className="divide-y">
                {rfqs.map((r) => (
                  <tr key={r.id}>
                    <td className="py-2 font-semibold">{r.molecule}</td>
                    <td>{r.volume_mtpd} MTPD</td>
                    <td>{eur(r.max_price_eur_kg)}</td>
                    <td>{r.delivery_start} → {r.delivery_end}
                      {r.valid_until ? <div className="text-xs text-gray-500">valid to {r.valid_until.slice(0, 10)}</div> : null}</td>
                    <td><RequirementsCell req={r.requirements} /></td>
                    <td><CounterpartyBadge role={r.buyer_role} vetting={r.buyer_vetting} /></td>
                    <td>{r.mine
                      ? <span className="rounded bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700">yours</span>
                      : <span className="inline-flex flex-wrap items-center gap-1">
                          <Ask kind="rfq" id={r.id} molecule={r.molecule} label={`an RFQ for ${r.molecule} ${r.volume_mtpd} MTPD`} />
                          <Propose rowId={r.id} pair={(mine) => [mine, r.id]}
                            options={myListingsFor(r.molecule).map((o) => ({ id: o.id, label: `your listing ${o.volume_mtpd} MTPD` }))} /></span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

export default MarketDiscoveryPage;
