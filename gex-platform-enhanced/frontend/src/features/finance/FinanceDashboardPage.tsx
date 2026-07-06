// Screen: Finance dashboard screen (/finance-dashboard, /finance/dashboard)
/**
 * FinanceDashboardPage — Bloomberg / Kiodex–density rewrite.
 *
 * Doctrine:
 *  - Color reserved for state — every accent is a 2px left band, never a full border.
 *  - Square corners, mono-spaced numbers, slate palette only.
 *  - Every number traces to a project field or is explicitly marked PENDING.
 *  - No decorative icons.  Density first.
 *
 * Routes:
 *   /finance-dashboard         (top-level)
 *   /finance/dashboard         (nested)
 *   /finance                   (index)
 */
import { type ReactNode, useState } from 'react'
import { Link } from 'react-router-dom'
import { ProductionRoadmapGantt } from '@/components/gantt/ProductionRoadmapGantt'
import { TaskRouter } from '@/components/TaskRouter'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'
import { CooperationHandoffFeed } from '@/components/CooperationHandoffFeed'
import type { CustomerProject, Offtake } from '@/data/customerProjects'

// ─── Chips ────────────────────────────────────────────────────────────────────

type ChipTone = 'live' | 'warn' | 'concern' | 'info' | 'none'

function chipClasses(tone: ChipTone): string {
  switch (tone) {
    case 'live':    return 'border-l-emerald-600 text-emerald-800 dark:text-emerald-300'
    case 'info':    return 'border-l-sky-600     text-sky-800     dark:text-sky-300'
    case 'warn':    return 'border-l-amber-600   text-amber-800   dark:text-amber-300'
    case 'concern': return 'border-l-red-600     text-red-800     dark:text-red-300'
    default:        return 'border-l-slate-400   text-slate-500   dark:text-slate-400'
  }
}

function Chip({ text, tone, title }: { text: string; tone: ChipTone; title?: string }) {
  return (
    <span
      title={title}
      className={`inline-flex h-[15px] items-center justify-center border border-l-2 border-slate-300 bg-white dark:bg-slate-950 px-1 font-mono text-[8px] font-bold uppercase tracking-[0.08em] leading-none whitespace-nowrap ${chipClasses(tone)}`}
    >
      {text}
    </span>
  )
}

// ─── Section frame ────────────────────────────────────────────────────────────

function Section({ title, link, children }: { title: string; link?: { href: string; label: string }; children: ReactNode }) {
  return (
    <section className="border border-slate-200 dark:border-slate-800">
      <header className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 px-2 py-1">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.12em] text-slate-600 dark:text-slate-400">
          {title}
        </h2>
        {link && (
          <Link to={link.href} className="font-mono text-[10px] uppercase tracking-[0.08em] text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-slate-100 hover:underline">
            {link.label} →
          </Link>
        )}
      </header>
      <div className="divide-y divide-slate-100 dark:divide-slate-900">
        {children}
      </div>
    </section>
  )
}

// ─── Generic dense row ────────────────────────────────────────────────────────

function Row({
  label,
  value,
  target,
  chip,
  note,
}: {
  label: string
  value: ReactNode
  target?: string
  chip?: { text: string; tone: ChipTone; title?: string }
  note?: string
}) {
  return (
    <div className="grid grid-cols-[120px_minmax(0,1fr)_120px_120px] items-center gap-2 px-2 py-[3px] hover:bg-slate-50 dark:hover:bg-slate-900">
      <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400 whitespace-nowrap">
        {label}
      </span>
      <span className="font-mono text-[11px] font-semibold tabular-nums text-slate-900 dark:text-slate-100 truncate">
        {value}
      </span>
      <span className="font-mono text-[10px] text-slate-500 dark:text-slate-400 truncate">
        {target ?? ''}
      </span>
      <div className="flex items-center justify-end gap-1 min-w-0">
        {note && (
          <span className="font-mono text-[10px] text-slate-500 dark:text-slate-400 truncate">{note}</span>
        )}
        {chip && <Chip text={chip.text} tone={chip.tone} title={chip.title} />}
      </div>
    </div>
  )
}

// ─── Derivations from project data (Hidalgo causal compression) ──────────────

// Stage gate roll-up: which of FEL / FEED / FID / FINANCIAL CLOSE / COD is the
// current frontier, derived from project.bankability.gates completion.
type Stage = 'FEL' | 'FEED' | 'FID' | 'FIN_CLOSE' | 'COD'

function stageStatus(project: CustomerProject, stage: Stage): { state: 'COMPLETE' | 'IN_PROGRESS' | 'PENDING'; pct: number } {
  const gates = project.bankability.gates
  const pctOf = (ids: string[]) => {
    const g = gates.filter(x => ids.includes(x.id))
    if (g.length === 0) return 0
    return Math.round(g.reduce((s, x) => s + x.completion_pct, 0) / g.length)
  }
  let pct = 0
  switch (stage) {
    case 'FEL':       pct = pctOf(['G0_SITE_RIGHTS', 'G1_GRID_UTILITIES_REALITY', 'G2_CERTIFICATION_PATH_LOCKED', 'G3_INPUTS_SECURED']); break
    case 'FEED':      pct = pctOf(['G4_OFFTAKE_BANKABLE', 'G5_EPC_RISK_PRICED']); break
    case 'FID':       pct = pctOf(['G6_IE_SIGNOFF', 'G8_AUDIT_GRADE_MODEL']); break
    case 'FIN_CLOSE': pct = pctOf(['G7_INSURANCE_BOUND', 'G9_PERMITS_SAFE', 'G10_FINANCIAL_CLOSE_CP']); break
    case 'COD':       pct = pctOf(['G11_COD_STABILIZATION']); break
  }
  const state: 'COMPLETE' | 'IN_PROGRESS' | 'PENDING' = pct >= 100 ? 'COMPLETE' : pct > 0 ? 'IN_PROGRESS' : 'PENDING'
  return { state, pct }
}

// Cross all gates, surface the worst-blocked one (≤ 50%) with its blocking items.
function criticalGate(project: CustomerProject) {
  const incomplete = project.bankability.gates.filter(g => !g.is_complete)
  if (incomplete.length === 0) return null
  const worst = [...incomplete].sort((a, b) => a.completion_pct - b.completion_pct)[0]
  return worst
}

// Offtake coverage = Σ binding & term-sheet volumes / annual capacity.
function offtakeCoverage(project: CustomerProject): { pct: number | null; contracted_kt: number; active_kt: number; merchant_kt: number } {
  const capKt = project.capacity_kt_yr ?? Math.round((project.capacity_mtpd * 365) / 1000)
  if (!project.offtakes || capKt === 0) return { pct: null, contracted_kt: 0, active_kt: 0, merchant_kt: capKt }
  const sum = (status: Offtake['binding_status'][]) =>
    project.offtakes!.filter(o => status.includes(o.binding_status)).reduce((s, o) => s + (o.volume_tpy ?? 0), 0) / 1000
  const contracted = sum(['BINDING', 'TERM_SHEET'])
  const active     = sum(['LOI', 'MOU', 'INDICATIVE'])
  const merchant   = Math.max(0, capKt - contracted - active)
  const pct        = Math.round((contracted / capKt) * 100)
  return { pct, contracted_kt: contracted, active_kt: active, merchant_kt: merchant }
}

// Compliance per certification scheme — derives from project.certifications
function complianceRows(project: CustomerProject) {
  return (project.certifications ?? []).map(c => {
    const tone: ChipTone =
      c.status === 'ACTIVE'        ? 'live' :
      c.status === 'UNDER_REVIEW'  ? 'warn' :
      c.status === 'PRE-ASSESSMENT' ? 'info' :
      c.status === 'INTENDED'      ? 'none' :
                                     'concern'
    return { scheme: c.scheme, status: c.status, tier: c.tier, note: c.note, tone }
  })
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function FinanceDashboardPage() {
  const { selectedProjectId } = useSelectedProject()
  const { projects: visibleProjects } = useVisibleProjects()
  const project = visibleProjects.find(p => p.id === selectedProjectId) ?? visibleProjects[0]
  const [showLegacyDashboard, setShowLegacyDashboard] = useState(false)

  // ── Guided view (TaskRouter) — unchanged ──────────────────────────────────
  if (!showLegacyDashboard) {
    return (
      <div className="max-w-3xl mx-auto space-y-3 py-2">
        <div className="flex items-baseline justify-between">
          <h1 className="font-mono text-[12px] font-bold uppercase tracking-[0.12em] text-slate-900 dark:text-slate-100">Finance Workspace</h1>
          <span className="font-mono text-[10px] text-slate-500">{project.name}</span>
        </div>
        <TaskRouter
          actorType="COMMERCIAL_BANKER"
          projectId={project.id}
          projectName={project.name}
          onShowSidebar={() => setShowLegacyDashboard(true)}
        />
      </div>
    )
  }

  // ── Detail view — Bloomberg density ───────────────────────────────────────
  const stages: { id: Stage; label: string }[] = [
    { id: 'FEL',       label: 'FEL' },
    { id: 'FEED',      label: 'FEED' },
    { id: 'FID',       label: 'FID' },
    { id: 'FIN_CLOSE', label: 'FINANCIAL CLOSE' },
    { id: 'COD',       label: 'COD' },
  ]
  const stageState = stages.map(s => ({ ...s, ...stageStatus(project, s.id) }))
  const critical   = criticalGate(project)
  const cov        = offtakeCoverage(project)
  const compliance = complianceRows(project)
  const ovComp     = project.bankability.overall_completion

  // Status-line metadata
  const now = new Date()
  const asOf = `${now.toISOString().slice(0, 19).replace('T', ' ')}Z`

  return (
    <div className="max-w-6xl mx-auto space-y-2 px-2 py-2">

      {/* ── Status line ── */}
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-slate-200 dark:border-slate-800 pb-1">
        <div className="flex items-baseline gap-3 min-w-0">
          <h1 className="font-mono text-[12px] font-bold uppercase tracking-[0.12em] text-slate-900 dark:text-slate-100 whitespace-nowrap">
            Finance Workspace
          </h1>
          <span className="font-mono text-[10px] text-slate-600 dark:text-slate-400 truncate">
            {project.id} · {project.name} · {project.country} · {project.molecule}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowLegacyDashboard(false)}
            className="font-mono text-[10px] uppercase tracking-[0.08em] text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 hover:underline"
          >
            ← guided
          </button>
          <span className="font-mono text-[10px] text-slate-500">{asOf}</span>
        </div>
      </div>

      {/* ── Roll-up KPIs (slate, mono, no decoration) ── */}
      <div className="grid grid-cols-4 gap-px bg-slate-200 dark:bg-slate-800 border border-slate-200 dark:border-slate-800">
        {[
          { label: 'Overall completion', value: `${ovComp}%`,                            chip: { text: `${project.bankability.unlocked_capital.length} unlocked`, tone: 'info' as ChipTone } },
          { label: 'Critical gate',      value: critical ? critical.id.split('_')[0] : '—',
                                         note: critical ? `${critical.completion_pct}%` : 'all clear',
                                         chip: { text: critical ? 'BLOCKED' : 'OK',    tone: critical ? ('warn' as ChipTone) : ('live' as ChipTone) } },
          { label: 'Offtake coverage',   value: cov.pct == null ? '—' : `${cov.pct}%`,    note: `${cov.contracted_kt.toFixed(0)}/${(cov.contracted_kt + cov.active_kt + cov.merchant_kt).toFixed(0)} kt/yr`,
                                         chip: { text: cov.pct == null ? 'PENDING' : (cov.pct >= 70 ? 'LIVE' : 'WARN'), tone: cov.pct == null ? ('none' as ChipTone) : (cov.pct >= 70 ? 'live' : 'warn') as ChipTone } },
          { label: 'Risk alerts',        value: String(project.bankability.risk_alerts.length),
                                         chip: { text: project.bankability.risk_alerts.length === 0 ? 'CLEAR' : 'OPEN', tone: project.bankability.risk_alerts.length === 0 ? ('live' as ChipTone) : ('warn' as ChipTone) } },
        ].map((kpi, i) => (
          <div key={i} className="bg-white dark:bg-slate-950 px-2 py-1.5 space-y-0.5">
            <div className="font-mono text-[9px] uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">{kpi.label}</div>
            <div className="flex items-baseline justify-between gap-2">
              <span className="font-mono text-[15px] font-bold tabular-nums text-slate-900 dark:text-slate-100">{kpi.value}</span>
              <div className="flex items-baseline gap-1.5">
                {kpi.note && <span className="font-mono text-[9px] text-slate-500 dark:text-slate-400">{kpi.note}</span>}
                <Chip text={kpi.chip.text} tone={kpi.chip.tone} />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* ── Stage gate strip ── */}
      <Section title="Stage gate progression" link={{ href: '/finance/stage-gates', label: 'Open gate checklist' }}>
        {stageState.map(s => {
          const tone: ChipTone = s.state === 'COMPLETE' ? 'live' : s.state === 'IN_PROGRESS' ? 'warn' : 'none'
          return (
            <Row
              key={s.id}
              label={s.label}
              value={`${s.pct}%`}
              target=""
              note={s.state.replace('_', ' ').toLowerCase()}
              chip={{ text: s.state.replace('_', ' '), tone }}
            />
          )
        })}
        {critical && (
          <div className="border-l-2 border-l-amber-600 px-2 py-1.5 bg-slate-50 dark:bg-slate-900">
            <div className="font-mono text-[10px] uppercase tracking-[0.08em] text-slate-600 dark:text-slate-400">
              Binding gate · {critical.id} · {critical.completion_pct}%
            </div>
            <div className="font-mono text-[11px] text-slate-800 dark:text-slate-200 mt-0.5">{critical.name}</div>
            {critical.blocking_items.length > 0 && (
              <ul className="mt-1 space-y-0.5 font-mono text-[10px] text-slate-700 dark:text-slate-300">
                {critical.blocking_items.slice(0, 5).map(item => (
                  <li key={item}>· {item.replace(/_/g, ' ')}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </Section>

      {/* ── Key project-finance metrics — link to Pre-COD panel for full lineage ── */}
      <Section title="Project-finance metrics" link={{ href: '/finance/bankability', label: 'Open Pre-COD panel' }}>
        <Row
          label="DSCR  current"
          value="pending"
          target="covenant ≥ 1.25×"
          note="post-COD only"
          chip={{ text: 'AWAITING ENGINE', tone: 'none', title: 'Forward projection from gex_pf_engine at T-2 quarters from COD' }}
        />
        <Row
          label="LLCR  projected"
          value="pending"
          target="covenant ≥ 1.40×"
          chip={{ text: 'AWAITING ENGINE', tone: 'none', title: 'POST /api/v1/finance-model/lifetime' }}
        />
        <Row
          label="DSRA  balance"
          value="pending"
          target="target ≥ 6 months DS"
          chip={{ text: 'AWAITING ENGINE', tone: 'none', title: 'gex_pf_engine waterfall — not yet wired' }}
        />
        <Row
          label="Offtake coverage"
          value={cov.pct == null ? '—' : `${cov.pct}%`}
          target="bankability ≥ 70%"
          note={`${cov.contracted_kt.toFixed(0)} contracted · ${cov.active_kt.toFixed(0)} active · ${cov.merchant_kt.toFixed(0)} merchant kt/yr`}
          chip={{ text: cov.pct == null ? 'PENDING' : 'LIVE', tone: cov.pct == null ? 'none' : 'live' }}
        />
      </Section>

      {/* ── Contract stack — derived from project.offtakes ── */}
      <Section title="Contract stack" link={{ href: '/finance/revenue', label: 'Open revenue page' }}>
        {(project.offtakes ?? []).length === 0 && (
          <div className="px-2 py-2 font-mono text-[11px] italic text-slate-500">No offtakes declared on this project.</div>
        )}
        {(project.offtakes ?? []).map((o, i) => {
          const tone: ChipTone =
            o.binding_status === 'BINDING'    ? 'live' :
            o.binding_status === 'TERM_SHEET' ? 'info' :
            o.binding_status === 'LOI' || o.binding_status === 'MOU' ? 'warn' : 'none'
          return (
            <Row
              key={i}
              label={o.binding_status}
              value={o.party}
              target={o.volume_tpy ? `${o.volume_tpy.toLocaleString('en-US')} t/yr` : 'volume undisclosed'}
              note={[
                o.term_years ? `${o.term_years}y` : null,
                o.is_related_party ? 'related-party' : null,
                o.verification === 'UNVERIFIED' ? 'unverified' : null,
              ].filter(Boolean).join(' · ')}
              chip={{ text: o.binding_status, tone }}
            />
          )
        })}
      </Section>

      {/* ── Compliance / certification evidence ── */}
      <Section title="Certification readiness" link={{ href: '/finance/cert-readiness', label: 'Open cert readiness' }}>
        {compliance.length === 0 && (
          <div className="px-2 py-2 font-mono text-[11px] italic text-slate-500">
            No certifications declared. Add them under TECHNICAL on the project edit page.
          </div>
        )}
        {compliance.map((c, i) => (
          <Row
            key={i}
            label={c.scheme}
            value={c.status.replace(/_/g, ' ').toLowerCase()}
            target={c.tier ?? ''}
            note={c.note ?? ''}
            chip={{ text: c.status.replace('_', ' '), tone: c.tone }}
          />
        ))}
      </Section>

      {/* ── Roadmap ── */}
      <Section title="Production roadmap">
        <div className="px-2 py-1">
          <ProductionRoadmapGantt workspaceId="finance" compact />
        </div>
      </Section>

      {/* ── Handoff feed ── */}
      <Section title="Cross-functional handoff">
        <div className="px-2 py-1">
          <CooperationHandoffFeed projectId={project.id} maxItems={5} compact />
        </div>
      </Section>

    </div>
  )
}
