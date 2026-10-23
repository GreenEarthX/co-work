// Screen: Market Discovery (/market-discovery)
// Every open listing and open RFQ on the platform, anonymised: no company,
// project, token or location (JML, 2026-10-23). A company sees its own rows
// flagged "yours". Matching is bilateral (spec decision 2B): a company proposes
// one of its own RFQs to a listing, or one of its own listings to an RFQ; the
// match binds only when both accept, on the RFQ Management desk. GEX pairs no
// one automatically. Replaces a placeholder (gap register G-04).
import { useCallback, useEffect, useState } from 'react';
import { Search } from 'lucide-react';
import { marketAPI, type Commodity, type MarketRFQ, type OfferListing, type RFQListing } from '@/api';

const eur = (v: number | null | undefined) => (v == null ? '—' : `€${v.toFixed(2)}/kg`);

export function MarketDiscoveryPage() {
  const [molecule, setMolecule] = useState('');
  const [offers, setOffers] = useState<OfferListing[]>([]);
  const [rfqs, setRfqs] = useState<RFQListing[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [myRfqs, setMyRfqs] = useState<MarketRFQ[]>([]);
  const [choice, setChoice] = useState<Record<string, string>>({});
  const [commodities, setCommodities] = useState<Commodity[]>([]);

  useEffect(() => {   // tb_commodity in PostgreSQL — no molecule list in code
    marketAPI.commodities().then(({ commodities }) => setCommodities(commodities))
      .catch((e) => setError((e as Error).message));
  }, []);

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
      await marketAPI.proposeMatch(offerId, rfqId);
      setNotice('Match proposed — it binds only when both parties accept, on the RFQ Management desk.');
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const Propose = ({ rowId, options, pair }: {
    rowId: string; options: { id: string; label: string }[]; pair: (mine: string) => [string, string];
  }) => {
    if (options.length === 0) return null;
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
      </div>

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

      {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
      {notice && <div role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</div>}

      <section className="gex-card rounded-2xl p-5">
        <h2 className="mb-3 text-sm font-black uppercase tracking-widest text-[var(--text-muted)]">
          Supply — open listings ({offers.length})
        </h2>
        {loading ? <p className="text-sm text-gray-500">Loading…</p> : offers.length === 0 ? (
          <p className="text-sm text-gray-500">No open listing{molecule ? ` for ${molecule}` : ''}.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-gray-500">
                <tr><th className="py-2">Molecule</th><th>Volume</th><th>Price</th><th>Delivery</th>
                  <th>Basis</th><th>Carbon intensity</th><th>Certification</th><th /></tr>
              </thead>
              <tbody className="divide-y">
                {offers.map((o) => (
                  <tr key={o.id}>
                    <td className="py-2 font-semibold">{o.molecule}</td>
                    <td>{o.volume_mtpd} MTPD</td>
                    <td>{eur(o.price_eur_kg)}</td>
                    <td>{o.delivery_start} → {o.delivery_end}</td>
                    <td>{[o.delivery_type, o.delivery_basis].filter(Boolean).join(' · ') || '—'}</td>
                    <td>{o.carbon_intensity_gco2e_mj != null ? `${o.carbon_intensity_gco2e_mj} gCO₂e/MJ` : '—'}</td>
                    <td>{o.certification_pathway ?? '—'}</td>
                    <td>{o.mine
                      ? <span className="rounded bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700">yours</span>
                      : <Propose rowId={o.id} pair={(mine) => [o.id, mine]}
                          options={myRfqsFor(o.molecule).map((r) => ({ id: r.id, label: `your RFQ ${r.volume_mtpd} MTPD` }))} />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="gex-card rounded-2xl p-5">
        <h2 className="mb-3 text-sm font-black uppercase tracking-widest text-[var(--text-muted)]">
          Demand — open RFQs ({rfqs.length})
        </h2>
        {loading ? <p className="text-sm text-gray-500">Loading…</p> : rfqs.length === 0 ? (
          <p className="text-sm text-gray-500">No open RFQ{molecule ? ` for ${molecule}` : ''}.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-gray-500">
                <tr><th className="py-2">Molecule</th><th>Volume</th><th>Max price</th><th>Delivery</th><th /></tr>
              </thead>
              <tbody className="divide-y">
                {rfqs.map((r) => (
                  <tr key={r.id}>
                    <td className="py-2 font-semibold">{r.molecule}</td>
                    <td>{r.volume_mtpd} MTPD</td>
                    <td>{eur(r.max_price_eur_kg)}</td>
                    <td>{r.delivery_start} → {r.delivery_end}</td>
                    <td>{r.mine
                      ? <span className="rounded bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700">yours</span>
                      : <Propose rowId={r.id} pair={(mine) => [mine, r.id]}
                          options={myListingsFor(r.molecule).map((o) => ({ id: o.id, label: `your listing ${o.volume_mtpd} MTPD` }))} />}</td>
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
