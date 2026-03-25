import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Leaf, ArrowRight, CheckCircle, Lock, Zap, Globe, BarChart2,
  ShieldCheck, TrendingUp, FileText, LogIn,
} from 'lucide-react';

// ─── Static guest-visible content ────────────────────────────────────────────
// The CISO controls which of these blocks are shown via guest policy.
// For now they are hard-coded to the defaults in DEFAULT_GUEST_POLICY.

const GATES = [
  { id: 'G0', label: 'Site Rights & Social License', visible: true },
  { id: 'G1', label: 'Grid Connection & Utilities',  visible: true },
  { id: 'G2', label: 'Green Certification Pathway',  visible: true },
  { id: 'G3', label: 'Feedstock & Logistics',        visible: true },
  { id: 'G4', label: 'Binding Offtake',              visible: false },
  { id: 'G5', label: 'EPC & Construction',           visible: true },
  { id: 'G6', label: 'Independent Engineer',         visible: false },
  { id: 'G7', label: 'Insurance Package',            visible: false },
  { id: 'G8', label: 'Audit-Grade Financial Model',  visible: false },
  { id: 'G9', label: 'Permits & Approvals',          visible: true },
  { id: 'G10', label: 'Financial Close',             visible: false },
  { id: 'G11', label: 'Commercial Operations Date',  visible: false },
];

const MOLECULES = [
  { label: 'Green Hydrogen',       formula: 'H₂',    color: 'from-sky-600 to-sky-800' },
  { label: 'Green Ammonia',        formula: 'NH₃',   color: 'from-violet-600 to-violet-800' },
  { label: 'Sustainable Aviation', formula: 'SAF',   color: 'from-amber-600 to-amber-800' },
  { label: 'e-Methanol',           formula: 'e-MeOH', color: 'from-teal-600 to-teal-800' },
];

const BENEFITS = [
  { icon: <BarChart2 className="w-5 h-5" />,  title: 'Bankability Assessment',    body: '12-gate lifecycle engine from speculative to financial close.' },
  { icon: <TrendingUp className="w-5 h-5" />, title: 'Capital Stack Modelling',   body: 'DSCR-sculpted debt, waterfall analysis, covenant tracking.' },
  { icon: <ShieldCheck className="w-5 h-5" />,title: 'Compliance & Certification',body: 'RED III, 45V, and custom green certification pathway.' },
  { icon: <FileText className="w-5 h-5" />,   title: 'IC Pack & Deal Room',       body: 'Export-ready investment committee packs with audit trail.' },
];

// ─── Component ───────────────────────────────────────────────────────────────

export function GuestLandingPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gray-950 text-white">

      {/* ── Top nav (guest version) ───────────────────────────── */}
      <header className="h-12 bg-gray-900 border-b border-gray-800 flex items-center px-6 sticky top-0 z-40">
        <div className="flex items-center gap-2 flex-1">
          <div className="w-7 h-7 rounded-md bg-teal-600 flex items-center justify-center">
            <Leaf className="w-4 h-4 text-white" />
          </div>
          <span className="text-sm font-bold text-gray-200 tracking-wide">GreenEarthX</span>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500 bg-gray-800 px-2 py-1 rounded">
            Guest — limited view
          </span>
          <button
            onClick={() => navigate('/login')}
            className="flex items-center gap-1.5 text-xs text-teal-400 hover:text-teal-300
                       border border-teal-800 hover:border-teal-600 rounded-lg px-3 py-1.5 transition-colors"
          >
            <LogIn className="w-3.5 h-3.5" />
            Sign in
          </button>
        </div>
      </header>

      {/* ── Hero ─────────────────────────────────────────────── */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-teal-950/60 via-gray-950 to-gray-950 pointer-events-none" />
        <div className="relative max-w-5xl mx-auto px-6 pt-20 pb-16 text-center">
          <div className="inline-flex items-center gap-2 bg-teal-900/30 border border-teal-800/50
                          rounded-full px-4 py-1.5 text-xs text-teal-300 mb-6">
            <Zap className="w-3.5 h-3.5" />
            Green Fuel Project Finance Platform
          </div>

          <h1 className="text-5xl font-bold leading-tight mb-6 max-w-3xl mx-auto">
            Is your green fuel project
            <span className="text-teal-400"> bankable?</span>
          </h1>
          <p className="text-lg text-gray-400 max-w-2xl mx-auto mb-10 leading-relaxed">
            GreenEarthX evaluates H₂, NH₃, SAF and e-MeOH projects against
            12 bankability gates — giving producers, banks, and regulators a
            shared language from speculative to financial close.
          </p>

          {/* ── PRIMARY CTA — Project Viability Teaser ── */}
          <div className="bg-gray-900 border border-teal-800/50 rounded-2xl p-8 max-w-2xl mx-auto
                          shadow-[0_0_40px_rgba(20,184,166,0.08)]">
            <div className="flex items-center gap-2 mb-2">
              <Globe className="w-5 h-5 text-teal-400" />
              <span className="text-sm font-semibold text-teal-300 uppercase tracking-wider">
                Free Assessment
              </span>
            </div>
            <h2 className="text-2xl font-bold text-white mb-3">
              Planning a New Project?
            </h2>
            <p className="text-gray-400 text-sm leading-relaxed mb-6">
              Answer 4 sets of questions — molecule, economics, certification pathway —
              and receive an instant bankability viability report. No account required.
            </p>

            <div className="flex flex-col sm:flex-row gap-3">
              <button
                onClick={() => navigate('/onboarding')}
                className="flex-1 flex items-center justify-center gap-2
                           bg-teal-600 hover:bg-teal-500 text-white font-semibold
                           rounded-xl py-3 px-6 transition-colors text-sm"
              >
                Start Project Viability Check
                <ArrowRight className="w-4 h-4" />
              </button>
              <button
                onClick={() => navigate('/login')}
                className="flex items-center justify-center gap-2
                           border border-gray-700 hover:border-gray-500
                           text-gray-300 hover:text-white font-medium
                           rounded-xl py-3 px-5 transition-colors text-sm"
              >
                <LogIn className="w-4 h-4" />
                Sign in for full access
              </button>
            </div>

            {/* Step indicators */}
            <div className="flex items-center justify-center gap-2 mt-5">
              {['Molecule & Site', 'Economics', 'Certification', 'Report'].map((step, i) => (
                <React.Fragment key={step}>
                  <div className="flex flex-col items-center gap-1">
                    <div className="w-6 h-6 rounded-full bg-teal-900 border border-teal-700
                                    flex items-center justify-center text-xs text-teal-400 font-bold">
                      {i + 1}
                    </div>
                    <span className="text-[10px] text-gray-500 hidden sm:block">{step}</span>
                  </div>
                  {i < 3 && <div className="w-6 h-px bg-gray-700 mb-3" />}
                </React.Fragment>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── Molecule pills ────────────────────────────────────── */}
      <section className="max-w-5xl mx-auto px-6 py-10">
        <p className="text-center text-xs text-gray-500 uppercase tracking-widest mb-6">
          Supported molecules
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {MOLECULES.map(({ label, formula, color }) => (
            <div key={formula}
                 className={`bg-gradient-to-br ${color} rounded-xl p-5 text-center`}>
              <div className="text-2xl font-bold text-white mb-1">{formula}</div>
              <div className="text-xs text-white/70">{label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── 12-Gate overview (blurred locked gates) ───────────── */}
      <section className="max-w-5xl mx-auto px-6 py-10">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-lg font-bold text-white">12 Bankability Gates</h3>
            <p className="text-xs text-gray-500 mt-1">
              Sign in to see your project's gate scores and evidence requirements.
            </p>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-gray-500">
            <Lock className="w-3.5 h-3.5" />
            Scores visible after sign-in
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {GATES.map(({ id, label, visible }) => (
            <div
              key={id}
              className={`flex items-center gap-3 rounded-lg border px-4 py-3
                          ${visible
                            ? 'bg-gray-900 border-gray-800'
                            : 'bg-gray-900/40 border-gray-800/40'}`}
            >
              <span className={`text-xs font-mono font-bold w-7
                               ${visible ? 'text-teal-400' : 'text-gray-600'}`}>
                {id}
              </span>
              {visible ? (
                <span className="text-sm text-gray-300 flex-1">{label}</span>
              ) : (
                <span className="text-sm text-gray-600 flex-1 blur-[3px] select-none">{label}</span>
              )}
              {visible
                ? <CheckCircle className="w-4 h-4 text-teal-600 flex-shrink-0" />
                : <Lock className="w-3.5 h-3.5 text-gray-700 flex-shrink-0" />
              }
            </div>
          ))}
        </div>
      </section>

      {/* ── Platform benefits ─────────────────────────────────── */}
      <section className="max-w-5xl mx-auto px-6 py-10">
        <h3 className="text-lg font-bold text-white mb-6 text-center">
          Full platform — available after sign-in
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {BENEFITS.map(({ icon, title, body }) => (
            <div key={title}
                 className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-8 h-8 rounded-lg bg-teal-900/50 border border-teal-800/50
                                flex items-center justify-center text-teal-400">
                  {icon}
                </div>
                <span className="font-semibold text-sm text-white">{title}</span>
              </div>
              <p className="text-xs text-gray-400 leading-relaxed">{body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Bottom CTA ────────────────────────────────────────── */}
      <section className="max-w-5xl mx-auto px-6 py-16 text-center">
        <h3 className="text-2xl font-bold text-white mb-3">Ready to assess your project?</h3>
        <p className="text-gray-400 text-sm mb-8">
          No commitment required — run a free viability check in under 5 minutes.
        </p>
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <button
            onClick={() => navigate('/onboarding')}
            className="flex items-center justify-center gap-2
                       bg-teal-600 hover:bg-teal-500 text-white font-semibold
                       rounded-xl py-3 px-8 transition-colors"
          >
            Start Project Viability Check
            <ArrowRight className="w-4 h-4" />
          </button>
          <button
            onClick={() => navigate('/login')}
            className="flex items-center justify-center gap-2
                       border border-gray-700 hover:border-gray-500
                       text-gray-300 hover:text-white font-medium
                       rounded-xl py-3 px-6 transition-colors"
          >
            <LogIn className="w-4 h-4" />
            Sign in to existing account
          </button>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-gray-800 py-6 text-center text-xs text-gray-600">
        © {new Date().getFullYear()} GreenEarthX · Proprietary · All rights reserved
      </footer>
    </div>
  );
}

export default GuestLandingPage;
