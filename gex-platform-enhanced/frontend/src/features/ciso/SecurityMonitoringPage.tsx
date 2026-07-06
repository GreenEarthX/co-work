// Screen: Security monitoring / access monitor screen (/ciso-access-monitor)
import { useState, useEffect, useMemo } from 'react';
import { Search, RefreshCw, CheckCircle, XCircle } from 'lucide-react';

// ─── Types ───────────────────────────────────────────────────────────────────

interface AccessEvent {
  id: string;
  timestamp: string;
  user_id: string;
  user_name: string;
  company_id: string;
  project_id: string;
  project_name: string;
  resource_type: string;
  action: string;
  decision: 'ALLOW' | 'DENY';
  rule_triggered: string | null;
  denial_reason: string | null;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const DECISION_BADGE: Record<string, string> = {
  ALLOW: 'gex-badge gex-badge-green',
  DENY:  'gex-badge gex-badge-red',
};

const ACTION_BADGE: Record<string, string> = {
  READ:   'gex-badge gex-badge-default',
  WRITE:  'gex-badge gex-badge-amber',
  EXPORT: 'gex-badge gex-badge-amber',
  VERIFY: 'gex-badge gex-badge-default',
  SHARE:  'gex-badge gex-badge-amber',
  DELETE: 'gex-badge gex-badge-red',
};

function fmt(ts: string) {
  return new Date(ts).toLocaleString('en-GB', {
    day: '2-digit', month: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function SecurityMonitoringPage() {
  const [events, setEvents]       = useState<AccessEvent[]>([]);
  const [loading, setLoading]     = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const [search, setSearch]       = useState('');
  const [filterDecision, setFilterDecision] = useState<'ALL' | 'ALLOW' | 'DENY'>('ALL');
  const [filterUser, _setFilterUser]         = useState('');
  const [filterProject, _setFilterProject]   = useState('');

  const load = (showRefresh = false) => {
    if (showRefresh) setRefreshing(true);
    const params = new URLSearchParams({ limit: '120' });
    if (filterDecision !== 'ALL') params.set('decision', filterDecision);
    if (filterUser)    params.set('user_id', filterUser);
    if (filterProject) params.set('project_id', filterProject);

    fetch(`/api/v1/ciso/access-log?${params}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d?.events) setEvents(d.events);
        setLoading(false);
        setRefreshing(false);
      })
      .catch(() => { setLoading(false); setRefreshing(false); });
  };

  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return events.filter(e => {
      if (q && !e.user_name.toLowerCase().includes(q) &&
               !e.project_name.toLowerCase().includes(q) &&
               !e.resource_type.toLowerCase().includes(q) &&
               !e.action.toLowerCase().includes(q)) return false;
      if (filterDecision !== 'ALL' && e.decision !== filterDecision) return false;
      return true;
    });
  }, [events, search, filterDecision]);

  // Stats
  const allow_ct  = filtered.filter(e => e.decision === 'ALLOW').length;
  const deny_ct   = filtered.filter(e => e.decision === 'DENY').length;
  const deny_rate = filtered.length ? ((deny_ct / filtered.length) * 100).toFixed(1) : '0';

  return (
    <div className="space-y-5 animate-fade-in">

      {/* ── Header ── */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold text-[var(--text-primary)]">Access Monitor</h1>
          <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
            Real-time ABAC access event log — BP Global Energy
          </p>
        </div>
        <button
          onClick={() => load(true)}
          disabled={refreshing}
          className="flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-4 py-2 text-sm font-semibold text-[var(--text-primary)] hover:bg-[var(--surface-hover)] transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* ── Stat strip ── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: 'Total Events',   value: String(filtered.length), accent: 'text-[var(--text-primary)]' },
          { label: 'Allowed',        value: String(allow_ct),        accent: 'text-emerald-600 dark:text-emerald-400' },
          { label: 'Denied',         value: String(deny_ct),         accent: 'text-red-600 dark:text-red-400' },
          { label: 'Deny Rate',      value: `${deny_rate}%`,         accent: deny_ct > 0 ? 'text-amber-600 dark:text-amber-400' : 'text-[var(--text-primary)]' },
        ].map(({ label, value, accent }) => (
          <div key={label} className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 shadow-card">
            <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--text-muted)]">{label}</div>
            <div className={`mt-1 font-display text-2xl font-extrabold leading-none ${accent}`}>{value}</div>
          </div>
        ))}
      </div>

      {/* ── Filters ── */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Search */}
        <div className="relative" style={{ minWidth: '220px' }}>
          <Search className="absolute left-3 top-1/2 w-3.5 h-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search user, project, resource…"
            className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] py-[7px] pl-9 pr-4 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--brand)] focus:outline-none focus:ring-2 focus:ring-[var(--brand-ring)]"
          />
        </div>

        {/* Decision filter */}
        <select
          value={filterDecision}
          onChange={e => setFilterDecision(e.target.value as any)}
          className="gex-select text-sm"
          aria-label="Filter by decision"
        >
          <option value="ALL">All decisions</option>
          <option value="ALLOW">ALLOW only</option>
          <option value="DENY">DENY only</option>
        </select>
      </div>

      {/* ── Table ── */}
      <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
        <div className="border-b border-[var(--border)] px-5 py-3.5">
          <h2 className="text-sm font-bold text-[var(--text-primary)]">
            ABAC Events
            {filterDecision === 'DENY' && (
              <span className="ml-2 text-xs font-normal text-[var(--text-muted)]">— showing denied requests only</span>
            )}
          </h2>
        </div>

        {loading ? (
          <div className="px-6 py-12 text-center text-sm text-[var(--text-muted)]">
            Loading events…
          </div>
        ) : filtered.length === 0 ? (
          <div className="px-6 py-12 text-center text-sm text-[var(--text-muted)]">
            No events match the selected filters.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="gex-table">
              <thead>
                <tr>
                  {['Time', 'User', 'Project', 'Resource', 'Action', 'Decision', 'Rule', 'Reason'].map(h => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map(evt => (
                  <tr
                    key={evt.id}
                    className={evt.decision === 'DENY'
                      ? 'bg-red-50/40 dark:bg-red-950/10'
                      : undefined}
                  >
                    <td className="whitespace-nowrap font-mono text-xs text-[var(--text-muted)]">
                      {fmt(evt.timestamp)}
                    </td>
                    <td>
                      <div className="font-semibold text-[var(--text-primary)] text-sm">{evt.user_name}</div>
                      <div className="font-mono text-xs text-[var(--text-muted)]">{evt.user_id}</div>
                    </td>
                    <td className="text-sm text-[var(--text-secondary)]">{evt.project_name}</td>
                    <td>
                      <span className="gex-badge gex-badge-default text-[10px]">{evt.resource_type}</span>
                    </td>
                    <td>
                      <span className={`${ACTION_BADGE[evt.action] ?? 'gex-badge gex-badge-default'} text-[10px]`}>
                        {evt.action}
                      </span>
                    </td>
                    <td>
                      <span className={`${DECISION_BADGE[evt.decision] ?? 'gex-badge gex-badge-default'} flex items-center gap-1`}>
                        {evt.decision === 'ALLOW'
                          ? <CheckCircle className="w-3 h-3" />
                          : <XCircle className="w-3 h-3" />}
                        {evt.decision}
                      </span>
                    </td>
                    <td className="font-mono text-xs text-[var(--text-muted)]">
                      {evt.rule_triggered ?? '—'}
                    </td>
                    <td className="max-w-[240px]">
                      {evt.denial_reason
                        ? <span className="text-xs text-red-600 dark:text-red-400">{evt.denial_reason}</span>
                        : <span className="text-xs text-[var(--text-muted)]">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

    </div>
  );
}
