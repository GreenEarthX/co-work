import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Leaf, Eye, EyeOff, ArrowRight, ChevronRight } from 'lucide-react';
import { useUserRole } from '@/contexts/UserRoleContext';
import type { UserRole } from '@/contexts/UserRoleContext';

// ─── Demo credentials ────────────────────────────────────────────────────────
// In production these would be verified server-side (JWT returned).
// For now the demo accepts any email + password "demo1234" and maps
// a role based on the email domain.
const DEMO_USERS: Record<string, { role: UserRole; token: string }> = {
  'producer@greenearthx.com': {
    token: 'demo-token-producer',
    role: {
      company_type: 'PRODUCER',
      service_type: null,
      business_function: 'FINANCE_TREASURY',
      company_name: 'GreenEarthX',
      user_name: 'Producer Demo',
      company_logo_url: undefined,
    },
  },
  'banker@bp.com': {
    token: 'demo-token-banker',
    role: {
      company_type: 'THIRD_PARTY',
      service_type: 'BANK',
      business_function: 'FINANCE_TREASURY',
      company_name: 'BP Energy',
      user_name: 'Banker Demo',
      company_logo_url: undefined,
    },
  },
  'regulator@gov.eu': {
    token: 'demo-token-regulator',
    role: {
      company_type: 'THIRD_PARTY',
      service_type: 'CERTIFIER',
      business_function: 'COMPLIANCE_LEGAL',
      company_name: 'EU Regulatory Body',
      user_name: 'Regulator Demo',
      company_logo_url: undefined,
    },
  },
};

const DEMO_PASSWORD = 'demo1234';

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
      setError('Invalid email or password. Try demo1234 as password.');
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
    <div className="min-h-screen bg-gray-950 flex">
      {/* ── Left panel — branding ───────────────────────────────── */}
      <div className="hidden lg:flex lg:w-1/2 bg-gradient-to-br from-teal-900 via-gray-900 to-gray-950 flex-col justify-between p-12">
        {/* Logo */}
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-teal-500 flex items-center justify-center">
            <Leaf className="w-5 h-5 text-white" />
          </div>
          <span className="text-xl font-bold text-white tracking-wide">GreenEarthX</span>
        </div>

        {/* Headline */}
        <div>
          <h1 className="text-4xl font-bold text-white leading-tight mb-6">
            The operating system<br />
            for green fuel finance.
          </h1>
          <p className="text-teal-200/70 text-lg leading-relaxed max-w-md">
            Bankability assessment, capital structuring, and compliance
            for H₂, NH₃, SAF and e-MeOH projects — from speculative to
            financial close.
          </p>

          {/* Stats row */}
          <div className="flex gap-10 mt-12">
            {[
              { value: '12', label: 'Bankability Gates' },
              { value: '9', label: 'Lifecycle States' },
              { value: '4', label: 'Fuel Molecules' },
            ].map(({ value, label }) => (
              <div key={label}>
                <div className="text-3xl font-bold text-teal-400">{value}</div>
                <div className="text-xs text-gray-400 mt-1 uppercase tracking-wider">{label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <p className="text-xs text-gray-600">
          © {new Date().getFullYear()} GreenEarthX · Proprietary
        </p>
      </div>

      {/* ── Right panel — login form ─────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-md">
          {/* Mobile logo */}
          <div className="flex items-center gap-2 mb-10 lg:hidden">
            <div className="w-8 h-8 rounded-md bg-teal-500 flex items-center justify-center">
              <Leaf className="w-4 h-4 text-white" />
            </div>
            <span className="text-lg font-bold text-white">GreenEarthX</span>
          </div>

          <h2 className="text-2xl font-bold text-white mb-1">Welcome back</h2>
          <p className="text-gray-400 text-sm mb-8">Sign in to your GEX platform account.</p>

          <form onSubmit={handleLogin} className="space-y-5">
            {/* Email */}
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5 uppercase tracking-wider">
                Email address
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                required
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5
                           text-sm text-white placeholder-gray-600
                           focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500/40
                           transition-colors"
              />
            </div>

            {/* Password */}
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5 uppercase tracking-wider">
                Password
              </label>
              <div className="relative">
                <input
                  type={showPwd ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 pr-10
                             text-sm text-white placeholder-gray-600
                             focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500/40
                             transition-colors"
                />
                <button
                  type="button"
                  onClick={() => setShowPwd((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
                >
                  {showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Error */}
            {error && (
              <p className="text-xs text-red-400 bg-red-900/20 border border-red-800/40 rounded-lg px-3 py-2">
                {error}
              </p>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2
                         bg-teal-600 hover:bg-teal-500 disabled:bg-teal-900
                         text-white font-medium text-sm rounded-lg py-2.5
                         transition-colors"
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
            <div className="flex-1 h-px bg-gray-800" />
            <span className="text-xs text-gray-600">or</span>
            <div className="flex-1 h-px bg-gray-800" />
          </div>

          {/* Guest access */}
          <button
            onClick={handleGuest}
            className="w-full flex items-center justify-center gap-2
                       border border-gray-700 hover:border-gray-500
                       text-gray-400 hover:text-gray-200 text-sm font-medium
                       rounded-lg py-2.5 transition-colors"
          >
            Explore as Guest
            <ChevronRight className="w-4 h-4" />
          </button>
          <p className="text-center text-xs text-gray-600 mt-3">
            Guest access shows public content only. No project data or scores visible.
          </p>

          {/* Demo credentials hint */}
          <div className="mt-8 p-4 bg-gray-900 rounded-lg border border-gray-800">
            <p className="text-xs text-gray-500 font-medium mb-2 uppercase tracking-wider">Demo accounts</p>
            <div className="space-y-1">
              {Object.keys(DEMO_USERS).map((e) => (
                <button
                  key={e}
                  type="button"
                  onClick={() => { setEmail(e); setPassword(DEMO_PASSWORD); }}
                  className="block w-full text-left text-xs text-teal-400/70 hover:text-teal-400
                             font-mono transition-colors"
                >
                  {e}
                </button>
              ))}
            </div>
            <p className="text-xs text-gray-600 mt-2">Password: <code className="text-gray-500">demo1234</code></p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default LoginPage;
