// Screen: Counterparties (/counterparties)
// The shared register of legal entities that contracts name as buyer or seller
// (tb_counterparty, PostgreSQL). Any signed-in company reads it and adds an entity
// it trades with; GEX staff correct entries (the register is shared, so a company
// cannot rewrite one another relies on). Replaces a placeholder page (2026-10-23).
// Not here yet, and not implied: credit ratings, exposure limits, restrictions.
import { useCallback, useEffect, useState } from 'react';
import { Plus, Users } from 'lucide-react';
import { tradingBookAPI, type Counterparty } from '@/api';

const EMPTY = { legal_name: '', lei: '', country_code: '' };

export function CounterpartiesPage() {
  const [rows, setRows] = useState<Counterparty[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState(EMPTY);
  const [query, setQuery] = useState('');

  const load = useCallback(async () => {
    try {
      setRows(await tradingBookAPI.counterparties());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await tradingBookAPI.addCounterparty({
        legal_name: form.legal_name.trim(), lei: form.lei.trim() || null,
        country_code: form.country_code.trim().toUpperCase(),
      });
      setForm(EMPTY);
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const shown = rows.filter((r) => !query || `${r.legal_name} ${r.lei ?? ''} ${r.country_code}`
    .toLowerCase().includes(query.toLowerCase()));

  return (
    <div className="max-w-5xl mx-auto space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-black text-[var(--text-primary)]">Counterparties</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          The register of legal entities contracts are booked against. Shared by every company on the
          platform; GEX staff correct entries. Credit ratings and exposure limits are not recorded here.
        </p>
      </div>

      {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}

      <form onSubmit={add} className="flex flex-wrap items-end gap-3 rounded-xl border border-gray-200 bg-white p-4">
        <div className="min-w-[16rem] flex-1">
          <label htmlFor="cp-name" className="block text-xs font-semibold text-gray-600">Legal name</label>
          <input id="cp-name" required maxLength={255} value={form.legal_name}
                 onChange={(e) => setForm({ ...form, legal_name: e.target.value })}
                 className="mt-1 w-full rounded-lg border px-3 py-1.5 text-sm" />
        </div>
        <div className="w-56">
          <label htmlFor="cp-lei" className="block text-xs font-semibold text-gray-600">LEI (20 characters, optional)</label>
          <input id="cp-lei" minLength={20} maxLength={20} value={form.lei}
                 onChange={(e) => setForm({ ...form, lei: e.target.value })}
                 className="mt-1 w-full rounded-lg border px-3 py-1.5 font-mono text-sm" />
        </div>
        <div className="w-24">
          <label htmlFor="cp-country" className="block text-xs font-semibold text-gray-600">Country</label>
          <input id="cp-country" required minLength={2} maxLength={2} placeholder="DE" value={form.country_code}
                 onChange={(e) => setForm({ ...form, country_code: e.target.value })}
                 className="mt-1 w-full rounded-lg border px-3 py-1.5 text-sm uppercase" />
        </div>
        <button type="submit" className="inline-flex items-center gap-1 rounded-lg bg-gray-900 px-3 py-2 text-sm font-semibold text-white">
          <Plus className="h-4 w-4" /> Add to the register
        </button>
      </form>

      <div className="rounded-xl border border-gray-200 bg-white">
        <div className="flex items-center justify-between border-b px-4 py-2">
          <span className="text-sm font-bold text-gray-900">{rows.length} in the register</span>
          <label htmlFor="cp-search" className="sr-only">Search</label>
          <input id="cp-search" placeholder="Search" value={query} onChange={(e) => setQuery(e.target.value)}
                 className="rounded-lg border px-3 py-1 text-sm" />
        </div>
        {loading ? <p className="p-6 text-sm text-gray-500">Loading…</p> : shown.length === 0 ? (
          <div className="flex flex-col items-center gap-2 p-10 text-center text-sm text-gray-500">
            <Users className="h-6 w-6 text-gray-400" />
            {rows.length === 0 ? 'The register is empty.' : 'No entry matches.'}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-gray-500">
              <tr><th className="px-4 py-2">Legal name</th><th>LEI</th><th>Country</th><th>Status</th></tr>
            </thead>
            <tbody className="divide-y">
              {shown.map((r) => (
                <tr key={r.id}>
                  <td className="px-4 py-2 font-medium text-gray-900">{r.legal_name}</td>
                  <td className="font-mono text-xs text-gray-600">{r.lei ?? '—'}</td>
                  <td>{r.country_code}</td>
                  <td>{r.is_active ? 'Active' : 'Inactive'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default CounterpartiesPage;
