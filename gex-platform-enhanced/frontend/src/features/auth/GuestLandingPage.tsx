// Screen: Guest landing screen (/)
//
// Dark treatment ("Direction D"). Two ordering rules, both deliberate:
//   BREADTH first  — "What GEX orchestrates" says what the platform spans.
//   PROOF second   — the gate ladder shows how readiness is judged.
// The ladder used to lead, which framed GEX as a project-readiness tool rather
// than market infrastructure, and spoke in GEX's internal vocabulary — nobody
// arrives thinking "I need G4".
//
// Research & market insight sits last, immediately above the footer.
//
// Colours are local constants rather than the app's CSS variables: this is the
// one dark screen in a light application, and hard-coding it here keeps the
// global theme untouched. Previous versions are in frontend/.backups/.
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, ChevronRight, Lock, Zap, LogIn } from 'lucide-react';
import HeroField from './HeroField';

// ─── Local dark palette ──────────────────────────────────────────────────────
const C = {
  ground: '#0F1412',
  panel:  '#161C19',
  rule:   '#252E2A',
  ink:    '#E9EDE9',
  muted:  '#8B9891',
  dim:    '#5F6D67',
  teal:   '#3FBFA8',
  amber:  '#D2904F',
};

// ─── Static guest-visible content ────────────────────────────────────────────
// The CISO controls which of these blocks are shown via guest policy.
// For now they are hard-coded to the defaults in DEFAULT_GUEST_POLICY.

const GATES = [
  { id: 'G0',  label: 'Site Rights & Social License', short: 'Site rights',     visible: true },
  { id: 'G1',  label: 'Grid Connection & Utilities',  short: 'Grid',            visible: true },
  { id: 'G2',  label: 'Green Certification Pathway',  short: 'Certification',   visible: true },
  { id: 'G3',  label: 'Feedstock & Logistics',        short: 'Feedstock',       visible: true },
  { id: 'G4',  label: 'Binding Offtake',              short: 'Binding offtake', visible: false },
  { id: 'G5',  label: 'EPC & Construction',           short: 'EPC',             visible: true },
  { id: 'G6',  label: 'Independent Engineer',         short: 'Ind. engineer',   visible: false },
  { id: 'G7',  label: 'Insurance Package',            short: 'Insurance',       visible: false },
  { id: 'G8',  label: 'Audit-Grade Financial Model',  short: 'Fin. model',      visible: false },
  { id: 'G9',  label: 'Permits & Approvals',          short: 'Permits',         visible: true },
  { id: 'G10', label: 'Financial Close',              short: 'Fin. close',      visible: false },
  { id: 'G11', label: 'Commercial Operations Date',   short: 'COD',             visible: false },
];

// Derived, never hand-written — the comp said "5 of 12" while the data says 6,
// and a headline number that disagrees with the row beneath it is the fastest
// way to lose a reader who counts.
const EVIDENCED = GATES.filter((g) => g.visible).length;
const FIRST_BLOCKED = GATES.findIndex((g) => !g.visible);
const NEXT_BLOCKER = FIRST_BLOCKED >= 0 ? GATES[FIRST_BLOCKED] : undefined;

// The full catalogue, not a decorative subset. The page previously showed four
// molecules while the platform carries ten.
const MOLECULES = [
  { f: 'H₂',         n: 'Hydrogen' },
  { f: 'NH₃',        n: 'Ammonia' },
  { f: 'e-NH₃',      n: 'e-Ammonia' },
  { f: 'e-MeOH',     n: 'e-Methanol' },
  { f: 'e-CH₄',      n: 'e-Methane' },
  { f: 'SAF',        n: 'Aviation fuel' },
  { f: 'HVO',        n: 'Renewable diesel' },
  { f: 'e-Naphtha',  n: 'Petrochem feed' },
  { f: 'e-Gasoline', n: 'Road fuel' },
  { f: 'e-LG',       n: 'Liquefied gas' },
];

// What GEX spans, as a sequence rather than a ring of peers. `soon` marks the
// domains not yet in the software — kept on the map deliberately, distinguished
// quietly rather than claimed outright.
const PHASES = [
  { lab: '01 · Develop', sub: 'Bringing a project to bankable', stations: [
      { t: 'Molecules',     d: 'Hydrogen, ammonia, methanol and seven more e-fuels' },
      { t: 'Green fuels',   d: 'SAF, HVO, e-naphtha, e-gasoline' },
      { t: 'Certification', d: 'RED III, RFNBO, 45V / IRA, CertifHy' },
      { t: 'Financials',    d: 'Banks, insurance, re-insurance, DFIs' },
  ] },
  { lab: '02 · Issue', sub: 'Making volume transferable', stations: [
      { t: 'Tokenised transactions', d: 'Hash-chained registry with mass-balance lot control' },
  ] },
  { lab: '03 · Trade', sub: 'Moving and de-risking volume', stations: [
      { t: 'PPA',     d: 'Power purchase contract management' },
      { t: 'HPA',     d: 'Hydrogen purchase agreements', soon: true },
      { t: 'Indexes', d: 'Green commodity indices' },
      { t: 'Hedging', d: 'OTC swaps & options, risk management', soon: true },
  ] },
];

const PROOF = [
  '12 bankability gates · G0 → G11',
  'RED III · RFNBO · 45V · CertifHy',
  'Append-only, hash-chained evidence',
  'Role-scoped access · four-eyes on capital',
  'Deterministic — no black-box scoring',
];

// Each card leads with the job, then names the mechanism that does it.
// NOTE: an earlier version claimed DSCR-sculpted debt and covenant tracking.
// The sculpting module exists in the PF engine but is not reachable from any
// API route, so a user cannot get to it. Claims below are limited to what a
// signed-in user can actually reach today.
const BENEFITS = [
  { title: 'Know what is missing before your lender does',
    body: 'Twelve gates, each with its own evidence requirements. "Not ready" always arrives with a reason and a list.' },
  { title: 'Test eligibility before you commit to FEED',
    body: 'RED III, RFNBO, 45V and CertifHy computed from project data, including temporal correlation and additionality.' },
  { title: 'See the capital stack, not just the model',
    body: 'Blended debt WACC, catalytic ratio, pre-FID spend by layer, post-FID drawdowns, named DFI criteria.' },
  { title: 'Hand the credit committee something it can check',
    body: 'IC packs to PDF or JSON, backed by an append-only, hash-chained evidence trail.' },
];

// Answered with mechanism, not reassurance — "we take security seriously"
// convinces nobody who has been burned.
const FAQ = [
  { q: 'Who can see my project data?',
    a: 'Only people you grant access to. Isolation is enforced in the database itself, not just in the application: a query carrying no verified identity returns nothing rather than everything. Access is scoped by organisation, project and role, and capital transitions require two different people — no single actor can both create and approve one.' },
  { q: 'What do I have to provide before I get anything back?',
    a: 'For the free viability check, four sets of answers — molecule and site, economics, certification pathway — and no account. You get a bankability report at the end of it. Full onboarding adds detail progressively; there is no data migration to complete before the platform becomes useful.' },
  { q: 'Can anyone sign up and start browsing projects?',
    a: 'No. Registration creates a pending account and nothing more. A GreenEarthX employee completes onboarding — including telephone verification and a signed usage agreement — before any account becomes active. That is deliberate: a counterparty you have never spoken to should not be inside a market for confidential project data.' },
  { q: 'Is this a score I have to take on trust?',
    a: 'No. Nothing here is a black-box model. Every gate result traces to the evidence and the rule that produced it, and the evidence log is append-only and hash-chained — so a changed record is detectable rather than merely discouraged.' },
  { q: 'Which molecules and certification schemes are covered?',
    a: 'Ten molecules today — hydrogen, ammonia, e-ammonia, e-methanol, e-methane, SAF, HVO, e-naphtha, e-gasoline and e-LG — each with its own energy density, unit conversions and certification route. Schemes: RED III, RFNBO, 45V / IRA and CertifHy.' },
];

// Curated externally and reviewed by GEX before publication — never
// auto-published. Replace with the live feed once the review queue exists.
const RESEARCH = [
  { src: 'European Commission', headline: 'Delegated act guidance updates temporal correlation rules for RFNBO hydrogen' },
  { src: 'IEA',                 headline: 'Global Hydrogen Review: announced capacity outpaces final investment decisions' },
  { src: 'IRENA',               headline: 'E-methanol offtake pricing converges as shipping demand firms' },
];

// ─── Shared bits ─────────────────────────────────────────────────────────────

function SectionHead({ title, meta }: { title: string; meta?: string }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-3 mb-7">
      <h2 className="text-xl font-semibold tracking-[-.018em] m-0" style={{ color: C.ink }}>{title}</h2>
      {meta && (
        <span className="text-[10px] font-mono uppercase tracking-[.12em]" style={{ color: C.dim }}>
          {meta}
        </span>
      )}
    </div>
  );
}

// ─── Component ───────────────────────────────────────────────────────────────

export function GuestLandingPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen" style={{ background: C.ground, color: C.ink }}>

      {/* ── Hero: generative field, nav sits on it ────────────── */}
      <section className="relative overflow-hidden" style={{ background: '#04182B' }}>
        <HeroField palette="ocean" />
        <div
          className="absolute inset-0 pointer-events-none"
          style={{ background: 'radial-gradient(circle at 50% 12%, rgba(4,18,24,.42), rgba(4,18,24,.80) 68%)' }}
        />

        <div className="relative max-w-6xl mx-auto px-6">
          <header className="flex items-center justify-between py-5">
            <img src="/GreenEarthX-updated.png" alt="GreenEarthX"
                 className="h-11 w-auto object-contain sm:h-12" />
            <div className="flex items-center gap-3">
              <span className="text-[11px] px-3 py-1.5 border"
                    style={{ color: 'rgba(233,237,233,.62)', borderColor: 'rgba(233,237,233,.20)' }}>
                Guest — limited view
              </span>
              <button
                onClick={() => navigate('/login')}
                className="flex items-center gap-1.5 text-[11px] font-mono tracking-wider px-3.5 py-2 border"
                style={{ color: C.ink, borderColor: 'rgba(233,237,233,.22)' }}
              >
                <LogIn className="w-3.5 h-3.5" />
                SIGN IN
              </button>
            </div>
          </header>

          <div className="pt-16 pb-16 text-center">
            <div className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-[11px] font-semibold
                            uppercase tracking-[0.16em] mb-7 border"
                 style={{ background: 'rgba(233,237,233,.06)', borderColor: 'rgba(233,237,233,.22)', color: C.teal }}>
              <Zap className="w-3.5 h-3.5" />
              Evidence-to-capital orchestration for green fuels
            </div>

            <h1 className="text-5xl sm:text-6xl font-semibold leading-[1.02] mb-6 max-w-4xl mx-auto"
                style={{ color: C.ink }}>
              Projects don’t become bankable because the story is convincing.
              <span style={{ color: C.teal }}> They become bankable when the evidence converges.</span>
            </h1>

            <p className="text-lg max-w-2xl mx-auto mb-8 leading-8" style={{ color: 'rgba(233,237,233,.78)' }}>
              GreenEarthX structures the technical, regulatory, commercial and financial
              evidence behind green and bio-based fuel projects — showing producers,
              offtakers, lenders, insurers, DFIs and certifiers what is ready, what is
              missing, and what must be solved before FEED, FID and COD.
            </p>

            <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-2 mb-12">
              {PROOF.map((label) => (
                <span key={label} className="text-[11px] rounded-full border px-3 py-1.5"
                      style={{ background: 'rgba(233,237,233,.05)',
                               borderColor: 'rgba(233,237,233,.20)',
                               color: 'rgba(233,237,233,.70)' }}>
                  {label}
                </span>
              ))}
            </div>

            {/* Free assessment — the conversion path */}
            <div className="rounded-[20px] p-8 sm:p-10 max-w-3xl mx-auto border text-left"
                 style={{ background: 'rgba(12,28,28,.62)', borderColor: 'rgba(233,237,233,.16)' }}>
              <p className="text-[10px] font-mono uppercase tracking-[0.14em] mb-2" style={{ color: C.teal }}>
                Free assessment
              </p>
              <h2 className="text-3xl font-semibold mb-3" style={{ color: C.ink }}>Planning a new project?</h2>
              <p className="text-sm leading-7 mb-7" style={{ color: 'rgba(233,237,233,.74)' }}>
                Answer four sets of questions — molecule and site, economics, certification
                pathway — and receive an instant bankability viability report. No account required.
              </p>
              <div className="flex flex-col sm:flex-row gap-3">
                <button
                  onClick={() => navigate('/onboarding')}
                  className="flex-1 flex items-center justify-center gap-2 font-semibold py-3.5 px-6 text-sm"
                  style={{ background: C.teal, color: '#06110F' }}
                >
                  Start project viability check
                  <ArrowRight className="w-4 h-4" />
                </button>
                <button
                  onClick={() => navigate('/login')}
                  className="flex items-center justify-center gap-2 border py-3.5 px-5 text-sm"
                  style={{ borderColor: 'rgba(233,237,233,.22)', color: 'rgba(233,237,233,.8)' }}
                >
                  <LogIn className="w-4 h-4" />
                  Sign in for full access
                </button>
              </div>
              <div className="flex items-center justify-center gap-2 mt-5 pt-4 border-t"
                   style={{ borderColor: 'rgba(233,237,233,.14)' }}>
                {['Molecule & site', 'Economics', 'Certification', 'Report'].map((s, i) => (
                  <React.Fragment key={s}>
                    <span className="text-[10px] font-mono" style={{ color: 'rgba(233,237,233,.5)' }}>
                      {i + 1} {s}
                    </span>
                    {i < 3 && <span style={{ color: 'rgba(233,237,233,.25)' }}>·</span>}
                  </React.Fragment>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── BREADTH: what GEX orchestrates ────────────────────── */}
      <section className="max-w-6xl mx-auto px-6 py-14">
        {/* The meta line names the two ends of the chain. It used to list five
            steps while the body showed three phases, so the header and the
            layout disagreed about what the sequence even was. */}
        <SectionHead title="What GEX orchestrates" meta="From first molecule to settled trade" />

        {/* Rail: a start cap, a chevron at each phase boundary, an end cap.
            Without it the three columns read as three unrelated groups — the
            layout showed a sequence but never said it ran left to right. */}
        <div className="hidden md:grid md:grid-cols-[1.6fr_.9fr_1.6fr] items-center mb-6">
          {PHASES.map((ph, i) => (
            <div key={ph.lab} className="flex items-center gap-2">
              {i === 0 && (
                <span className="w-[7px] h-[7px] rounded-full flex-shrink-0"
                      style={{ background: C.teal }} />
              )}
              <span className="flex-1 h-px" style={{ background: C.rule }} />
              {i < PHASES.length - 1 ? (
                <ChevronRight className="w-3.5 h-3.5 flex-shrink-0" style={{ color: C.teal }} />
              ) : (
                <span className="w-[7px] h-[7px] rounded-full flex-shrink-0 border"
                      style={{ borderColor: C.teal, background: C.ground }} />
              )}
            </div>
          ))}
        </div>

        <div className="grid md:grid-cols-[1.6fr_.9fr_1.6fr] gap-y-8 md:gap-y-0">
          {PHASES.map((ph, i) => {
            const single = ph.stations.length === 1;
            return (
              <div key={ph.lab}
                   className={`flex flex-col ${i > 0 ? 'md:pl-7' : 'md:pr-7'} ${i === 1 ? 'md:pr-7' : ''}`}>
                <p className="text-[10px] font-mono uppercase tracking-[.14em] mb-1" style={{ color: C.teal }}>
                  {ph.lab}
                </p>
                <p className="text-[11.5px] mb-4" style={{ color: C.dim }}>{ph.sub}</p>

                {/* auto-rows-fr equalises card heights within a phase; the
                    single-card phase centres so it does not float above a void */}
                <div className={`grid gap-2 flex-1 ${single ? 'grid-cols-1 content-center' : 'grid-cols-2 auto-rows-fr'}`}>
                  {ph.stations.map((st) => {
                    const soon = (st as { soon?: boolean }).soon;
                    return (
                      <div key={st.t} className="p-3.5 border h-full"
                           style={{ borderColor: C.rule,
                                    borderStyle: soon ? 'dashed' : 'solid',
                                    background: soon ? 'transparent' : C.panel }}>
                        <b className="block text-[10px] font-mono uppercase tracking-[.1em] mb-1.5"
                           style={{ color: soon ? C.dim : C.ink }}>{st.t}</b>
                        <p className="text-[11.5px] leading-[1.5] m-0" style={{ color: C.muted }}>{st.d}</p>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
        <p className="mt-6 pt-3 border-t text-[10px] font-mono tracking-[.06em]"
           style={{ borderColor: C.rule, color: C.dim }}>
          <span className="inline-block w-4 border-t border-dashed align-middle mr-2"
                style={{ borderColor: C.dim }} />
          Dashed — on the roadmap, not yet live. Everything else is running today.
        </p>
      </section>

      {/* ── Molecules — all ten ───────────────────────────────── */}
      <section className="max-w-6xl mx-auto px-6 pb-14">
        <div className="grid md:grid-cols-[230px_1fr] gap-8 items-start">
          <div>
            <h3 className="text-[10px] font-mono uppercase tracking-[.14em] m-0" style={{ color: C.teal }}>
              Molecules covered
            </h3>
          </div>
          <div className="flex flex-wrap border-l border-t" style={{ borderColor: C.rule }}>
            {/* Formula only. The plain-English names still live on `n` in the
                data and are spelled out in the FAQ, so nothing is lost to a
                reader who needs them. */}
            {MOLECULES.map(({ f }) => (
              <div key={f} className="flex-1 min-w-[128px] px-5 py-4 border-r border-b"
                   style={{ borderColor: C.rule }}>
                <b className="block text-[17px] font-semibold tracking-[-.012em]" style={{ color: C.ink }}>{f}</b>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── PROOF: the gate spine ─────────────────────────────── */}
      <section className="max-w-6xl mx-auto px-6 py-14 border-t" style={{ borderColor: C.rule }}>
        <SectionHead title="How readiness is judged" meta="Sample project · 12 gates · sign in for your own" />

        <div className="overflow-x-auto">
          <div className="min-w-[860px]">
            <div className="relative h-px mt-8" style={{ background: C.rule }}>
              <div className="absolute left-0 top-0 h-px"
                   style={{ background: C.teal,
                            width: `${((FIRST_BLOCKED + 0.5) / GATES.length) * 100}%` }} />
            </div>
            <div className="grid grid-cols-12 -mt-[5px]">
              {GATES.map((g) => {
                const isNext = NEXT_BLOCKER?.id === g.id;
                const pip = g.visible
                  ? { background: C.teal, border: `1px solid ${C.teal}` }
                  : isNext
                    ? { background: C.ground, border: `2px solid ${C.amber}` }
                    : { background: C.ground, border: `1px solid ${C.rule}` };
                const tone = g.visible ? C.teal : isNext ? C.amber : C.dim;
                const nameTone = g.visible ? C.ink : isNext ? C.amber : C.dim;
                const blurred = !g.visible && !isNext;
                return (
                  <div key={g.id}>
                    <div className="w-[9px] h-[9px] rounded-full" style={pip} />
                    <code className="block text-[10px] font-mono mt-[11px]" style={{ color: tone }}>{g.id}</code>
                    <b className={`block text-[10.5px] font-normal mt-1 pr-3 leading-[1.34]
                                   ${blurred ? 'blur-[2.4px] select-none' : ''}`}
                       style={{ color: nameTone }}>
                      {g.short}
                    </b>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 mt-8 pt-4 border-t
                        text-[10.5px] font-mono uppercase tracking-[.06em]"
             style={{ borderColor: C.rule, color: C.dim }}>
          <span>
            {EVIDENCED} of {GATES.length} evidenced
            {NEXT_BLOCKER && (
              <> · next blocker <b style={{ color: C.teal }}>{NEXT_BLOCKER.id} {NEXT_BLOCKER.label}</b></>
            )}
          </span>
          <button onClick={() => navigate('/login')}
                  className="flex items-center gap-1.5 uppercase" style={{ color: C.dim }}>
            <Lock className="w-3 h-3" />
            Sign in to see all twelve
          </button>
        </div>
      </section>

      {/* ── Full platform — the sign-in nudge ─────────────────── */}
      <section className="max-w-6xl mx-auto px-6 py-14 border-t" style={{ borderColor: C.rule }}>
        <SectionHead title="Full platform — available after sign-in" meta="Guest view shows a fraction" />
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 border-t" style={{ borderColor: C.rule }}>
          {BENEFITS.map(({ title, body }, i) => (
            <div key={title} className={`py-5 pr-6 ${i > 0 ? 'lg:pl-6 lg:border-l' : ''}`}
                 style={i > 0 ? { borderColor: C.rule } : undefined}>
              <b className="block text-[13px] font-semibold leading-[1.35] mb-2" style={{ color: C.ink }}>{title}</b>
              <p className="text-[11.5px] leading-[1.55] m-0" style={{ color: C.muted }}>{body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── FAQ ───────────────────────────────────────────────── */}
      <section className="max-w-6xl mx-auto px-6 py-14 border-t" style={{ borderColor: C.rule }}>
        <SectionHead title="Before you put a project in" meta="The questions we are asked first" />
        <div className="border-t" style={{ borderColor: C.rule }}>
          {FAQ.map(({ q, a }) => (
            <details key={q} className="border-b group" style={{ borderColor: C.rule }}>
              <summary className="cursor-pointer list-none flex items-center justify-between gap-4
                                  py-4 text-[13.5px] font-medium" style={{ color: C.ink }}>
                {q}
                <span className="text-lg leading-none flex-shrink-0 transition-transform group-open:rotate-45"
                      style={{ color: C.teal }} aria-hidden="true">+</span>
              </summary>
              <p className="text-xs leading-relaxed pb-4 m-0 max-w-[80ch]" style={{ color: C.muted }}>{a}</p>
            </details>
          ))}
        </div>
      </section>

      {/* ── Bottom CTA ────────────────────────────────────────── */}
      <section className="max-w-5xl mx-auto px-6 py-14 text-center border-t" style={{ borderColor: C.rule }}>
        <h3 className="text-2xl font-semibold mb-3" style={{ color: C.ink }}>Ready to assess your project?</h3>
        <p className="text-sm mb-7" style={{ color: C.muted }}>
          No commitment required — run a free viability check in under five minutes.
        </p>
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <button onClick={() => navigate('/onboarding')}
                  className="flex items-center justify-center gap-2 font-semibold py-3 px-8"
                  style={{ background: C.teal, color: '#06110F' }}>
            Start project viability check
            <ArrowRight className="w-4 h-4" />
          </button>
          <button onClick={() => navigate('/login')}
                  className="flex items-center justify-center gap-2 border font-medium py-3 px-6"
                  style={{ borderColor: C.rule, color: C.muted }}>
            <LogIn className="w-4 h-4" />
            Sign in to existing account
          </button>
        </div>
      </section>

      {/* ── Research & market insight — last, above the footer ── */}
      <section className="max-w-6xl mx-auto px-6 py-12 border-t" style={{ borderColor: C.rule }}>
        <SectionHead title="Research & market insight"
                     meta="Curated · reviewed before publication · sample feed" />
        <div className="grid sm:grid-cols-3 border-t" style={{ borderColor: C.rule }}>
          {RESEARCH.map(({ src, headline }, i) => (
            <div key={headline} className={`py-5 pr-6 ${i > 0 ? 'sm:pl-6 sm:border-l' : ''}`}
                 style={i > 0 ? { borderColor: C.rule } : undefined}>
              <p className="text-[9.5px] font-mono uppercase tracking-[.11em] m-0" style={{ color: C.teal }}>{src}</p>
              <h4 className="text-[13.5px] font-medium leading-[1.42] mt-2.5 mb-2" style={{ color: C.ink }}>
                {headline}
              </h4>
              <time className="text-[10px] font-mono" style={{ color: C.dim }}>Sample entry</time>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t py-6 text-center text-xs"
              style={{ borderColor: C.rule, color: C.dim }}>
        © {new Date().getFullYear()} GreenEarthX · Proprietary · All rights reserved
      </footer>
    </div>
  );
}

export default GuestLandingPage;
