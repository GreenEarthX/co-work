// Screen: Guest landing screen (/)
import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowRight, CheckCircle, Lock, Zap, Globe, BarChart2,
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
  { label: 'Green Hydrogen', formula: 'H₂' },
  { label: 'Green Ammonia', formula: 'NH₃' },
  { label: 'Sustainable Aviation', formula: 'SAF' },
  { label: 'e-Methanol', formula: 'e-MeOH' },
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
    <div className="min-h-screen" style={{ background: 'var(--bg)', color: 'var(--text-primary)' }}>

      {/* ── Top nav (guest version) ───────────────────────────── */}
      <header
        className="h-20 border-b flex items-center px-6 sticky top-0 z-40 backdrop-blur"
        style={{ background: 'rgba(243, 244, 242, 0.94)', borderColor: 'var(--border)' }}
      >
        <div className="flex items-center gap-2 flex-1">
          <img
            src="/GreenEarthX-updated.png"
            alt="GreenEarthX"
            className="h-12 w-auto object-contain sm:h-14"
          />
        </div>

        <div className="flex items-center gap-3">
          <span
            className="text-xs px-3 py-1.5 rounded-full border"
            style={{ color: 'var(--text-secondary)', background: 'var(--surface)', borderColor: 'var(--border)' }}
          >
            Guest — limited view
          </span>
          <button
            onClick={() => navigate('/login')}
            className="flex items-center gap-1.5 text-xs rounded-lg px-3 py-2 transition-colors border"
            style={{ color: 'var(--text-primary)', background: 'var(--surface)', borderColor: 'var(--border)' }}
          >
            <LogIn className="w-3.5 h-3.5" />
            Sign in
          </button>
        </div>
      </header>

      {/* ── Hero ─────────────────────────────────────────────── */}
      <section className="relative overflow-hidden">
        <div
          className="absolute inset-0 pointer-events-none"
          style={{ background: 'radial-gradient(circle at top, rgba(15, 118, 110, 0.08), transparent 42%)' }}
        />
        <div className="relative max-w-6xl mx-auto px-6 pt-24 pb-18 text-center">
          <div
            className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.16em] mb-7 border"
            style={{ background: 'var(--surface)', borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
          >
            <Zap className="w-3.5 h-3.5" />
            Green Fuel Project Orchestration Software
          </div>

          <h1 className="text-5xl sm:text-6xl font-semibold leading-[1.02] mb-6 max-w-4xl mx-auto">
            Make your green fuel project a
            <span style={{ color: 'var(--brand)' }}> Success</span>
          </h1>
          <p className="text-lg max-w-2xl mx-auto mb-12 leading-8" style={{ color: 'var(--text-secondary)' }}>
            GreenEarthX evaluates green molecules projects against
            12 bankability gates — giving producers, banks, insurers, certifiersand regulators a
            shared language from inception to COD via financial close.
          </p>

          {/* ── PRIMARY CTA — Project Viability Teaser ── */}
          <div
            className="rounded-[28px] p-8 sm:p-10 max-w-3xl mx-auto border text-left"
            style={{
              background: 'var(--surface)',
              borderColor: 'var(--border)',
              boxShadow: '0 24px 60px rgba(22, 33, 29, 0.06)',
            }}
          >
            <div className="flex items-center gap-2 mb-2">
              <Globe className="w-5 h-5" style={{ color: 'var(--brand)' }} />
              <span className="text-sm font-semibold uppercase tracking-[0.14em]" style={{ color: 'var(--text-secondary)' }}>
                Free Assessment
              </span>
            </div>
            <h2 className="text-3xl font-semibold mb-3">
              Planning a New Project?
            </h2>
            <p className="text-sm leading-7 mb-7" style={{ color: 'var(--text-secondary)' }}>
              Answer 4 sets of questions — molecule, economics, certification pathway —
              and receive an instant bankability viability report. No account required.
            </p>

            <div className="flex flex-col sm:flex-row gap-3">
              <button
                onClick={() => navigate('/onboarding')}
                className="flex-1 flex items-center justify-center gap-2
                           text-white font-semibold rounded-xl py-3.5 px-6 transition-colors text-sm"
                style={{ background: '#16211d' }}
              >
                Start Project Viability Check
                <ArrowRight className="w-4 h-4" />
              </button>
              <button
                onClick={() => navigate('/login')}
                className="flex items-center justify-center gap-2
                           border font-medium rounded-xl py-3.5 px-5 transition-colors text-sm"
                style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
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
                    <div
                      className="w-7 h-7 rounded-full border flex items-center justify-center text-xs font-bold"
                      style={{ background: 'var(--surface-muted)', borderColor: 'var(--border)', color: 'var(--brand)' }}
                    >
                      {i + 1}
                    </div>
                    <span className="text-[10px] hidden sm:block" style={{ color: 'var(--text-muted)' }}>{step}</span>
                  </div>
                  {i < 3 && <div className="w-8 h-px mb-3" style={{ background: 'var(--border)' }} />}
                </React.Fragment>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── Molecule pills ────────────────────────────────────── */}
      <section className="max-w-5xl mx-auto px-6 py-10">
        <p className="text-center text-xs uppercase tracking-[0.18em] mb-6" style={{ color: 'var(--text-muted)' }}>
          Supported molecules
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {MOLECULES.map(({ label, formula }) => (
            <div
              key={formula}
              className="rounded-2xl border p-5 text-center"
              style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
            >
              <div className="text-2xl font-semibold mb-1">{formula}</div>
              <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>{label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── 12-Gate overview (blurred locked gates) ───────────── */}
      <section className="max-w-5xl mx-auto px-6 py-10">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-lg font-semibold">12 Bankability Gates</h3>
            <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
              Sign in to see your project's gate scores and evidence requirements.
            </p>
          </div>
          <div className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--text-muted)' }}>
            <Lock className="w-3.5 h-3.5" />
            Scores visible as you sign-in
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {GATES.map(({ id, label, visible }) => (
            <div
              key={id}
              className="flex items-center gap-3 rounded-xl border px-4 py-3"
              style={{
                background: visible ? 'var(--surface)' : 'var(--surface-muted)',
                borderColor: 'var(--border)',
              }}
            >
              <span
                className="text-xs font-mono font-bold w-7"
                style={{ color: visible ? 'var(--brand)' : 'var(--text-muted)' }}
              >
                {id}
              </span>
              {visible ? (
                <span className="text-sm flex-1" style={{ color: 'var(--text-primary)' }}>{label}</span>
              ) : (
                <span className="text-sm flex-1 blur-[2px] select-none" style={{ color: 'var(--text-muted)' }}>{label}</span>
              )}
              {visible
                ? <CheckCircle className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--brand)' }} />
                : <Lock className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--text-muted)' }} />
              }
            </div>
          ))}
        </div>
      </section>

      {/* ── Platform benefits ─────────────────────────────────── */}
      <section className="max-w-5xl mx-auto px-6 py-10">
        <h3 className="text-lg font-semibold mb-6 text-center">
          Full platform — available after sign-in
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {BENEFITS.map(({ icon, title, body }) => (
            <div key={title}
                 className="rounded-2xl border p-5"
                 style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}>
              <div className="flex items-center gap-3 mb-2">
                <div
                  className="w-8 h-8 rounded-lg border flex items-center justify-center"
                  style={{ background: 'var(--surface-muted)', borderColor: 'var(--border)', color: 'var(--brand)' }}
                >
                  {icon}
                </div>
                <span className="font-semibold text-sm">{title}</span>
              </div>
              <p className="text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Bottom CTA ────────────────────────────────────────── */}
      <section className="max-w-5xl mx-auto px-6 py-16 text-center">
        <h3 className="text-2xl font-semibold mb-3">Ready to assess your project?</h3>
        <p className="text-sm mb-8" style={{ color: 'var(--text-secondary)' }}>
          No commitment required — run a free viability check in under 5 minutes.
        </p>
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <button
            onClick={() => navigate('/onboarding')}
            className="flex items-center justify-center gap-2
                       text-white font-semibold rounded-xl py-3 px-8 transition-colors"
            style={{ background: '#16211d' }}
          >
            Start Project Viability Check
            <ArrowRight className="w-4 h-4" />
          </button>
          <button
            onClick={() => navigate('/login')}
            className="flex items-center justify-center gap-2
                       border font-medium rounded-xl py-3 px-6 transition-colors"
            style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
          >
            <LogIn className="w-4 h-4" />
            Sign in to existing account
          </button>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t py-6 text-center text-xs" style={{ borderColor: 'var(--border)', color: 'var(--text-muted)' }}>
        © {new Date().getFullYear()} GreenEarthX · Proprietary · All rights reserved
      </footer>
    </div>
  );
}

export default GuestLandingPage;
