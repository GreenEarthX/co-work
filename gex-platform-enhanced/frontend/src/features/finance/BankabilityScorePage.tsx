// Screen: State & Blockers (/bankability-scores, /finance/bankability-scores)
/**
 * State & Blockers — the gate engine's readout for the selected project:
 * the state its evidence supports, what blocks the next one, the offtake and
 * EPC levels, and which capital decisions it is eligible for.
 *
 * Every figure comes from one engine readout (useEngineReadout). This screen
 * used to compute a letter rating, scores, a random trajectory and typed
 * deal-killer thresholds from the customerProjects.ts fixture; D4 removed them
 * (no composite, quality or trust score in client material). When the engine
 * does not answer, the screen says so rather than falling back.
 */
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, ArrowRight, RefreshCw } from 'lucide-react'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'
import { useEngineReadout, useEngineRules, useVocabularyLabel } from '@/hooks/useEngineReadout'
import { DeclaredVsEvidenced } from '@/components/DeclaredVsEvidenced'
import {
  applicableDecisions, blockingGates, gateName, gateShortId, humanise, isEligible,
  openDealKillers, refusalReason, type EngineLevel, type EngineReadout,
} from '@/lib/engineReadout'

const GATES_AND_EVIDENCE = '/stage-gates'

export default function BankabilityScorePage() {
  const { selectedProjectId } = useSelectedProject()
  const { projects } = useVisibleProjects()
  const project = projects.find(p => p.id === selectedProjectId) ?? projects[0]
  const { data: readout, isLoading, isError, error, refetch, isFetching } = useEngineReadout(project?.id)

  return (
    <div className="space-y-4 max-w-5xl mx-auto">
      <div>
        <h1 className="text-lg font-bold text-[var(--text-primary)]">State &amp; Blockers</h1>
        {project && <p className="text-xs text-[var(--text-muted)] mt-0.5">{project.name}</p>}
      </div>

      {!project ? (
        <Panel>
          <p className="text-sm text-[var(--text-secondary)]">No project selected.</p>
        </Panel>
      ) : isLoading ? (
        <Panel>
          <p className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
            <RefreshCw className="w-4 h-4 animate-spin" /> Asking the gate engine…
          </p>
        </Panel>
      ) : isError || !readout ? (
        <Panel>
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            The gate engine did not answer, so no state is shown.
          </p>
          {refusalReason(error) && (
            <p className="mt-1 text-xs text-[var(--text-muted)]">{refusalReason(error)}</p>
          )}
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--surface-muted)]"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin' : ''}`} /> Retry
          </button>
        </Panel>
      ) : (
        <Readout readout={readout} />
      )}
    </div>
  )
}

function Readout({ readout }: { readout: EngineReadout }) {
  const stateLabel = useVocabularyLabel('readiness')
  const { data: rules } = useEngineRules()
  const blocking = blockingGates(readout)
  const shortfalls = readout.commitments_blocking_next_state ?? []
  const decisions = applicableDecisions(readout)
  const eligible = decisions.filter(isEligible)

  return (
    <>
      <Panel>
        <DeclaredVsEvidenced readout={readout} />
        {readout.regression && (
          <p className="mt-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800 dark:border-red-800/40 dark:bg-red-900/15 dark:text-red-300">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>
              State fell from {stateLabel(readout.regression.from_state)} to{' '}
              {stateLabel(readout.regression.to_state)}
              {readout.regression.reason ? `: ${readout.regression.reason}` : ''}
            </span>
          </p>
        )}
      </Panel>

      <Panel title="What blocks the next state">
        {!readout.next_state ? (
          <p className="text-sm text-[var(--text-secondary)]">No further state.</p>
        ) : (
          <>
            <p className="text-sm text-[var(--text-primary)]">
              Next state <strong>{stateLabel(readout.next_state)}</strong>
              {readout.next_state_label && (
                <span className="text-[var(--text-muted)]"> · {readout.next_state_label}</span>
              )}
            </p>
            {blocking.length === 0 && shortfalls.length === 0 && (
              <p className="mt-2 text-xs text-[var(--text-muted)]">The gates it needs are satisfied.</p>
            )}
            <ul className="mt-3 divide-y divide-[var(--border)]">
              {blocking.map(gate => {
                const killers = openDealKillers(gate)
                return (
                  <li key={gate.gate_id} className="py-2.5">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <span className="text-sm font-semibold text-[var(--text-primary)]">
                        {gateName(readout, gate.gate_id)}
                      </span>
                      <span className="text-xs text-[var(--text-muted)]">
                        {gate.determination ? humanise(gate.determination) : ''} · {gate.verified_count} of{' '}
                        {gate.total_evidence} items verified
                      </span>
                    </div>
                    {killers.length > 0 && (
                      <p className="mt-1 text-xs text-[var(--text-secondary)]">
                        Deal-killer items open: {killers.join(', ')}
                      </p>
                    )}
                    {(gate.blocked_reasons ?? []).map(reason => (
                      <p key={reason} className="mt-1 text-xs text-red-700 dark:text-red-400">{reason}</p>
                    ))}
                  </li>
                )
              })}
              {shortfalls.map(s => (
                <li key={`${s.gate}-${s.kind}-${s.message}`} className="py-2.5 text-xs text-red-700 dark:text-red-400">
                  {s.gate ? `${gateShortId(s.gate)} · ` : ''}{s.message}
                </li>
              ))}
            </ul>
          </>
        )}
        <Link
          to={GATES_AND_EVIDENCE}
          className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-[var(--brand)] hover:underline"
        >
          Work on these in Gates &amp; Evidence <ArrowRight className="w-3 h-3" />
        </Link>
      </Panel>

      <Panel title="Commitment ladders">
        <div className="grid gap-3 sm:grid-cols-2">
          <LevelRow name="Offtake" level={readout.offtake} />
          <LevelRow name="EPC" level={readout.epc} />
        </div>
      </Panel>

      <Panel title="Capital decisions">
        <p className="text-sm text-[var(--text-primary)]">
          Eligible for a capital decision: <strong>{eligible.length} of {decisions.length}</strong>
        </p>
        {rules?.capital_semantics && (
          <p className="mt-1 text-xs text-[var(--text-muted)]">{rules.capital_semantics}</p>
        )}
        <ul className="mt-3 divide-y divide-[var(--border)]">
          {decisions.map(d => (
            <li key={d.capital_type} className="flex flex-wrap items-baseline justify-between gap-2 py-2 text-xs">
              <span className="font-medium text-[var(--text-primary)]">{d.label ?? humanise(d.capital_type)}</span>
              <span className={isEligible(d) ? 'font-semibold text-emerald-700 dark:text-emerald-400' : 'text-[var(--text-muted)]'}>
                {isEligible(d)
                  ? 'Eligible'
                  : `Waiting on ${d.gating_gates.map(g => gateName(readout, g)).join(', ')}`}
              </span>
            </li>
          ))}
        </ul>
      </Panel>

      {readout.rules_version && (
        <p className="text-[10px] text-[var(--text-muted)]">Gate engine · evidence rules {readout.rules_version}</p>
      )}
    </>
  )
}

function LevelRow({ name, level }: { name: string; level?: EngineLevel }) {
  return (
    <div className="rounded-lg border border-[var(--border)] px-3 py-2">
      <div className="text-xs text-[var(--text-muted)]">{name}</div>
      <div className="text-sm font-bold text-[var(--text-primary)]">{level?.level ?? 'not reported'}</div>
      {level?.reasons?.[0] && <p className="mt-0.5 text-xs text-[var(--text-secondary)]">{level.reasons[0]}</p>}
    </div>
  )
}

function Panel({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-5 py-4">
      {title && <h2 className="mb-2 text-sm font-bold text-[var(--text-primary)]">{title}</h2>}
      {children}
    </section>
  )
}
