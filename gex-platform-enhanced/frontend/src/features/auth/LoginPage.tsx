import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Leaf, Eye, EyeOff, ArrowRight, ChevronRight } from 'lucide-react';
import { useUserRole } from '@/contexts/UserRoleContext';
import type { UserRole } from '@/contexts/UserRoleContext';

// ─── Demo credentials ────────────────────────────────────────────────────────
// Full GEX Ecosystem — sourced from gex_complete_ecosystem.json
// All accounts share password: demo1234
// Each email maps to a real persona, company, and role set.

interface DemoUser {
  role: UserRole;
  token: string;
  title: string;       // job title for display
  group: DemoGroup;
}

type DemoGroup = 'Producers' | 'Offtakers' | 'Bankers' | 'Engineers' | 'Insurers';

const DEMO_USERS: Record<string, DemoUser> = {
  // ── PRODUCERS — HamburgOne.com ─────────────────────────────────────────────
  'lisa.friedrich@hamburgone.com': {
    token: 'demo-token-lisa-friedrich',
    title: 'CEO / CFO · HamburgOne.com',
    group: 'Producers',
    role: {
      company_type: 'PRODUCER',
      service_type: null,
      business_function: 'EXECUTIVE',
      company_name: 'HamburgOne.com',
      user_name: 'Lisa Friedrich',
    },
  },
  'mark.puntz@hamburgone.com': {
    token: 'demo-token-mark-puntz',
    title: 'Chief Engineer · HamburgOne.com',
    group: 'Producers',
    role: {
      company_type: 'PRODUCER',
      service_type: null,
      business_function: 'ENGINEERING',
      company_name: 'HamburgOne.com',
      user_name: 'Mark Puntz',
    },
  },
  'lucie.mertz@hamburgone.com': {
    token: 'demo-token-lucie-mertz',
    title: 'CCO · HamburgOne.com',
    group: 'Producers',
    role: {
      company_type: 'PRODUCER',
      service_type: null,
      business_function: 'COMMERCIAL',
      company_name: 'HamburgOne.com',
      user_name: 'Lucie Mertz',
    },
  },
  // ── PRODUCERS — Madrid2.com ────────────────────────────────────────────────
  'diego.martinez@madrid2.com': {
    token: 'demo-token-diego-martinez',
    title: 'CEO · Madrid2.com',
    group: 'Producers',
    role: {
      company_type: 'PRODUCER',
      service_type: null,
      business_function: 'EXECUTIVE',
      company_name: 'Madrid2.com',
      user_name: 'Diego Martinez',
    },
  },
  'claudia.nunez@madrid2.com': {
    token: 'demo-token-claudia-nunez',
    title: 'CCO · Madrid2.com',
    group: 'Producers',
    role: {
      company_type: 'PRODUCER',
      service_type: null,
      business_function: 'COMMERCIAL',
      company_name: 'Madrid2.com',
      user_name: 'Claudia Nunez',
    },
  },
  // ── OFFTAKERS ──────────────────────────────────────────────────────────────
  'karl.tish@brementhree.com': {
    token: 'demo-token-karl-tish',
    title: 'CEO · BremenThree AG',
    group: 'Offtakers',
    role: {
      company_type: 'OFFTAKER',
      service_type: null,
      business_function: 'EXECUTIVE',
      company_name: 'BremenThree AG',
      user_name: 'Karl Tish',
    },
  },
  'frank.sabak@brementhree.com': {
    token: 'demo-token-frank-sabak',
    title: 'Purchasing · BremenThree AG',
    group: 'Offtakers',
    role: {
      company_type: 'OFFTAKER',
      service_type: null,
      business_function: 'COMMERCIAL',
      company_name: 'BremenThree AG',
      user_name: 'Frank Sabak',
    },
  },
  'luc.marchand@rotterdamofftake4.com': {
    token: 'demo-token-luc-marchand',
    title: 'CFO · RotterdamOfftake4 AG',
    group: 'Offtakers',
    role: {
      company_type: 'OFFTAKER',
      service_type: null,
      business_function: 'FINANCE_TREASURY',
      company_name: 'RotterdamOfftake4 AG',
      user_name: 'Luc Marchand',
    },
  },
  // ── BANKERS ────────────────────────────────────────────────────────────────
  'henrik.vost@nordlb.com': {
    token: 'demo-token-henrik-vost',
    title: 'Project Finance · NordLB',
    group: 'Bankers',
    role: {
      company_type: 'THIRD_PARTY',
      service_type: 'BANK',
      business_function: 'FINANCE_TREASURY',
      company_name: 'NordLB',
      user_name: 'Henrik Vost',
    },
  },
  'sander.devries@abnamro.com': {
    token: 'demo-token-sander-devries',
    title: 'Structured Lending · ABN-AMRO',
    group: 'Bankers',
    role: {
      company_type: 'THIRD_PARTY',
      service_type: 'BANK',
      business_function: 'FINANCE_TREASURY',
      company_name: 'ABN-AMRO',
      user_name: 'Sander de Vries',
    },
  },
  // ── ENGINEERS ──────────────────────────────────────────────────────────────
  'olaf.jacques@siemens-energy.com': {
    token: 'demo-token-olaf-jacques',
    title: 'Process Engineer · Siemens Energy',
    group: 'Engineers',
    role: {
      company_type: 'THIRD_PARTY',
      service_type: 'ENGINEER',
      business_function: 'ENGINEERING',
      company_name: 'Siemens Energy',
      user_name: 'Olaf Jacques',
    },
  },
  // ── INSURERS ───────────────────────────────────────────────────────────────
  'florian.schmidt@allianz.com': {
    token: 'demo-token-florian-schmidt',
    title: 'Risk Engineer · Allianz',
    group: 'Insurers',
    role: {
      company_type: 'THIRD_PARTY',
      service_type: 'INSURER',
      business_function: 'FINANCE_TREASURY',
      company_name: 'Allianz',
      user_name: 'Florian Schmidt',
    },
  },
  'phillipe.blanker@zurich.com': {
    token: 'demo-token-phillipe-blanker',
    title: 'Underwriter · Zürich Versicherung AG',
    group: 'Insurers',
    role: {
      company_type: 'THIRD_PARTY',
      service_type: 'INSURER',
      business_function: 'FINANCE_TREASURY',
      company_name: 'Zürich Versicherung AG',
      user_name: 'Phillipe Blanker',
    },
  },
};

const DEMO_PASSWORD = 'demo1234';

// ─── Group metadata ───────────────────────────────────────────────────────────
const GROUP_META: Record<DemoGroup, { label: string }> = {
  Producers: { label: 'Producers' },
  Offtakers: { label: 'Offtakers' },
  Bankers: { label: 'Banks' },
  Engineers: { label: 'Engineering' },
  Insurers: { label: 'Insurance' },
};

// ─── Component ───────────────────────────────────────────────────────────────

export function LoginPage() {
  const { login, continueAsGuest } = useUserRole();
  const navigate = useNavigate();

  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd]   = useState(false);
  const [error, setError]       = useState('');
  const [loading, setLoading]   = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    // Simulate network latency
    await new Promise((r) => setTimeout(r, 600));

    const match = DEMO_USERS[email.toLowerCase()];
    if (!match || password !== DEMO_PASSWORD) {
      setError('Invalid credentials. Use one of the demo accounts below with password demo1234.');
      setLoading(false);
      return;
    }

    login({ token: match.token, email }, match.role);
    navigate('/dashboard');
  };

  const handleGuest = () => {
    continueAsGuest();
    navigate('/');
  };

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[1.05fr_0.95fr]" style={{ background: 'var(--bg)' }}>
      {/* ── Left panel — branding ───────────────────────────────── */}
      <div
        className="hidden lg:flex flex-col justify-between p-14 border-r"
        style={{ background: 'var(--surface-muted)', borderColor: 'var(--border)' }}
      >
        {/* Logo */}
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-xl border flex items-center justify-center"
            style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
          >
            <Leaf className="w-5 h-5" style={{ color: 'var(--brand)' }} />
          </div>
          <span className="text-lg font-semibold tracking-[0.18em]" style={{ color: 'var(--text-primary)' }}>
            GreenEarthX
          </span>
        </div>

        {/* Headline */}
        <div className="max-w-xl">
          <div
            className="inline-flex items-center gap-2 rounded-full border px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.16em] mb-8"
            style={{ background: 'var(--surface)', borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
          >
            Decision Infrastructure for Green Fuels
          </div>
          <h1 className="text-[3.2rem] font-semibold leading-[1.05] mb-6" style={{ color: 'var(--text-primary)' }}>
            The operating system
            <br />
            for green fuel finance.
          </h1>
          <p className="text-[1.05rem] leading-8 max-w-lg" style={{ color: 'var(--text-secondary)' }}>
            Bankability assessment, capital structuring, and compliance
            for H₂, NH₃, SAF and e-MeOH projects — from speculative to
            financial close.
          </p>

          {/* Stats row */}
          <div className="grid grid-cols-3 gap-4 mt-14">
            {[
              { value: '12', label: 'Bankability Gates' },
              { value: '9', label: 'Lifecycle States' },
              { value: '4', label: 'Fuel Molecules' },
            ].map(({ value, label }) => (
              <div
                key={label}
                className="rounded-2xl border p-5"
                style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
              >
                <div className="text-3xl font-semibold" style={{ color: 'var(--text-primary)' }}>{value}</div>
                <div className="text-[11px] mt-2 uppercase tracking-[0.14em]" style={{ color: 'var(--text-muted)' }}>
                  {label}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          © {new Date().getFullYear()} GreenEarthX · Proprietary
        </p>
      </div>

      {/* ── Right panel — login form ─────────────────────────────── */}
      <div className="flex items-center justify-center px-6 py-10 lg:px-10">
        <div
          className="w-full max-w-md rounded-[28px] border p-7 sm:p-9"
          style={{
            background: 'var(--surface)',
            borderColor: 'var(--border)',
            boxShadow: '0 18px 40px rgba(22, 33, 29, 0.06)',
          }}
        >
          {/* Mobile logo */}
          <div className="flex items-center gap-2 mb-10 lg:hidden">
            <div
              className="w-9 h-9 rounded-xl border flex items-center justify-center"
              style={{ background: 'var(--surface-muted)', borderColor: 'var(--border)' }}
            >
              <Leaf className="w-4 h-4" style={{ color: 'var(--brand)' }} />
            </div>
            <span className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>GreenEarthX</span>
          </div>

          <h2 className="text-3xl font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>Welcome back</h2>
          <p className="text-sm mb-8" style={{ color: 'var(--text-secondary)' }}>
            Sign in to your GEX platform account.
          </p>

          <form onSubmit={handleLogin} className="space-y-5">
            {/* Email */}
            <div>
              <label className="block text-xs font-medium mb-1.5 uppercase tracking-[0.14em]" style={{ color: 'var(--text-muted)' }}>
                Email address
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                required
                className="w-full border rounded-xl px-4 py-3
                           text-sm placeholder-gray-400
                           focus:outline-none focus:ring-4
                           transition-colors"
                style={{
                  background: 'var(--surface-muted)',
                  borderColor: 'var(--border)',
                  color: 'var(--text-primary)',
                }}
              />
            </div>

            {/* Password */}
            <div>
              <label className="block text-xs font-medium mb-1.5 uppercase tracking-[0.14em]" style={{ color: 'var(--text-muted)' }}>
                Password
              </label>
              <div className="relative">
                <input
                  type={showPwd ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  className="w-full border rounded-xl px-4 py-3 pr-10
                             text-sm placeholder-gray-400
                             focus:outline-none focus:ring-4
                             transition-colors"
                  style={{
                    background: 'var(--surface-muted)',
                    borderColor: 'var(--border)',
                    color: 'var(--text-primary)',
                  }}
                />
                <button
                  type="button"
                  onClick={() => setShowPwd((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 transition-colors"
                  style={{ color: 'var(--text-muted)' }}
                >
                  {showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Error */}
            {error && (
              <p className="text-xs rounded-xl px-3 py-2.5" style={{ color: '#9c3c32', background: '#f6e9e6', border: '1px solid #e6c8c2' }}>
                {error}
              </p>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2
                         text-white font-medium text-sm rounded-xl py-3
                         transition-colors"
              style={{ background: '#16211d' }}
            >
              {loading ? (
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <>Sign in <ArrowRight className="w-4 h-4" /></>
              )}
            </button>
          </form>

          {/* Divider */}
          <div className="flex items-center gap-3 my-6">
            <div className="flex-1 h-px" style={{ background: 'var(--border)' }} />
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>or</span>
            <div className="flex-1 h-px" style={{ background: 'var(--border)' }} />
          </div>

          {/* Guest access */}
          <button
            onClick={handleGuest}
            className="w-full flex items-center justify-center gap-2
                       border text-sm font-medium
                       rounded-xl py-3 transition-colors"
            style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
          >
            Explore as Guest
            <ChevronRight className="w-4 h-4" />
          </button>
          <p className="text-center text-xs mt-3" style={{ color: 'var(--text-muted)' }}>
            Guest access shows public content only. No project data or scores visible.
          </p>

          {/* Demo accounts — grouped by role */}
          <div className="mt-8 rounded-2xl border overflow-hidden" style={{ borderColor: 'var(--border)', background: 'var(--surface-muted)' }}>
            <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: 'var(--border)' }}>
              <p className="text-xs font-bold uppercase tracking-[0.16em]" style={{ color: 'var(--text-secondary)' }}>Demo Accounts</p>
              <code className="text-xs" style={{ color: 'var(--text-muted)' }}>pw: demo1234</code>
            </div>
            <div>
              {(Object.keys(GROUP_META) as DemoGroup[]).map((group) => {
                const { label } = GROUP_META[group];
                const members = Object.entries(DEMO_USERS).filter(([, u]) => u.group === group);
                return (
                  <div key={group} className="px-4 py-3" style={{ borderTop: '1px solid var(--border)' }}>
                    <p className="text-[11px] font-semibold mb-2 uppercase tracking-[0.14em]" style={{ color: 'var(--text-muted)' }}>
                      {label}
                    </p>
                    <div className="space-y-1">
                      {members.map(([emailAddr, user]) => (
                        <button
                          key={emailAddr}
                          type="button"
                          onClick={() => { setEmail(emailAddr); setPassword(DEMO_PASSWORD); }}
                          className="w-full flex items-center justify-between gap-3 px-3 py-2.5 rounded-xl text-left group transition-colors"
                          style={{ background: 'var(--surface)' }}
                        >
                          <div className="min-w-0">
                            <div className="text-xs font-semibold truncate" style={{ color: 'var(--text-primary)' }}>
                              {user.role.user_name}
                            </div>
                            <div className="text-xs truncate" style={{ color: 'var(--text-muted)' }}>{user.title}</div>
                          </div>
                          <span className="text-xs font-mono shrink-0 transition-colors" style={{ color: 'var(--brand)' }}>
                            fill →
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default LoginPage;
