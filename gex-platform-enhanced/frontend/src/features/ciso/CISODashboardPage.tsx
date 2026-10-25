// Screen: CISO dashboard screen (/ciso-dashboard)
/**
 * The signed-in company's security posture, from its real accounts and sign-ins
 * (2026-10-25). The invented score, MFA rate, alerts and the five sample client
 * companies are gone: GEX staff now see the registered companies from the server.
 */
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Shield, AlertTriangle, Users, Activity,
  CheckCircle, XCircle, Lock, Eye, ChevronRight, Building2,
} from 'lucide-react';
import { cisoCall, NOT_RECORDED } from './cisoApi';

interface OverviewData {
  company_name: string;
  kpis: {
    total_users: number;
    mfa_enabled_pct: number | null;
    kyc_verified: number;
    kyc_pending: number;
    abac_assigned: number;
    abac_unassigned: number;
  };
  events_24h: { total: number; allow: number; deny: number; deny_rate_pct: number };
  abac_phase: { current: number };
  alerts: Array<{ id: string; severity: string; message: string }>;
}

interface Company { company_id: string; company_name: string; company_type: string }

function SeverityBadge({ severity }: { severity: string }) {
  const map: Record<string, string> = {
    high:   'gex-badge gex-badge-red',
    medium: 'gex-badge gex-badge-amber',
    low:    'gex-badge gex-badge-default',
  };
  return <span className={map[severity] ?? 'gex-badge gex-badge-default'}>{severity}</span>;
}

function KpiCard({
  label, value, sub, accent, icon: Icon,
}: {
  label: string; value: string | number; sub?: string; accent?: string; icon?: any;
}) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 shadow-card">
      <div className="flex items-center justify-between">
        <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--text-muted)]">
          {label}
        </div>
        {Icon && <Icon className="w-3.5 h-3.5 text-[var(--text-muted)]" />}
      </div>
      <div className={`mt-1 font-display text-2xl font-extrabold leading-none ${accent ?? 'text-[var(--text-primary)]'}`}>
        {value}
      </div>
      {sub && <div className="mt-0.5 text-xs text-[var(--text-muted)]">{sub}</div>}
    </div>
  );
}

export function CISODashboardPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<OverviewData | null>(null);
  const [companies, setCompanies] = useState<{ companies: Company[]; is_platform_admin: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([cisoCall<OverviewData>('/ciso/overview'), cisoCall('/ciso/companies')])
      .then(([ov, cos]) => { setData(ov); setCompanies(cos); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48 text-sm text-[var(--text-muted)]">
        Loading security posture…
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800/40 dark:bg-amber-900/10 dark:text-amber-300">
        Security posture unavailable: {error ?? 'no answer from the server.'}
      </div>
    );
  }
  const d = data;

  const now = new Date().toLocaleString('en-GB', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });

  return (
    <div className="space-y-5 animate-fade-in">

      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold text-[var(--text-primary)]">
            Security Overview
          </h1>
          <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
            {d.company_name} · CISO Dashboard · as of {now}
          </p>
        </div>
        <div className="flex gap-2">
          <a href="/ciso-access-monitor"
            className="flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-4 py-2 text-sm font-semibold text-[var(--text-primary)] hover:bg-[var(--surface-hover)] transition-colors">
            <Eye className="w-3.5 h-3.5" /> Access Monitor
          </a>
          <a href="/ciso-compliance"
            className="flex items-center gap-1.5 rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-semibold text-white hover:opacity-90 transition-opacity">
            <Shield className="w-3.5 h-3.5" /> Compliance Report
          </a>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <KpiCard label="Accounts"      value={d.kpis.total_users} icon={Users} />
        <KpiCard label="MFA Adoption"  value={d.kpis.mfa_enabled_pct ?? NOT_RECORDED}
          accent="text-[var(--text-muted)]" sub="accounts carry no MFA attribute" icon={Lock} />
        <KpiCard label="KYC Verified"  value={d.kpis.kyc_verified}
          sub={`${d.kpis.kyc_pending} not verified`} accent="text-[var(--brand)]" icon={CheckCircle} />
        <KpiCard label="Project roles" value={d.kpis.abac_assigned}
          sub={`${d.kpis.abac_unassigned} account(s) without one`} accent="text-[var(--brand)]" icon={Shield} />
        <KpiCard label="Sign-ins (24 h)" value={d.events_24h.total}
          sub={`${d.events_24h.allow} accepted / ${d.events_24h.deny} refused`} icon={Activity} />
        <KpiCard label="Refused"       value={`${d.events_24h.deny_rate_pct}%`}
          accent={d.events_24h.deny_rate_pct > 30 ? 'text-red-600 dark:text-red-400' : 'text-[var(--text-primary)]'}
          sub="of sign-in attempts" icon={XCircle} />
      </div>

      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card px-5 py-3.5 flex items-center gap-3">
        <h2 className="text-sm font-bold text-[var(--text-primary)]">ABAC enforcement phase</h2>
        <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300">
          Phase {d.abac_phase.current}
        </span>
        <span className="text-xs text-[var(--text-muted)]">platform setting</span>
      </div>

      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
        <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-3.5">
          <h2 className="text-sm font-bold text-[var(--text-primary)]">Alerts</h2>
          <span className={d.alerts.length ? 'gex-badge gex-badge-red' : 'gex-badge gex-badge-green'}>{d.alerts.length} open</span>
        </div>
        <div className="divide-y divide-[var(--border)]">
          {d.alerts.length === 0 && (
            <p className="px-5 py-3.5 text-sm text-[var(--text-muted)]">Nothing in the account records needs attention.</p>
          )}
          {d.alerts.map(a => (
            <div key={a.id} className="flex items-start gap-4 px-5 py-3.5">
              <AlertTriangle className={`mt-0.5 w-4 h-4 flex-shrink-0
                ${a.severity === 'high' ? 'text-red-500' : a.severity === 'medium' ? 'text-amber-500' : 'text-[var(--text-muted)]'}`}
              />
              <p className="flex-1 min-w-0 text-sm text-[var(--text-primary)]">{a.message}</p>
              <SeverityBadge severity={a.severity} />
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: 'Access Monitor',     path: '/ciso-access-monitor', icon: Eye,          desc: 'Sign-in history' },
          { label: 'Identity & Access',  path: '/ciso-identity',       icon: Users,        desc: 'Account attributes' },
          { label: 'Compliance',         path: '/ciso-compliance',     icon: CheckCircle,  desc: 'What is recorded' },
          { label: 'Policy Matrix',      path: '/ciso-policy',         icon: Lock,         desc: 'Gate visibility map' },
        ].map(({ label, path, icon: Icon, desc }) => (
          <a key={path} href={path}
            className="group flex items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3.5 shadow-card hover:border-[var(--brand)] hover:bg-[var(--surface-hover)] transition-colors">
            <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-indigo-50 dark:bg-indigo-900/20">
              <Icon className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold text-[var(--text-primary)] group-hover:text-[var(--brand)]">{label}</div>
              <div className="text-xs text-[var(--text-muted)]">{desc}</div>
            </div>
            <ChevronRight className="w-3.5 h-3.5 text-[var(--text-muted)] group-hover:text-[var(--brand)]" />
          </a>
        ))}
      </div>

      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
        <div className="border-b border-[var(--border)] px-5 py-3.5 flex items-center gap-2">
          <Building2 className="w-4 h-4 text-[var(--text-muted)]" />
          <h2 className="text-sm font-bold text-[var(--text-primary)]">
            {companies?.is_platform_admin ? 'Client CISO Dashboards' : 'Company CISO Dashboard'}
          </h2>
          <span className="ml-auto gex-badge gex-badge-default">{companies?.companies.length ?? 0} companies</span>
        </div>
        <div className="divide-y divide-[var(--border)]">
          {(companies?.companies ?? []).map(co => (
            <button
              key={co.company_id}
              onClick={() => navigate(`/ciso/client/${co.company_id}`)}
              className="w-full flex items-center gap-4 px-5 py-3.5 hover:bg-[var(--surface-hover)] transition-colors text-left"
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-indigo-100 dark:bg-indigo-900/30">
                <Shield className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
              </div>
              <div className="flex-1 min-w-0">
                <span className="text-sm font-semibold text-[var(--text-primary)]">{co.company_name}</span>
                <p className="text-xs text-[var(--text-muted)]">{co.company_type}</p>
              </div>
              <ChevronRight className="w-4 h-4 text-[var(--text-muted)]" />
            </button>
          ))}
        </div>
      </div>

    </div>
  );
}
