// Screen: ABAC identity management screen (/ciso-identity)
/**
 * The signed-in company's accounts and their access attributes, from auth_users
 * (2026-10-25). Attributes are written by GEX staff only (accounts are vetted, not
 * self-served); anyone else sees the server's refusal, never an optimistic copy.
 * Project roles are read-only here — they come from appointments. Removed: the
 * invented NDA partner list, certifications (no store), a copy of the gate table
 * (now read from /ciso/policy-matrix) and a guest-policy panel that only saved to
 * this browser and was enforced nowhere.
 */
import { useState, useEffect } from 'react';
import { cisoCall, NOT_RECORDED } from './cisoApi';
import {
  ChevronRight, Save, X, CheckCircle,
  Info,
} from 'lucide-react';

// ─── Types ───────────────────────────────────────────────────────────────────

interface GexProject {
  id: string;
  name: string;
  molecule: string;
  location: string;
}

interface GexUser {
  user_id: string;
  name: string;
  email: string;
  role: string;
  clearance_level: string;
  actor_type_per_project: Record<string, string[]>;
  nda_signed_with: string[];
  kyc_status: string;
  account_state?: string;
  mfa_enabled: null;
  // Prosumer / trade attributes
  capabilities?: string[];
  credit_rating?: string;
  credit_rating_source?: string;
  export_licenses?: string[];
  token_ready?: boolean;
  transformation_license?: boolean;
  aggregation_limit_mt?: number | null;
}

const CLEARANCE_LEVELS = ['STANDARD', 'CONFIDENTIAL', 'RESTRICTED'];

const CAPABILITIES = ['OFFTAKE', 'PRODUCE', 'SELL', 'TRADE', 'CERTIFY', 'FINANCE', 'INSURE'];

const CLEARANCE_DESC: Record<string, string> = {
  STANDARD:     'Read shared & public resources only',
  CONFIDENTIAL: 'Read confidential resources; limited export',
  RESTRICTED:   'Full read access including restricted data; export allowed',
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

function KycBadge({ status }: { status: string }) {
  return (
    <span className={`gex-badge ${status === 'VERIFIED' ? 'gex-badge-green' : 'gex-badge-amber'}`}>
      {status}
    </span>
  );
}

function ClearanceBadge({ level }: { level: string }) {
  const map: Record<string, string> = {
    STANDARD:     'gex-badge gex-badge-default',
    CONFIDENTIAL: 'gex-badge gex-badge-amber',
    RESTRICTED:   'gex-badge gex-badge-red',
  };
  return <span className={map[level] ?? 'gex-badge gex-badge-default'}>{level}</span>;
}

// ─── Edit drawer ─────────────────────────────────────────────────────────────

function EditDrawer({
  user,
  projects,
  gates,
  onClose,
  onSave,
}: {
  user: GexUser;
  projects: GexProject[];
  gates: Record<string, string[]>;
  onClose: () => void;
  onSave: (updated: Partial<GexUser>) => Promise<string | null>;
}) {
  const [clearance, setClearance]     = useState(user.clearance_level);
  const actorMap = user.actor_type_per_project;
  const [ndas, setNdas]               = useState<string[]>([...user.nda_signed_with]);
  const [error, setError]             = useState<string | null>(null);
  const ndaOptions = [...new Set([...projects.map(p => p.id), ...user.nda_signed_with])];
  const [caps, setCaps]               = useState<string[]>([...(user.capabilities ?? [])]);
  const [creditRating, setCreditRating] = useState(user.credit_rating ?? 'NR');
  const [exportLicenses, setExportLicenses] = useState<string[]>([...(user.export_licenses ?? [])]);
  const [tokenReady, setTokenReady]   = useState(user.token_ready ?? false);
  const [saving, setSaving]           = useState(false);
  const [saved, setSaved]             = useState(false);
  const [showGates, setShowGates]     = useState<string | null>(null);

  const toggleNda = (p: string) =>
    setNdas(prev => prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p]);

  const toggleCap = (c: string) =>
    setCaps(prev => prev.includes(c) ? prev.filter(x => x !== c) : [...prev, c]);

  const handleSave = async () => {
    setSaving(true);
    const refusal = await onSave({
      clearance_level: clearance,
      nda_signed_with: ndas,
      capabilities: caps,
      credit_rating: creditRating,
      export_licenses: exportLicenses,
      token_ready: tokenReady,
    } as Partial<GexUser>);
    setSaving(false);
    setError(refusal);
    if (!refusal) {
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Overlay */}
      <button className="flex-1 bg-black/30 backdrop-blur-sm" onClick={onClose} />

      {/* Panel */}
      <div className="relative w-full max-w-md overflow-y-auto border-l border-[var(--border)] bg-[var(--surface)] shadow-2xl">
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-[var(--border)] bg-[var(--surface)] px-5 py-4">
          <div>
            <div className="font-bold text-[var(--text-primary)]">{user.name}</div>
            <div className="text-xs text-[var(--text-muted)]">{user.email}</div>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 hover:bg-[var(--surface-hover)] transition-colors">
            <X className="w-4 h-4 text-[var(--text-muted)]" />
          </button>
        </div>

        <div className="space-y-6 p-5">

          {/* ── Clearance level ── */}
          <section>
            <label className="block text-xs font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-2">
              Clearance Level
            </label>
            <div className="space-y-2">
              {CLEARANCE_LEVELS.map(lvl => (
                <label key={lvl}
                  className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors
                    ${clearance === lvl
                      ? 'border-[var(--brand)] bg-indigo-50/60 dark:bg-indigo-900/15'
                      : 'border-[var(--border)] hover:bg-[var(--surface-hover)]'}`}
                >
                  <input type="radio" name="clearance" value={lvl}
                    checked={clearance === lvl}
                    onChange={() => setClearance(lvl)}
                    className="mt-0.5 accent-indigo-600"
                  />
                  <div>
                    <div className="text-sm font-semibold text-[var(--text-primary)]">{lvl}</div>
                    <div className="text-xs text-[var(--text-muted)]">{CLEARANCE_DESC[lvl]}</div>
                  </div>
                </label>
              ))}
            </div>
          </section>

          {/* ── Trade Capabilities (Prosumer) ── */}
          <section>
            <label className="block text-xs font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-2">
              Trade Capabilities
            </label>
            <div className="flex flex-wrap gap-2">
              {CAPABILITIES.map(c => (
                <button
                  key={c}
                  onClick={() => toggleCap(c)}
                  className={`rounded-full border px-3 py-1 text-xs font-semibold transition-colors
                    ${caps.includes(c)
                      ? 'border-emerald-400 bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
                      : 'border-[var(--border)] text-[var(--text-muted)] hover:border-emerald-300'}`}
                >
                  {c}
                </button>
              ))}
            </div>
            <p className="mt-1.5 text-[10px] text-[var(--text-muted)]">
              Prosumers hold multiple capabilities (e.g. OFFTAKE + PRODUCE + SELL). Enforced by ABAC R7.
            </p>
          </section>

          {/* ── Credit & Geofence ── */}
          <section>
            <label className="block text-xs font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-2">
              Credit Rating & Export Compliance
            </label>
            <div className="space-y-3">
              <div className="flex gap-3">
                <div className="flex-1">
                  <label className="text-[10px] text-[var(--text-muted)]">Credit Rating</label>
                  <input
                    type="text"
                    value={creditRating}
                    onChange={e => setCreditRating(e.target.value)}
                    placeholder="e.g. A-, BBB+, GEX-4"
                    className="gex-input mt-1 w-full text-xs"
                  />
                </div>
                <div className="flex-1">
                  <label className="text-[10px] text-[var(--text-muted)]">Export Licenses (ISO codes)</label>
                  <input
                    type="text"
                    value={exportLicenses.join(', ')}
                    onChange={e => setExportLicenses(e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                    placeholder="e.g. DE, NL, FR"
                    className="gex-input mt-1 w-full text-xs"
                  />
                </div>
              </div>
              <label className="flex cursor-pointer items-center gap-2.5">
                <input
                  type="checkbox"
                  checked={tokenReady}
                  onChange={e => setTokenReady(e.target.checked)}
                  className="accent-indigo-600"
                />
                <span className="text-sm text-[var(--text-primary)]">Token-ready (can settle tokenized molecules)</span>
              </label>
            </div>
          </section>

          {/* ── Actor type per project (multi-select for prosumers) ── */}
          <section>
            <label className="block text-xs font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-2">
              Roles per GEX Project
            </label>
            <div className="space-y-2">
              <p className="text-[10px] text-[var(--text-muted)]">Set by appointment, not here.</p>
              {projects.map(proj => {
                const roles = actorMap[proj.id] ?? [];
                const uniqueGates = [...new Set(roles.flatMap(r => gates[r] ?? []))].sort();
                return (
                  <div key={proj.id} className="rounded-lg border border-[var(--border)] p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <div>
                        <div className="text-xs font-semibold text-[var(--text-primary)]">{proj.name}</div>
                        <div className="text-[10px] text-[var(--text-muted)]">{proj.molecule} · {proj.location}</div>
                      </div>
                      {roles.length > 0 && (
                        <button
                          onClick={() => setShowGates(showGates === proj.id ? null : proj.id)}
                          className="flex items-center gap-1 text-[10px] text-indigo-600 dark:text-indigo-400 hover:underline"
                        >
                          <Info className="w-3 h-3" /> Gates ({uniqueGates.length})
                        </button>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {roles.length === 0 ? <span className="text-[10px] text-[var(--text-muted)]">No role</span>
                        : roles.map(t => (
                          <span key={t} className="rounded-full border border-indigo-400 bg-indigo-100 px-2 py-0.5 text-[10px] font-semibold text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300">{t}</span>
                        ))}
                    </div>
                    {showGates === proj.id && uniqueGates.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {uniqueGates.map(g => (
                          <span key={g} className="rounded bg-indigo-100 dark:bg-indigo-900/30 px-1.5 py-0.5 text-[10px] font-mono text-indigo-700 dark:text-indigo-300">
                            {g}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>

          {/* ── NDA partners ── */}
          <section>
            <label className="block text-xs font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-2">
              NDA Signed With
            </label>
            <div className="space-y-1.5">
              {ndaOptions.map(p => (
                <label key={p} className="flex cursor-pointer items-center gap-2.5 rounded-lg px-3 py-2 hover:bg-[var(--surface-hover)] transition-colors">
                  <input
                    type="checkbox"
                    checked={ndas.includes(p)}
                    onChange={() => toggleNda(p)}
                    className="accent-indigo-600"
                  />
                  <span className="text-sm text-[var(--text-primary)]">{p}</span>
                </label>
              ))}
            </div>
          </section>

          {error && (
            <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-800/40 dark:bg-amber-900/10 dark:text-amber-300">
              Not saved: {error}
            </p>
          )}

        </div>

        {/* Footer */}
        <div className="sticky bottom-0 flex justify-end gap-3 border-t border-[var(--border)] bg-[var(--surface)] px-5 py-3.5">
          <button onClick={onClose}
            className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm font-semibold text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] transition-colors">
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-1.5 rounded-lg bg-[var(--brand)] px-5 py-2 text-sm font-semibold text-white hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {saved
              ? <><CheckCircle className="w-3.5 h-3.5" /> Saved</>
              : saving
              ? 'Saving…'
              : <><Save className="w-3.5 h-3.5" /> Save Changes</>}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function ABACManagementPage() {
  const [users, setUsers]         = useState<GexUser[]>([]);
  const [projects, setProjects]   = useState<GexProject[]>([]);
  const [gates, setGates]         = useState<Record<string, string[]>>({});
  const [companyName, setCompanyName] = useState('');
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);
  const [selected, setSelected]   = useState<GexUser | null>(null);

  useEffect(() => {
    Promise.all([cisoCall('/ciso/users'), cisoCall('/ciso/policy-matrix'), cisoCall('/ciso/overview')])
      .then(([d, matrix, ov]) => {
        setUsers(d.users ?? []);
        setProjects(d.projects ?? []);
        setGates(matrix.gate_visibility ?? {});
        setCompanyName(ov.company_name ?? '');
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async (updated: Partial<GexUser>): Promise<string | null> => {
    if (!selected) return null;
    try {
      const d = await cisoCall(`/ciso/users/${selected.user_id}/attributes`, undefined, {
        method: 'PATCH',
        body: JSON.stringify(updated),
      });
      setUsers(prev => prev.map(u => u.user_id === selected.user_id ? d.user : u));
      setSelected(d.user);
      return null;
    } catch (e) {
      return (e as Error).message;
    }
  };

  return (
    <div className="space-y-5 animate-fade-in">

      {/* ── Header ── */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold text-[var(--text-primary)]">Identity & Access</h1>
          <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
            ABAC attributes of {companyName || 'your company'}'s accounts in GEX
          </p>
        </div>
      </div>

      {/* ── Info banner ── */}
      <div className="flex items-start gap-3 rounded-xl border border-indigo-200 bg-indigo-50 dark:border-indigo-800 dark:bg-indigo-900/20 px-4 py-3">
        <Info className="mt-0.5 w-4 h-4 flex-shrink-0 text-indigo-600 dark:text-indigo-400" />
        <p className="text-sm text-indigo-800 dark:text-indigo-200">
          Each user's <strong>roles per project</strong> and <strong>trade capabilities</strong> determine which gates, documents,
          and trade actions they can access. Prosumers (entities that both buy and produce) hold multiple roles.
          Credit rating, export licenses, and token readiness are enforced by ABAC rules R7-R9.
          GEX staff change these attributes; each change is recorded in the event ledger.
        </p>
      </div>

      {/* ── User table ── */}
      <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
        <div className="border-b border-[var(--border)] px-5 py-3.5">
          <h2 className="text-sm font-bold text-[var(--text-primary)]">
            {companyName} — Users ({users.length})
          </h2>
        </div>

        {loading ? (
          <div className="px-6 py-12 text-center text-sm text-[var(--text-muted)]">Loading…</div>
        ) : error ? (
          <div className="px-6 py-6 text-sm text-amber-700 dark:text-amber-300">Accounts unavailable: {error}</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="gex-table">
              <thead>
                <tr>
                  {['User', 'Role', 'Capabilities', 'Credit', 'Clearance', 'KYC', 'MFA', 'Projects', ''].map(h => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map(u => {
                  const projectCount = Object.keys(u.actor_type_per_project).length;
                  const caps = u.capabilities ?? [];
                  const isProsumer = caps.includes('OFFTAKE') && caps.includes('PRODUCE');
                  return (
                    <tr key={u.user_id}>
                      <td>
                        <div className="font-semibold text-[var(--text-primary)]">{u.name}</div>
                        <div className="text-xs text-[var(--text-muted)]">{u.email}</div>
                      </td>
                      <td className="text-sm text-[var(--text-secondary)]">{u.role}</td>
                      <td>
                        <div className="flex flex-wrap gap-0.5">
                          {caps.length > 0 ? caps.map(c => (
                            <span key={c} className={`rounded px-1 py-0.5 text-[10px] font-bold
                              ${isProsumer
                                ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
                                : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}`}
                            >{c}</span>
                          )) : <span className="text-[10px] text-[var(--text-muted)]">—</span>}
                        </div>
                      </td>
                      <td>
                        {u.credit_rating && u.credit_rating !== 'NR'
                          ? <span className="rounded bg-amber-100 dark:bg-amber-900/20 px-1.5 py-0.5 text-[10px] font-bold text-amber-700 dark:text-amber-300">
                              {u.credit_rating}
                            </span>
                          : <span className="text-[10px] text-[var(--text-muted)]">NR</span>}
                      </td>
                      <td><ClearanceBadge level={u.clearance_level} /></td>
                      <td><KycBadge status={u.kyc_status} /></td>
                      <td>
                        <span className="text-[10px] text-[var(--text-muted)]">{NOT_RECORDED}</span>
                      </td>
                      <td>
                        {projectCount > 0
                          ? <span className="gex-badge gex-badge-default">{projectCount} project{projectCount > 1 ? 's' : ''}</span>
                          : <span className="text-xs text-[var(--text-muted)]">No access</span>}
                      </td>
                      <td>
                        <button
                          onClick={() => setSelected(u)}
                          className="flex items-center gap-1 rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs font-semibold text-[var(--text-primary)] hover:bg-[var(--surface-hover)] transition-colors"
                        >
                          Edit <ChevronRight className="w-3 h-3" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Edit drawer ── */}
      {selected && (
        <EditDrawer
          user={selected}
          projects={projects}
          gates={gates}
          onClose={() => setSelected(null)}
          onSave={handleSave}
        />
      )}

    </div>
  );
}
