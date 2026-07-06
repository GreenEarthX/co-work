// Screen: CISO communications screen (/ciso-communications)
import React, { useState, useEffect, useCallback } from 'react';
import {
  MessageSquare, Shield, AlertTriangle, CheckCircle, XCircle,
  RefreshCw, ChevronDown, ChevronRight, Lock, Users, Hash,
} from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────────────────

interface CommEvent {
  id: number;
  timestamp: string;
  event_type: string;
  room_id: string | null;
  project_id: string | null;
  gate_id: string | null;
  actor_user_id: string | null;
  company_id: string | null;
  metadata: string | null;
  abac_decision: string | null;
}

interface AdminEntry {
  id: number;
  timestamp: string;
  admin_user_id: string;
  action: string;
  room_id: string | null;
  target_user_id: string | null;
  justification: string;
  before_state: string | null;
  after_state: string | null;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const EVENT_TYPE_LABEL: Record<string, { label: string; color: string }> = {
  'room.created':   { label: 'Room Created',    color: 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20' },
  'room.archived':  { label: 'Room Archived',   color: 'text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-800' },
  'member.joined':  { label: 'Member Joined',   color: 'text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20' },
  'member.kicked':  { label: 'Member Kicked',   color: 'text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20' },
  'member.denied':  { label: 'Access Denied',   color: 'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20' },
  'message.sent':   { label: 'Message Sent',    color: 'text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-900/20' },
};

const DECISION_CONFIG: Record<string, { icon: React.ReactNode; cls: string }> = {
  ALLOW: { icon: <CheckCircle className="w-3.5 h-3.5" />, cls: 'text-emerald-600 dark:text-emerald-400' },
  DENY:  { icon: <XCircle    className="w-3.5 h-3.5" />, cls: 'text-red-600 dark:text-red-400' },
  'N/A': { icon: <Shield     className="w-3.5 h-3.5" />, cls: 'text-gray-400 dark:text-gray-500' },
};

function fmtTs(ts: string) {
  try {
    return new Date(ts).toLocaleString('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  } catch { return ts; }
}

function parseMeta(raw: string | null): Record<string, string> {
  if (!raw) return {};
  try { return JSON.parse(raw); } catch { return {}; }
}

// ─── Event Log tab ────────────────────────────────────────────────────────────

function EventLog() {
  const [events, setEvents] = useState<CommEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>('all');
  const [search, setSearch] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    fetch('/api/v1/comms/events?limit=200')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.events) setEvents(d.events); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = events.filter(e => {
    if (filter !== 'all' && e.abac_decision !== filter) return false;
    if (search) {
      const q = search.toLowerCase();
      return (
        (e.actor_user_id?.toLowerCase().includes(q)) ||
        (e.project_id?.toLowerCase().includes(q)) ||
        (e.gate_id?.toLowerCase().includes(q)) ||
        (e.event_type?.toLowerCase().includes(q))
      );
    }
    return true;
  });

  const deny  = events.filter(e => e.abac_decision === 'DENY').length;
  const allow = events.filter(e => e.abac_decision === 'ALLOW').length;

  return (
    <div className="space-y-4">
      {/* Stat strip */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'Total Events', value: events.length, cls: 'text-[var(--text-primary)]' },
          { label: 'ALLOW', value: allow, cls: 'text-emerald-600 dark:text-emerald-400' },
          { label: 'DENY',  value: deny,  cls: 'text-red-600 dark:text-red-400' },
        ].map(s => (
          <div key={s.label} className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 shadow-card">
            <div className={`font-display text-2xl font-extrabold ${s.cls}`}>{s.value}</div>
            <div className="text-[10px] font-bold uppercase tracking-widest text-[var(--text-muted)] mt-0.5">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="text"
          placeholder="Search user, project, gate, event…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="flex-1 min-w-[200px] rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
        <div className="flex gap-1 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-1">
          {['all', 'ALLOW', 'DENY'].map(v => (
            <button
              key={v}
              onClick={() => setFilter(v)}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                filter === v
                  ? 'bg-[var(--brand)] text-white'
                  : 'text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]'
              }`}
            >
              {v === 'all' ? 'All' : v}
            </button>
          ))}
        </div>
        <button
          onClick={load}
          className="flex items-center gap-1 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 text-xs font-semibold text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
        <div className="border-b border-[var(--border)] px-5 py-3 flex items-center justify-between">
          <span className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-widest">
            Communication Events — metadata only (A.12.4.1)
          </span>
          <span className="text-xs text-[var(--text-muted)]">{filtered.length} shown</span>
        </div>
        {loading ? (
          <div className="py-12 text-center text-sm text-[var(--text-muted)]">Loading events…</div>
        ) : filtered.length === 0 ? (
          <div className="py-12 text-center text-sm text-[var(--text-muted)]">No events match your filter.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="gex-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Event</th>
                  <th>Actor</th>
                  <th>Project / Gate</th>
                  <th>Metadata</th>
                  <th>ABAC</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(ev => {
                  const meta   = parseMeta(ev.metadata);
                  const etype  = EVENT_TYPE_LABEL[ev.event_type] ?? { label: ev.event_type, color: 'text-[var(--text-secondary)] bg-[var(--surface-hover)]' };
                  const dec    = DECISION_CONFIG[ev.abac_decision ?? 'N/A'] ?? DECISION_CONFIG['N/A'];
                  const isDeny = ev.abac_decision === 'DENY';
                  return (
                    <tr key={ev.id} className={isDeny ? 'bg-red-50/40 dark:bg-red-900/10' : ''}>
                      <td className="font-mono text-[11px] text-[var(--text-muted)] whitespace-nowrap">
                        {fmtTs(ev.timestamp)}
                      </td>
                      <td>
                        <span className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-bold ${etype.color}`}>
                          {etype.label}
                        </span>
                      </td>
                      <td className="font-mono text-[11px] text-[var(--text-secondary)] max-w-[180px] truncate">
                        {ev.actor_user_id ?? '—'}
                      </td>
                      <td className="text-xs text-[var(--text-secondary)] whitespace-nowrap">
                        <div>{ev.project_id ?? '—'}</div>
                        {ev.gate_id && (
                          <div className="text-[10px] text-[var(--text-muted)]">{ev.gate_id}</div>
                        )}
                      </td>
                      <td className="text-[11px] text-[var(--text-muted)] max-w-[220px]">
                        {Object.entries(meta).map(([k, v]) => (
                          <div key={k} className="truncate">
                            <span className="font-semibold text-[var(--text-secondary)]">{k}:</span> {String(v)}
                          </div>
                        ))}
                      </td>
                      <td>
                        <span className={`flex items-center gap-1 text-xs font-semibold ${dec.cls}`}>
                          {dec.icon} {ev.abac_decision ?? 'N/A'}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <div className="border-t border-[var(--border)] px-5 py-2.5 flex items-center gap-2 text-[10px] text-[var(--text-muted)]">
          <Lock className="w-3 h-3" />
          Message content is end-to-end encrypted (Megolm) and never stored server-side per ISO 27001 A.12.4.1.
        </div>
      </div>
    </div>
  );
}

// ─── Admin Log tab ────────────────────────────────────────────────────────────

function AdminLogTab() {
  const [entries, setEntries] = useState<AdminEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<number | null>(null);

  useEffect(() => {
    fetch('/api/v1/comms/admin-log?limit=100')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.entries) setEntries(d.entries); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const ACTION_LABEL: Record<string, string> = {
    'member.override':     'Member Override',
    'power.override':      'Power Level Override',
    'room.force_archive':  'Force Archive',
  };

  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
        <div className="border-b border-[var(--border)] px-5 py-3.5 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-500" />
          <div>
            <h2 className="text-sm font-bold text-[var(--text-primary)]">Admin Override Log</h2>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">
              Append-only — every admin action requires a written justification (ISO 27001 A.12.4.3)
            </p>
          </div>
          <span className="ml-auto text-xs text-[var(--text-muted)]">{entries.length} entries</span>
        </div>

        {loading ? (
          <div className="py-12 text-center text-sm text-[var(--text-muted)]">Loading admin log…</div>
        ) : entries.length === 0 ? (
          <div className="py-12 text-center text-sm text-[var(--text-muted)]">No admin overrides recorded.</div>
        ) : (
          <div className="divide-y divide-[var(--border)]">
            {entries.map(entry => (
              <div key={entry.id}>
                <button
                  onClick={() => setExpanded(expanded === entry.id ? null : entry.id)}
                  className="flex w-full items-start gap-3 px-5 py-4 text-left hover:bg-[var(--surface-hover)] transition-colors"
                >
                  <div className="mt-0.5 flex-shrink-0 w-8 h-8 rounded-lg bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
                    <Shield className="w-4 h-4 text-amber-600 dark:text-amber-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-sm text-[var(--text-primary)]">
                        {ACTION_LABEL[entry.action] ?? entry.action}
                      </span>
                      <span className="text-[10px] font-mono text-[var(--text-muted)] bg-[var(--surface-hover)] rounded px-1.5 py-0.5">
                        {entry.action}
                      </span>
                    </div>
                    <div className="mt-0.5 text-xs text-[var(--text-muted)]">
                      {entry.admin_user_id} · {fmtTs(entry.timestamp)}
                    </div>
                    <div className="mt-1 text-xs text-[var(--text-secondary)] line-clamp-1">
                      <span className="font-semibold">Justification:</span> {entry.justification}
                    </div>
                  </div>
                  {expanded === entry.id
                    ? <ChevronDown className="w-4 h-4 flex-shrink-0 text-[var(--text-muted)] mt-1" />
                    : <ChevronRight className="w-4 h-4 flex-shrink-0 text-[var(--text-muted)] mt-1" />}
                </button>

                {expanded === entry.id && (
                  <div className="border-t border-[var(--border)] px-5 py-4 bg-[var(--surface-hover)] space-y-3 text-xs">
                    <div className="grid grid-cols-2 gap-x-8 gap-y-2">
                      <div>
                        <div className="text-[10px] font-bold uppercase tracking-widest text-[var(--text-muted)] mb-1">Room</div>
                        <div className="font-mono text-[var(--text-secondary)]">{entry.room_id ?? '—'}</div>
                      </div>
                      <div>
                        <div className="text-[10px] font-bold uppercase tracking-widest text-[var(--text-muted)] mb-1">Target User</div>
                        <div className="font-mono text-[var(--text-secondary)]">{entry.target_user_id ?? '—'}</div>
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] font-bold uppercase tracking-widest text-[var(--text-muted)] mb-1">Full Justification</div>
                      <div className="text-[var(--text-primary)] leading-relaxed">{entry.justification}</div>
                    </div>
                    {(entry.before_state || entry.after_state) && (
                      <div className="grid grid-cols-2 gap-4">
                        {[['Before', entry.before_state], ['After', entry.after_state]].map(([label, val]) => val && (
                          <div key={label as string}>
                            <div className="text-[10px] font-bold uppercase tracking-widest text-[var(--text-muted)] mb-1">{label}</div>
                            <pre className="text-[10px] font-mono bg-[var(--surface)] rounded p-2 overflow-x-auto text-[var(--text-secondary)]">
                              {JSON.stringify(JSON.parse(val as string), null, 2)}
                            </pre>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Room Policy tab ──────────────────────────────────────────────────────────

function RoomPolicyTab() {
  const [policy, setPolicy] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/v1/comms/policy')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setPolicy(d); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="py-12 text-center text-sm text-[var(--text-muted)]">Loading room policy…</div>
  );

  if (!policy) return (
    <div className="py-12 text-center text-sm text-[var(--text-muted)]">Policy unavailable — backend offline.</div>
  );

  return (
    <div className="space-y-4">
      {/* ISO 27001 controls panel */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card overflow-hidden">
        <div className="border-b border-[var(--border)] px-5 py-3.5">
          <h2 className="text-sm font-bold text-[var(--text-primary)]">ISO 27001 Controls</h2>
        </div>
        <div className="divide-y divide-[var(--border)]">
          {Object.entries(policy.iso_27001 as Record<string, string>).map(([ctrl, desc]) => (
            <div key={ctrl} className="flex items-start gap-3 px-5 py-3">
              <span className="flex-shrink-0 gex-badge gex-badge-green font-mono">{ctrl}</span>
              <span className="text-xs text-[var(--text-secondary)]">{desc}</span>
            </div>
          ))}
        </div>
      </div>

      {/* E2EE notice */}
      <div className="flex items-start gap-3 rounded-xl border border-indigo-200 dark:border-indigo-800 bg-indigo-50 dark:bg-indigo-900/20 px-4 py-3">
        <Lock className="w-4 h-4 text-indigo-600 dark:text-indigo-400 mt-0.5 flex-shrink-0" />
        <div className="text-xs text-indigo-700 dark:text-indigo-300 leading-relaxed">
          <span className="font-bold">End-to-end encryption:</span> {policy.e2ee}
        </div>
      </div>

      {/* Gate room specs */}
      <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
        <div className="border-b border-[var(--border)] px-5 py-3.5">
          <h2 className="text-sm font-bold text-[var(--text-primary)]">Gate Room Specifications</h2>
          <p className="text-xs text-[var(--text-muted)] mt-0.5">ABAC actor types permitted per gate (A.9.1.1)</p>
        </div>
        <div className="divide-y divide-[var(--border)]">
          {Object.entries(policy.room_policy as Record<string, any>).map(([gateId, spec]) => (
            <div key={gateId}>
              <button
                onClick={() => setExpanded(expanded === gateId ? null : gateId)}
                className="flex w-full items-center gap-3 px-5 py-3 hover:bg-[var(--surface-hover)] transition-colors"
              >
                <Hash className="w-3.5 h-3.5 text-indigo-500 flex-shrink-0" />
                <span className="font-mono text-sm font-semibold text-[var(--text-primary)]">{gateId}</span>
                <span className="text-xs text-[var(--text-muted)]">{spec.alias}</span>
                <span className="ml-auto text-[10px] text-[var(--text-muted)]">{spec.actors?.length ?? 0} actor types</span>
                {expanded === gateId
                  ? <ChevronDown className="w-3.5 h-3.5 text-[var(--text-muted)]" />
                  : <ChevronRight className="w-3.5 h-3.5 text-[var(--text-muted)]" />}
              </button>
              {expanded === gateId && (
                <div className="px-5 pb-4 bg-[var(--surface-hover)]">
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {(spec.actors as string[]).map(a => (
                      <span key={a} className="rounded-full bg-indigo-100 dark:bg-indigo-900/30 px-2.5 py-0.5 text-[11px] font-mono font-semibold text-indigo-700 dark:text-indigo-300">
                        {a}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Power level legend */}
      <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
        <div className="border-b border-[var(--border)] px-5 py-3.5">
          <h2 className="text-sm font-bold text-[var(--text-primary)]">Power Level Mapping</h2>
        </div>
        <div className="divide-y divide-[var(--border)]">
          {Object.entries(policy.power_level_mapping as Record<string, string>).map(([lvl, desc]) => (
            <div key={lvl} className="flex items-center gap-3 px-5 py-2.5">
              <span className="w-8 text-center font-mono text-sm font-bold text-indigo-600 dark:text-indigo-400">{lvl}</span>
              <span className="text-xs text-[var(--text-secondary)]">{desc}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function CommunicationPage() {
  const [tab, setTab] = useState<'events' | 'admin' | 'policy'>('events');

  const tabs = [
    { id: 'events', label: 'Event Log',       icon: <MessageSquare className="w-3.5 h-3.5" /> },
    { id: 'admin',  label: 'Admin Overrides', icon: <AlertTriangle  className="w-3.5 h-3.5" /> },
    { id: 'policy', label: 'Room Policy',     icon: <Lock          className="w-3.5 h-3.5" /> },
  ] as const;

  return (
    <div className="space-y-5 animate-fade-in">

      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold text-[var(--text-primary)]">
            Secure Communications Monitor
          </h1>
          <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
            Matrix / Synapse · E2EE · ABAC-governed rooms · BP Global Energy
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1.5 rounded-lg border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-900/20 px-3 py-1.5 text-xs font-semibold text-emerald-700 dark:text-emerald-300">
            <CheckCircle className="w-3.5 h-3.5" /> E2EE Active
          </span>
          <span className="flex items-center gap-1.5 rounded-lg border border-indigo-200 dark:border-indigo-800 bg-indigo-50 dark:bg-indigo-900/20 px-3 py-1.5 text-xs font-semibold text-indigo-700 dark:text-indigo-300">
            <Users className="w-3.5 h-3.5" /> ABAC Enforced
          </span>
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-1 w-fit">
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold transition-colors
              ${tab === t.id
                ? 'bg-[var(--brand)] text-white'
                : 'text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]'}`}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {tab === 'events' && <EventLog />}
      {tab === 'admin'  && <AdminLogTab />}
      {tab === 'policy' && <RoomPolicyTab />}

    </div>
  );
}
