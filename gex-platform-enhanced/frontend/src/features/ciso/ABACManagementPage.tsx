import React, { useState, useEffect } from 'react';
import {
  Users, Shield, ChevronRight, Save, X, CheckCircle,
  AlertTriangle, Lock, Info,
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
  actor_type_per_project: Record<string, string>;
  nda_signed_with: string[];
  certifications: string[];
  last_active: string;
  kyc_status: string;
  mfa_enabled: boolean;
}

const ACTOR_TYPES = [
  'PRODUCER', 'OFFTAKER', 'COMMERCIAL_BANKER', 'DFI', 'INSURER',
  'REGULATOR', 'GOV_AGENCY', 'CERTIFIER', 'EPC_CONTRACTOR',
  'LOGISTICS_OPERATOR', 'TECHNOLOGY_PROVIDER', 'EXECUTIVE',
];

const CLEARANCE_LEVELS = ['STANDARD', 'CONFIDENTIAL', 'RESTRICTED'];

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
  const [actorMap, setActorMap]       = useState<Record<string, string>>({ ...user.actor_type_per_project });
  const [ndas, setNdas]               = useState<string[]>([...user.nda_signed_with]);
  const [certs, setCerts]             = useState<string[]>([...user.certifications]);
  const [saving, setSaving]           = useState(false);
  const [saved, setSaved]             = useState(false);
  const [showGates, setShowGates]     = useState<string | null>(null);

  const toggleNda = (p: string) =>
    setNdas(prev => prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p]);

  const toggleCert = (c: string) =>
    setCerts(prev => prev.includes(c) ? prev.filter(x => x !== c) : [...prev, c]);

  const handleSave = async () => {
    setSaving(true);
    await onSave({
      clearance_level: clearance,
      actor_type_per_project: actorMap,
      nda_signed_with: ndas,
      certifications: certs,
    });
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

          {/* ── Actor type per project ── */}
          <section>
            <label className="block text-xs font-bold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-2">
              Role per GEX Project
            </label>
            <div className="space-y-2">
              {projects.map(proj => (
                <div key={proj.id} className="rounded-lg border border-[var(--border)] p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <div>
                      <div className="text-xs font-semibold text-[var(--text-primary)]">{proj.name}</div>
                      <div className="text-[10px] text-[var(--text-muted)]">{proj.molecule} · {proj.location}</div>
                    </div>
                    {actorMap[proj.id] && (
                      <button
                        onClick={() => setShowGates(showGates === proj.id ? null : proj.id)}
                        className="flex items-center gap-1 text-[10px] text-indigo-600 dark:text-indigo-400 hover:underline"
                      >
                        <Info className="w-3 h-3" /> Gates
                      </button>
                    )}
                  </div>
                  <select
                    value={actorMap[proj.id] ?? ''}
                    onChange={e => setActorMap(prev => ({
                      ...prev,
                      [proj.id]: e.target.value || undefined as any,
                    }))}
                    className="gex-select w-full text-xs"
                    aria-label={`Actor type for ${proj.name}`}
                  >
                    <option value="">— No access —</option>
                    {ACTOR_TYPES.map(t => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                  {showGates === proj.id && actorMap[proj.id] && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {(ACTOR_GATES[actorMap[proj.id]] ?? []).map(g => (
                        <span key={g} className="rounded bg-indigo-100 dark:bg-indigo-900/30 px-1.5 py-0.5 text-[10px] font-mono text-indigo-700 dark:text-indigo-300">
                          {g}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
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
  const [users, setUsers]         = useState<GexUser[]>([]);
  const [projects, setProjects]   = useState<GexProject[]>([]);
  const [loading, setLoading]     = useState(true);
  const [selected, setSelected]   = useState<GexUser | null>(null);

  useEffect(() => {
    fetch('/api/v1/ciso/users', { headers: { 'x-demo-company': 'bp_global_energy' } })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d?.users)    setUsers(d.users);
        if (d?.projects) setProjects(d.projects);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const handleSave = async (updated: Partial<GexUser>) => {
    if (!selected) return;
    try {
      const res = await fetch(`/api/v1/ciso/users/${selected.user_id}/attributes`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'x-demo-company': 'bp_global_energy',
        },
        body: JSON.stringify({
          clearance_level:         updated.clearance_level,
          actor_type_per_project:  updated.actor_type_per_project,
          nda_signed_with:         updated.nda_signed_with,
          certifications:          updated.certifications,
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
            Manage ABAC attributes for BP Global Energy users in GEX
          </p>
        </div>
        <span className="rounded-full bg-indigo-100 dark:bg-indigo-900/20 px-3 py-1 text-xs font-bold uppercase tracking-wide text-indigo-700 dark:text-indigo-300">
          ABAC Phase 2 Active
        </span>
      </div>

      {/* ── Info banner ── */}
      <div className="flex items-start gap-3 rounded-xl border border-indigo-200 bg-indigo-50 dark:border-indigo-800 dark:bg-indigo-900/20 px-4 py-3">
        <Info className="mt-0.5 w-4 h-4 flex-shrink-0 text-indigo-600 dark:text-indigo-400" />
        <p className="text-sm text-indigo-800 dark:text-indigo-200">
          Each user's <strong>actor type per project</strong> determines which bankability gates and documents
          they can read, write or export. Changes take effect immediately and are logged to the immutable audit trail.
        </p>
      </div>

      {/* ── User table ── */}
      <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
        <div className="border-b border-[var(--border)] px-5 py-3.5">
          <h2 className="text-sm font-bold text-[var(--text-primary)]">
            Organisation Users ({users.length})
          </h2>
        </div>

        {loading ? (
          <div className="px-6 py-12 text-center text-sm text-[var(--text-muted)]">Loading…</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="gex-table">
              <thead>
                <tr>
                  {['User', 'Role', 'Clearance', 'KYC', 'MFA', 'Projects', 'Last Active', ''].map(h => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map(u => {
                  const projectCount = Object.keys(u.actor_type_per_project).length;
                  return (
                    <tr key={u.user_id}>
                      <td>
                        <div className="font-semibold text-[var(--text-primary)]">{u.name}</div>
                        <div className="text-xs text-[var(--text-muted)]">{u.email}</div>
                      </td>
                      <td className="text-sm text-[var(--text-secondary)]">{u.role}</td>
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
                      <td className="text-xs text-[var(--text-muted)] whitespace-nowrap">
                        {new Date(u.last_active).toLocaleDateString('en-GB')}
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

    </div>
  );
}
