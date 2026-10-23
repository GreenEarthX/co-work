// Screen: Matching screen (/matching)
// The company's own matches, from the market engine (PostgreSQL). Matching is
// bilateral (JML, 2026-10-23, spec decision 2B): a match is proposed to a
// specific listing on Market Discovery and binds only when both parties accept.
// GEX screens no one. Until 2026-10-23 this page filtered and scored invented
// companies on credit, logistics, certificates, carbon and tenor; matches carry
// none of those, so the comparison uses only what a match records.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Target } from 'lucide-react';
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Legend, Tooltip,
} from 'recharts';
import { marketAPI, type MarketMatch } from '@/api';

const RADAR_COLORS = ['#0ea5a0', '#f59e0b', '#6366f1', '#10b981', '#f43f5e'];
type Side = 'buyer' | 'seller';

// Each dimension is a field the match itself records, scaled 0–100 across the
// matches being compared (100 = best for the viewing side).
const DIMS = [
  { key: 'price', label: 'Price', value: (m: MarketMatch) => m.price_eur_kg, higherIsBetter: (s: Side) => s === 'seller' },
  { key: 'volume', label: 'Volume', value: (m: MarketMatch) => m.volume_mtpd, higherIsBetter: () => true },
  { key: 'start', label: 'Earliest delivery', value: (m: MarketMatch) => -new Date(m.delivery_start).getTime(), higherIsBetter: () => true },
  { key: 'score', label: 'GEX match score', value: (m: MarketMatch) => m.match_score, higherIsBetter: () => true },
];

function radarData(selected: MarketMatch[], side: Side) {
  return DIMS.map((d) => {
    const vals = selected.map(d.value);
    const lo = Math.min(...vals);
    const hi = Math.max(...vals);
    const row: Record<string, number | string> = { dim: d.label };
    selected.forEach((m) => {
      const t = hi === lo ? 1 : (d.value(m) - lo) / (hi - lo);
      row[m.id] = Math.round(100 * (d.higherIsBetter(side) ? t : 1 - t));
    });
    return row;
  });
}

export function MatchingPage() {
  const navigate = useNavigate();
  const [side, setSide] = useState<Side>('buyer');
  const [molecule, setMolecule] = useState('');
  const [matches, setMatches] = useState<MarketMatch[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setMatches((await marketAPI.myMatches()).matches);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const act = async (fn: () => Promise<unknown>) => {
    try { await fn(); await load(); } catch (e) { setError((e as Error).message); }
  };

  const shown = useMemo(() => matches.filter((m) => m.side === side
    && (m.status === 'pending' || m.status === 'accepted') && (!molecule || m.molecule === molecule)),
  [matches, side, molecule]);
  const molecules = [...new Set(matches.map((m) => m.molecule))];
  const compared = shown.filter((m) => selected.includes(m.id)).slice(0, RADAR_COLORS.length);
  const myAcceptance = (m: MarketMatch) => (m.side === 'seller' ? m.seller_accepted_by : m.buyer_accepted_by);

  return (
    <div className="max-w-7xl mx-auto space-y-6 p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black text-[var(--text-primary)]">Your matches</h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Matches you proposed or received. A match binds only when both parties accept; new ones are
            proposed to a listing on Market Discovery.
          </p>
        </div>
        <button onClick={() => navigate('/market-discovery')}
                className="shrink-0 rounded-xl bg-[var(--text-primary)] px-4 py-2.5 text-sm font-semibold text-white">
          Market discovery
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        {(['buyer', 'seller'] as Side[]).map((s) => (
          <button key={s} onClick={() => { setSide(s); setSelected([]); }}
                  className={`rounded-lg px-3 py-1.5 text-sm font-semibold ${side === s ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-600'}`}>
            {s === 'buyer' ? 'Buying' : 'Selling'}
          </button>
        ))}
        <label htmlFor="mt-molecule" className="ml-2 text-sm text-gray-600">Molecule</label>
        <select id="mt-molecule" value={molecule} onChange={(e) => setMolecule(e.target.value)}
                className="rounded-lg border px-3 py-1.5 text-sm">
          <option value="">All</option>
          {molecules.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>

      {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}

      {loading ? <p className="text-sm text-gray-500">Loading…</p> : shown.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-12 text-center">
          <Target className="h-8 w-8 text-[var(--brand)]" />
          <p className="text-sm text-[var(--text-secondary)]">
            No open match on your {side === 'buyer' ? 'buying' : 'selling'} side.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="space-y-3">
            {shown.map((m) => (
              <div key={m.id} className="rounded-xl border border-gray-200 bg-white p-4">
                <div className="flex items-start justify-between gap-3">
                  <label className="flex items-start gap-2">
                    <input type="checkbox" checked={selected.includes(m.id)} aria-label={`Compare ${m.id}`}
                           onChange={() => setSelected((cur) => cur.includes(m.id) ? cur.filter((x) => x !== m.id) : [...cur, m.id])} />
                    <span>
                      <span className="block text-sm font-semibold text-gray-900">
                        {m.molecule} · {m.volume_mtpd} MTPD · €{m.price_eur_kg}/kg
                      </span>
                      <span className="block text-xs text-gray-500">
                        {side === 'buyer' ? 'From' : 'To'} {(side === 'buyer' ? m.seller_company_name : m.buyer_name) ?? '—'}
                        {' · '}{m.delivery_start} → {m.delivery_end} · score {Math.round(m.match_score)}
                      </span>
                    </span>
                  </label>
                  <div className="flex shrink-0 gap-2">
                    {m.status === 'pending' && !myAcceptance(m) && (
                      <>
                        <button onClick={() => act(() => marketAPI.acceptMatch(m.id))}
                                className="rounded-lg bg-gray-900 px-3 py-1.5 text-xs font-bold text-white">Accept</button>
                        <button onClick={() => act(() => marketAPI.declineMatch(m.id))}
                                className="rounded-lg border px-3 py-1.5 text-xs font-semibold">Decline</button>
                      </>
                    )}
                    {m.status === 'pending' && myAcceptance(m) && (
                      <span className="text-xs font-semibold text-gray-500">Awaiting the counterparty</span>
                    )}
                    {m.status === 'accepted' && (
                      <span className="text-xs font-semibold text-emerald-700">Agreed</span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="rounded-xl border border-gray-200 bg-white p-4">
            <h2 className="mb-2 text-sm font-bold text-gray-900">Compare</h2>
            {compared.length < 2 ? (
              <p className="text-sm text-gray-500">Tick two or more matches to compare them on what they record.</p>
            ) : (
              <div className="h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart data={radarData(compared, side)}>
                    <PolarGrid stroke="var(--border)" />
                    <PolarAngleAxis dataKey="dim" tick={{ fontSize: 11 }} />
                    <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                    {compared.map((m, i) => (
                      <Radar key={m.id} name={`${m.volume_mtpd} MTPD @ €${m.price_eur_kg}`} dataKey={m.id}
                             stroke={RADAR_COLORS[i]} fill={RADAR_COLORS[i]} fillOpacity={0.15} />
                    ))}
                    <Legend />
                    <Tooltip />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default MatchingPage;
