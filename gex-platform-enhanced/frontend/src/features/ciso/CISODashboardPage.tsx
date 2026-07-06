// Screen: CISO dashboard screen (/ciso-dashboard)
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Shield, ShieldCheck, AlertTriangle, Users, Activity,
  CheckCircle, XCircle, Lock, Eye, ChevronRight, Building2,
} from 'lucide-react';

// ─── Types ───────────────────────────────────────────────────────────────────

interface OverviewData {
  company_name: string;
  security_score: number;
  score_label: string;
  kpis: {
    total_users: number;
    mfa_enabled_pct: number;
    kyc_verified: number;
    kyc_pending: number;
    abac_assigned: number;
    abac_unassigned: number;
  };
  events_24h: {
    total: number;
    allow: number;
    deny: number;
    deny_rate_pct: number;
  };
  abac_phase: {
    current: number;
    phases: Array<{ phase: number; label: string; status: string }>;
  };
  alerts: Array<{ id: string; severity: string; message: string; ts: string }>;
}

// ─── Score gauge ──────────────────────────────────────────────────────────────

function ScoreGauge({ score, label }: { score: number; label: string }) {
  const color =
    score >= 75 ? 'text-emerald-600 dark:text-emerald-400'
    : score >= 50 ? 'text-amber-600 dark:text-amber-400'
    : 'text-red-600 dark:text-red-400';
  const ring =
    score >= 75 ? 'stroke-emerald-500'
    : score >= 50 ? 'stroke-amber-500'
    : 'stroke-red-500';

  const r = 38;
  const circ = 2 * Math.PI * r;
  const dashoffset = circ - (score / 100) * circ;

  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative w-28 h-28">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
          <circle cx="50" cy="50" r={r} fill="none"
            strokeWidth="8" className="stroke-[var(--border)]" />
          <circle cx="50" cy="50" r={r} fill="none"
            strokeWidth="8"
            strokeLinecap="round"
            className={ring}
            strokeDasharray={circ}
            strokeDashoffset={dashoffset}
            style={{ transition: 'stroke-dashoffset 0.8s ease' }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={`font-display text-3xl font-extrabold leading-none ${color}`}>
            {score}
          </span>
          <span className="text-[10px] text-[var(--text-muted)] font-semibold uppercase tracking-wide">
            /100
          </span>
        </div>
      </div>
      <span className={`text-sm font-bold ${color}`}>{label}</span>
    </div>
  );
}

// ─── Alert severity badge ────────────────────────────────────────────────────

function SeverityBadge({ severity }: { severity: string }) {
  const map: Record<string, string> = {
    high:   'gex-badge gex-badge-red',
    medium: 'gex-badge gex-badge-amber',
    low:    'gex-badge gex-badge-default',
  };
  return <span className={map[severity] ?? 'gex-badge gex-badge-default'}>{severity}</span>;
}

// ─── KPI card ────────────────────────────────────────────────────────────────

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

// ─── Page ─────────────────────────────────────────────────────────────────────

// ─── Company registry (mirrored from ClientCISODashboard) ─────────────────────

const GEX_COMPANIES = [
  { id: 'bp_global_energy', name: 'BP Global Energy',   ciso: 'Marcus Webb',   jurisdiction: 'EU / GB', iso27001: true,  score: 76, alerts: 2 },
  { id: 'shell_energy',     name: 'Shell Energy',        ciso: 'Anna Broersen', jurisdiction: 'EU / NL', iso27001: true,  score: 79, alerts: 1 },
  { id: 'bnp_paribas',      name: 'BNP Paribas',         ciso: 'Henri Leconte', jurisdiction: 'EU / FR', iso27001: true,  score: 88, alerts: 0 },
  { id: 'rwe_renewables',   name: 'RWE Renewables',      ciso: 'Klaus Fischer', jurisdiction: 'EU / DE', iso27001: false, score: 61, alerts: 3 },
  { id: 'total_energies',   name: 'TotalEnergies',       ciso: 'Claire Moreau', jurisdiction: 'EU / FR', iso27001: true,  score: 74, alerts: 1 },
]

// ─── Page ─────────────────────────────────────────────────────────────────────

export function CISODashboardPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/v1/ciso/overview')
      .then(r => r.ok ? r.json() : null)
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48 text-sm text-[var(--text-muted)]">
        Loading security posture…
      </div>
    );
  }

  // Fallback demo data so the page is never blank
  const d: OverviewData = data ?? {
    company_name: 'BP Global Energy',
    security_score: 76,
    score_label: 'Good',
    kpis: { total_users: 5, mfa_enabled_pct: 80, kyc_verified: 4, kyc_pending: 1, abac_assigned: 4, abac_unassigned: 1 },
    events_24h: { total: 28, allow: 22, deny: 6, deny_rate_pct: 21.4 },
    abac_phase: {
      current: 2,
      phases: [
        { phase: 1, label: 'R1–R3: Stakeholder + Evidence', status: 'active' },
        { phase: 2, label: 'R4–R6: Financial + Export + Write', status: 'active' },
        { phase: 3, label: 'Phase 3: Context attributes', status: 'planned' },
      ],
    },
    alerts: [
      { id: 'a1', severity: 'high',   message: '80% MFA adoption — 1 user without MFA', ts: '2026-03-16T06:00:00Z' },
      { id: 'a2', severity: 'medium', message: '1 user with KYC status PENDING (Marcus Johansson)', ts: '2026-03-15T14:00:00Z' },
      { id: 'a3', severity: 'low',    message: 'ABAC Phase 3 (context attributes) not yet enabled', ts: '2026-03-14T09:00:00Z' },
    ],
  };

  const now = new Date().toLocaleString('en-GB', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });

  return (
    <div className="space-y-5 animate-fade-in">

      {/* ── Header ── */}
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

      {/* ── Top band: score + KPIs ── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-[auto_1fr]">

        {/* Score gauge */}
        <div className="flex items-center justify-center rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-8 py-5 shadow-card">
          <div className="flex flex-col items-center gap-4">
            <ScoreGauge score={d.security_score} label={d.score_label} />
            <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--text-muted)]">
              Security Score
            </div>
          </div>
        </div>

        {/* KPI grid */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <KpiCard label="Total Users"   value={d.kpis.total_users}         icon={Users}     />
          <KpiCard label="MFA Adoption"  value={`${d.kpis.mfa_enabled_pct}%`}
            accent={d.kpis.mfa_enabled_pct === 100 ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'}
            sub="of users enrolled"    icon={Lock}      />
          <KpiCard label="KYC Verified"  value={d.kpis.kyc_verified}
            sub={`${d.kpis.kyc_pending} pending`}
            accent="text-[var(--brand)]"               icon={CheckCircle} />
          <KpiCard label="ABAC Assigned" value={d.kpis.abac_assigned}
            sub={`${d.kpis.abac_unassigned} unassigned`}
            accent="text-[var(--brand)]"               icon={Shield}      />
          <KpiCard label="Events (24 h)" value={d.events_24h.total}
            sub={`${d.events_24h.allow} allow / ${d.events_24h.deny} deny`} icon={Activity}   />
          <KpiCard label="Deny Rate"     value={`${d.events_24h.deny_rate_pct}%`}
            accent={d.events_24h.deny_rate_pct > 30 ? 'text-red-600 dark:text-red-400' : 'text-[var(--text-primary)]'}
            sub="of access requests"   icon={XCircle}   />
        </div>
      </div>

      {/* ── ABAC Phase status ── */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
        <div className="border-b border-[var(--border)] px-5 py-3.5">
          <h2 className="text-sm font-bold text-[var(--text-primary)]">ABAC Policy Implementation</h2>
        </div>
        <div className="divide-y divide-[var(--border)]">
          {d.abac_phase.phases.map(p => (
            <div key={p.phase} className="flex items-center gap-4 px-5 py-3.5">
              <div className={`flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full text-xs font-bold
                ${p.status === 'active'  ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
                : p.status === 'planned' ? 'bg-[var(--surface-hover)] text-[var(--text-muted)]'
                : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'}`}>
                {p.phase}
              </div>
              <div className="flex-1">
                <div className="text-sm font-semibold text-[var(--text-primary)]">{p.label}</div>
              </div>
              <span className={`gex-badge ${p.status === 'active' ? 'gex-badge-green' : p.status === 'planned' ? 'gex-badge-default' : 'gex-badge-amber'}`}>
                {p.status}
              </span>
              {p.phase === d.abac_phase.current && (
                <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300">
                  Current
                </span>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* ── Active Alerts ── */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
        <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-3.5">
          <h2 className="text-sm font-bold text-[var(--text-primary)]">Active Alerts</h2>
          <span className="gex-badge gex-badge-red">{d.alerts.length} open</span>
        </div>
        <div className="divide-y divide-[var(--border)]">
          {d.alerts.map(a => (
            <div key={a.id} className="flex items-start gap-4 px-5 py-3.5">
              <AlertTriangle className={`mt-0.5 w-4 h-4 flex-shrink-0
                ${a.severity === 'high' ? 'text-red-500' : a.severity === 'medium' ? 'text-amber-500' : 'text-[var(--text-muted)]'}`}
              />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-[var(--text-primary)]">{a.message}</p>
                <p className="mt-0.5 text-xs text-[var(--text-muted)]">
                  {new Date(a.ts).toLocaleString('en-GB')}
                </p>
              </div>
              <SeverityBadge severity={a.severity} />
            </div>
          ))}
        </div>
      </div>

      {/* ── Quick links ── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: 'Access Monitor',     path: '/ciso-access-monitor', icon: Eye,          desc: 'Real-time ABAC log' },
          { label: 'Identity & Access',  path: '/ciso-identity',       icon: Users,        desc: 'Manage user attributes' },
          { label: 'Compliance',         path: '/ciso-compliance',     icon: CheckCircle,  desc: 'ISO 27001, SOC 2, GDPR' },
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

      {/* ── Client company selector ── */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
        <div className="border-b border-[var(--border)] px-5 py-3.5 flex items-center gap-2">
          <Building2 className="w-4 h-4 text-[var(--text-muted)]" />
          <h2 className="text-sm font-bold text-[var(--text-primary)]">Client CISO Dashboards</h2>
          <span className="ml-auto gex-badge gex-badge-default">{GEX_COMPANIES.length} companies</span>
        </div>
        <div className="divide-y divide-[var(--border)]">
          {GEX_COMPANIES.map(co => {
            const scoreColor = co.score >= 80 ? 'text-emerald-600 dark:text-emerald-400'
              : co.score >= 65 ? 'text-amber-500' : 'text-red-500'
            return (
              <button
                key={co.id}
                onClick={() => navigate(`/ciso/client/${co.id}`)}
                className="w-full flex items-center gap-4 px-5 py-3.5 hover:bg-[var(--surface-hover)] transition-colors text-left"
              >
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-indigo-100 dark:bg-indigo-900/30">
                  <Shield className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-[var(--text-primary)]">{co.name}</span>
                    {co.iso27001 && (
                      <span className="gex-badge gex-badge-green text-[9px]">
                        <ShieldCheck className="w-2.5 h-2.5 mr-0.5 inline" /> ISO 27001
                      </span>
                    )}
                    {co.alerts > 0 && (
                      <span className="gex-badge gex-badge-red text-[9px]">{co.alerts} alert{co.alerts > 1 ? 's' : ''}</span>
                    )}
                  </div>
                  <p className="text-xs text-[var(--text-muted)]">CISO: {co.ciso} · {co.jurisdiction}</p>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <span className={`font-display text-xl font-extrabold ${scoreColor}`}>{co.score}</span>
                  <ChevronRight className="w-4 h-4 text-[var(--text-muted)]" />
                </div>
              </button>
            )
          })}
        </div>
      </div>

    </div>
  );
}
