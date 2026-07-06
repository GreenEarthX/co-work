// Screen: ABAC identity management screen (/ciso-identity)
import { useState, useEffect } from 'react';
import {
  ChevronRight, Save, X, CheckCircle,
  AlertTriangle, Lock, Info, Globe, Eye, EyeOff,
} from 'lucide-react';
import { useUserRole } from '@/contexts/UserRoleContext';

/** Convert a company display name to the demo slug used as the API company key.
 *  e.g. "HamburgOne.com" → "hamburgone_com",  "NordLB" → "nordlb" */
function toDemoCompanyKey(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
}

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
  certifications: string[];
  last_active: string;
  kyc_status: string;
  mfa_enabled: boolean;
  // Prosumer / trade attributes
  capabilities?: string[];
  credit_rating?: string;
  credit_rating_source?: string;
  export_licenses?: string[];
  token_ready?: boolean;
  transformation_license?: boolean;
  aggregation_limit_mt?: number | null;
}

const ACTOR_TYPES = [
  'PRODUCER', 'OFFTAKER', 'COMMERCIAL_BANKER', 'DFI', 'INSURER',
  'REGULATOR', 'GOV_AGENCY', 'CERTIFIER', 'EPC_CONTRACTOR',
  'LOGISTICS_OPERATOR', 'TECHNOLOGY_PROVIDER', 'EXECUTIVE',
];

const CLEARANCE_LEVELS = ['STANDARD', 'CONFIDENTIAL', 'RESTRICTED'];

const CAPABILITIES = ['OFFTAKE', 'PRODUCE', 'SELL', 'TRADE', 'CERTIFY', 'FINANCE', 'INSURE'];

const CERT_OPTIONS = ['ISO_27001', 'SOC2_TYPE_II', 'GDPR_DPO', 'ISO_14064', 'RED_III'];

const NDA_PARTNERS = [
  'GreenEarthX_Admin',
  'proj_bremen_operator',
  'proj_wales_operator',
  'proj_helios_operator',
  'proj_rotterdam_operator',
  'proj_lehavre_operator',
];

const CLEARANCE_DESC: Record<string, string> = {
  STANDARD:     'Read shared & public resources only',
  CONFIDENTIAL: 'Read confidential resources; limited export',
  RESTRICTED:   'Full read access including restricted data; export allowed',
};

const ACTOR_GATES: Record<string, string[]> = {
  PRODUCER:           ['G0_SITE_RIGHTS', 'G1_GRID_WATER', 'G3_FEEDSTOCK_LOGISTICS', 'G5_EPC', 'G9_PERMITS', 'G11_COD'],
  OFFTAKER:           ['G4_OFFTAKE'],
  COMMERCIAL_BANKER:  ['G4_OFFTAKE', 'G6_IE_SIGNOFF', 'G7_INSURANCE', 'G8_MODEL_AUDIT', 'G10_FINANCIAL_CLOSE'],
  DFI:                ['G4_OFFTAKE', 'G6_IE_SIGNOFF', 'G7_INSURANCE', 'G8_MODEL_AUDIT', 'G10_FINANCIAL_CLOSE'],
  INSURER:            ['G5_EPC', 'G6_IE_SIGNOFF', 'G7_INSURANCE'],
  REGULATOR:          ['G2_CERTIFICATION', 'G6_IE_SIGNOFF', 'G9_PERMITS'],
  GOV_AGENCY:         ['G0–G11 (all)'],
  CERTIFIER:          ['G2_CERTIFICATION', 'G6_IE_SIGNOFF', 'G9_PERMITS'],
  EPC_CONTRACTOR:     ['G5_EPC', 'G11_COD'],
  LOGISTICS_OPERATOR: ['G3_FEEDSTOCK_LOGISTICS'],
  TECHNOLOGY_PROVIDER:['G5_EPC', 'G11_COD'],
  EXECUTIVE:          ['G0–G11 (all)'],
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
  onClose,
  onSave,
}: {
  user: GexUser;
  projects: GexProject[];
  onClose: () => void;
  onSave: (updated: Partial<GexUser>) => Promise<void>;
}) {
  const [clearance, setClearance]     = useState(user.clearance_level);
  const [actorMap, setActorMap]       = useState<Record<string, string[]>>({ ...user.actor_type_per_project });
  const [ndas, setNdas]               = useState<string[]>([...user.nda_signed_with]);
  const [certs, setCerts]             = useState<string[]>([...user.certifications]);
  const [caps, setCaps]               = useState<string[]>([...(user.capabilities ?? [])]);
  const [creditRating, setCreditRating] = useState(user.credit_rating ?? 'NR');
  const [exportLicenses, setExportLicenses] = useState<string[]>([...(user.export_licenses ?? [])]);
  const [tokenReady, setTokenReady]   = useState(user.token_ready ?? false);
  const [saving, setSaving]           = useState(false);
  const [saved, setSaved]             = useState(false);
  const [showGates, setShowGates]     = useState<string | null>(null);

  const toggleNda = (p: string) =>
    setNdas(prev => prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p]);

  const toggleCert = (c: string) =>
    setCerts(prev => prev.includes(c) ? prev.filter(x => x !== c) : [...prev, c]);

  const toggleCap = (c: string) =>
    setCaps(prev => prev.includes(c) ? prev.filter(x => x !== c) : [...prev, c]);

  const handleSave = async () => {
    setSaving(true);
    await onSave({
      clearance_level: clearance,
      actor_type_per_project: actorMap,
      nda_signed_with: ndas,
      certifications: certs,
      capabilities: caps,
      credit_rating: creditRating,
      export_licenses: exportLicenses,
      token_ready: tokenReady,
    } as Partial<GexUser>);
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
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
              {projects.map(proj => {
                const roles = actorMap[proj.id] ?? [];
                const toggleRole = (role: string) => {
                  setActorMap(prev => {
                    const current = prev[proj.id] ?? [];
                    const next = current.includes(role)
                      ? current.filter(r => r !== role)
                      : [...current, role];
                    return { ...prev, [proj.id]: next };
                  });
                };
                // Union of gates across all assigned actor types
                const visibleGates = roles.flatMap(r => ACTOR_GATES[r] ?? []);
                const uniqueGates = [...new Set(visibleGates)].sort();

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
                      {ACTOR_TYPES.map(t => (
                        <button
                          key={t}
                          onClick={() => toggleRole(t)}
                          className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold transition-colors
                            ${roles.includes(t)
                              ? 'border-indigo-400 bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300'
                              : 'border-[var(--border)] text-[var(--text-muted)] hover:border-indigo-300'}`}
                        >
                          {t}
                        </button>
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
              {NDA_PARTNERS.map(p => (
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

          {/* ── Certifications ── */}
          <section>
            <label className="block text-xs font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-2">
              User Certifications
            </label>
            <div className="flex flex-wrap gap-2">
              {CERT_OPTIONS.map(c => (
                <button
                  key={c}
                  onClick={() => toggleCert(c)}
                  className={`rounded-full border px-3 py-1 text-xs font-semibold transition-colors
                    ${certs.includes(c)
                      ? 'border-indigo-400 bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300'
                      : 'border-[var(--border)] text-[var(--text-muted)] hover:border-indigo-300'}`}
                >
                  {c}
                </button>
              ))}
            </div>
          </section>

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
  const { role } = useUserRole();
  const companyKey = toDemoCompanyKey(role.company_name);

  const [users, setUsers]         = useState<GexUser[]>([]);
  const [projects, setProjects]   = useState<GexProject[]>([]);
  const [loading, setLoading]     = useState(true);
  const [selected, setSelected]   = useState<GexUser | null>(null);

  useEffect(() => {
    fetch('/api/v1/ciso/users', { headers: { 'x-demo-company': companyKey } })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d?.users)    setUsers(d.users);
        if (d?.projects) setProjects(d.projects);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [companyKey]);

  const handleSave = async (updated: Partial<GexUser>) => {
    if (!selected) return;
    try {
      const res = await fetch(`/api/v1/ciso/users/${selected.user_id}/attributes`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'x-demo-company': companyKey,
        },
        body: JSON.stringify({
          clearance_level:         updated.clearance_level,
          actor_type_per_project:  updated.actor_type_per_project,
          nda_signed_with:         updated.nda_signed_with,
          certifications:          updated.certifications,
          capabilities:            updated.capabilities,
          credit_rating:           updated.credit_rating,
          export_licenses:         updated.export_licenses,
          token_ready:             updated.token_ready,
        }),
      });
      if (res.ok) {
        const d = await res.json();
        setUsers(prev => prev.map(u => u.user_id === selected.user_id ? d.user : u));
        setSelected(d.user);
      }
    } catch {
      // network error — optimistic update anyway for demo
      setUsers(prev => prev.map(u =>
        u.user_id === selected.user_id ? { ...u, ...updated } : u
      ));
    }
  };

  return (
    <div className="space-y-5 animate-fade-in">

      {/* ── Header ── */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold text-[var(--text-primary)]">Identity & Access</h1>
          <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
            Manage ABAC attributes for {role.company_name} users in GEX
          </p>
        </div>
        <span className="rounded-full bg-indigo-100 dark:bg-indigo-900/20 px-3 py-1 text-xs font-bold uppercase tracking-wide text-indigo-700 dark:text-indigo-300">
          ABAC Phase 3 Active — Trade Policy
        </span>
      </div>

      {/* ── Info banner ── */}
      <div className="flex items-start gap-3 rounded-xl border border-indigo-200 bg-indigo-50 dark:border-indigo-800 dark:bg-indigo-900/20 px-4 py-3">
        <Info className="mt-0.5 w-4 h-4 flex-shrink-0 text-indigo-600 dark:text-indigo-400" />
        <p className="text-sm text-indigo-800 dark:text-indigo-200">
          Each user's <strong>roles per project</strong> and <strong>trade capabilities</strong> determine which gates, documents,
          and trade actions they can access. Prosumers (entities that both buy and produce) hold multiple roles.
          Credit rating, export licenses, and token readiness are enforced by ABAC rules R7-R9.
          Changes take effect immediately and are logged to the immutable audit trail.
        </p>
      </div>

      {/* ── User table ── */}
      <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
        <div className="border-b border-[var(--border)] px-5 py-3.5">
          <h2 className="text-sm font-bold text-[var(--text-primary)]">
            {role.company_name} — Users ({users.length})
          </h2>
        </div>

        {loading ? (
          <div className="px-6 py-12 text-center text-sm text-[var(--text-muted)]">Loading…</div>
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
                        {u.mfa_enabled
                          ? <CheckCircle className="w-4 h-4 text-emerald-500" />
                          : <AlertTriangle className="w-4 h-4 text-amber-500" />}
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
          onClose={() => setSelected(null)}
          onSave={handleSave}
        />
      )}

      {/* ── Guest & Prospect Policy ── */}
      <GuestPolicyPanel />

    </div>
  );
}

// ─── Guest Policy Panel ───────────────────────────────────────────────────────

interface GuestPolicyItem {
  key: string;
  label: string;
  description: string;
  locked?: boolean;   // always-on; cannot be disabled by CISO
  category: 'always_open' | 'opt_in' | 'blocked';
}

const GUEST_POLICY_ITEMS: GuestPolicyItem[] = [
  {
    key: 'onboarding_wizard',
    label: 'Project Viability Wizard',
    description: 'Free 4-step bankability assessment — lead capture. Always open.',
    locked: true,
    category: 'always_open',
  },
  {
    key: 'market_demand_overview',
    label: 'Market Demand Overview',
    description: 'Aggregated regional demand data — no project names or counterparties.',
    locked: true,
    category: 'always_open',
  },
  {
    key: 'gate_definitions',
    label: 'Gate Definitions',
    description: 'Public descriptions of the 12 bankability gates (no scores).',
    locked: true,
    category: 'always_open',
  },
  {
    key: 'pricing_curves',
    label: 'Indicative Pricing Curves',
    description: 'Delayed (T-5 days) regional price curves. CISO opt-in.',
    category: 'opt_in',
  },
  {
    key: 'project_data',
    label: 'Project Data',
    description: 'Project names, locations, and status — requires sign-in.',
    category: 'blocked',
  },
  {
    key: 'evidence',
    label: 'Evidence & Documents',
    description: 'Gate evidence, submissions, and supporting documents.',
    category: 'blocked',
  },
  {
    key: 'bankability_scores',
    label: 'Bankability Scores',
    description: 'Gate scores, state machine position, and verification status.',
    category: 'blocked',
  },
  {
    key: 'contracts',
    label: 'Contracts & Offtake Terms',
    description: 'Term sheets, signed contracts, and commitment records.',
    category: 'blocked',
  },
  {
    key: 'data_room',
    label: 'Virtual Data Room',
    description: 'Restricted documents shared with mandated lenders/insurers.',
    category: 'blocked',
  },
  {
    key: 'capital_stack',
    label: 'Capital Stack & Waterfall',
    description: 'Debt structure, DSCR model, and tranche distribution.',
    category: 'blocked',
  },
];

const STORAGE_KEY_GUEST_POLICY = 'gex_ciso_guest_policy';

function GuestPolicyPanel() {
  const [policy, setPolicy] = useState<Record<string, boolean>>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY_GUEST_POLICY);
      if (saved) return JSON.parse(saved);
    } catch { /* fall through */ }
    // defaults
    return {
      onboarding_wizard:      true,
      market_demand_overview: true,
      gate_definitions:       true,
      pricing_curves:         false,
      project_data:           false,
      evidence:               false,
      bankability_scores:     false,
      contracts:              false,
      data_room:              false,
      capital_stack:          false,
    };
  });
  const [saved, setSaved] = useState(false);

  const toggle = (key: string) => {
    setPolicy(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const handleSave = () => {
    localStorage.setItem(STORAGE_KEY_GUEST_POLICY, JSON.stringify(policy));
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const categories: { id: GuestPolicyItem['category']; label: string; color: string }[] = [
    { id: 'always_open', label: 'Always Open (lead capture)',    color: 'text-teal-400' },
    { id: 'opt_in',      label: 'CISO Opt-in (disabled by default)', color: 'text-amber-400' },
    { id: 'blocked',     label: 'Blocked (requires sign-in)',    color: 'text-red-400' },
  ];

  return (
    <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-3.5">
        <div className="flex items-center gap-2">
          <Globe className="w-4 h-4 text-teal-500" />
          <h2 className="text-sm font-bold text-[var(--text-primary)]">
            Guest & Prospect Visibility Policy
          </h2>
        </div>
        <span className="text-xs text-[var(--text-muted)] bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded">
          ACTOR_TYPE = GUEST
        </span>
      </div>

      <div className="p-5 space-y-5">
        {/* Info */}
        <div className="flex items-start gap-3 rounded-xl border border-teal-200 bg-teal-50 dark:border-teal-800 dark:bg-teal-900/20 px-4 py-3">
          <Info className="mt-0.5 w-4 h-4 flex-shrink-0 text-teal-600 dark:text-teal-400" />
          <p className="text-sm text-teal-800 dark:text-teal-200">
            Controls what unauthenticated visitors (ACTOR_TYPE = GUEST) can see on the
            public landing page. These rules feed the ABAC R0 gate — guests can never
            access anything above PUBLIC sensitivity, regardless of these settings.
          </p>
        </div>

        {/* Policy items grouped by category */}
        {categories.map(({ id, label, color }) => {
          const items = GUEST_POLICY_ITEMS.filter(i => i.category === id);
          return (
            <div key={id}>
              <p className={`text-xs font-bold uppercase tracking-wider mb-2 ${color}`}>
                {label}
              </p>
              <div className="space-y-2">
                {items.map((item) => {
                  const isOn = policy[item.key] ?? false;
                  const isLocked = !!item.locked;
                  return (
                    <div
                      key={item.key}
                      className={`flex items-center gap-4 rounded-lg border px-4 py-3 transition-colors
                        ${isOn
                          ? 'border-teal-700/40 bg-teal-900/10'
                          : 'border-[var(--border)] bg-[var(--surface-hover)]'
                        }`}
                    >
                      {/* Toggle */}
                      <button
                        type="button"
                        disabled={isLocked}
                        onClick={() => !isLocked && toggle(item.key)}
                        className={`relative flex-shrink-0 w-10 h-5 rounded-full transition-colors
                          ${isLocked ? 'cursor-not-allowed' : 'cursor-pointer'}
                          ${isOn ? 'bg-teal-600' : 'bg-gray-600'}`}
                      >
                        <span
                          className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform
                            ${isOn ? 'translate-x-5' : 'translate-x-0'}`}
                        />
                      </button>

                      {/* Label + description */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-[var(--text-primary)]">
                            {item.label}
                          </span>
                          {isLocked && (
                            <Lock className="w-3 h-3 text-gray-500 flex-shrink-0" />
                          )}
                        </div>
                        <p className="text-xs text-[var(--text-muted)] mt-0.5">
                          {item.description}
                        </p>
                      </div>

                      {/* State badge */}
                      <div className="flex-shrink-0">
                        {isOn ? (
                          <span className="flex items-center gap-1 text-xs text-teal-400">
                            <Eye className="w-3.5 h-3.5" /> Visible
                          </span>
                        ) : (
                          <span className="flex items-center gap-1 text-xs text-gray-500">
                            <EyeOff className="w-3.5 h-3.5" /> Hidden
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}

        {/* Save */}
        <div className="flex items-center justify-between pt-2 border-t border-[var(--border)]">
          <p className="text-xs text-[var(--text-muted)]">
            Changes take effect immediately for new guest sessions. Active sessions are unaffected.
          </p>
          <button
            onClick={handleSave}
            className="flex items-center gap-2 rounded-lg bg-teal-600 hover:bg-teal-500
                       px-4 py-2 text-sm font-semibold text-white transition-colors"
          >
            {saved ? <CheckCircle className="w-4 h-4" /> : <Save className="w-4 h-4" />}
            {saved ? 'Saved' : 'Save Guest Policy'}
          </button>
        </div>
      </div>
    </div>
  );
}
