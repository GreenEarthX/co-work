// Screen: Capital Eligibility (/finance-bankability, /finance/bankability)
/**
 * Capital Eligibility — which capital providers' decisions the project's
 * evidence makes it eligible for, and which gates each decision still waits on.
 *
 * Everything comes from one engine readout (useEngineReadout), the same one
 * /projects and State & Blockers read. GEX makes a project eligible for a
 * capital provider's decision; it does not commit, release or draw capital (D3).
 *
 * Removed 2026-09-30 (docs/master-reconciliation/06_gate_screens_inventory.md):
 * the fixture fallback, the package-state strip and capital bar built from the
 * customerProjects.ts fixture, and the pre-COD metrics panel (D11 keeps that
 * metric set out of client material).
 */
import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle, CheckCircle, ChevronDown, ChevronUp, Clock, FileCheck, Info, RefreshCw, X,
} from 'lucide-react';
import { useVisibleProjects } from '@/hooks/useVisibleProjects';
import { useSelectedProject } from '@/contexts/ProjectContext';
import { useEngineReadout, useEngineRules, useVocabularyLabel } from '@/hooks/useEngineReadout';
import { DeclaredVsEvidenced } from '@/components/DeclaredVsEvidenced';
import {
  applicableDecisions, gateName, gatesSatisfied, humanise, isEligible, refusalReason,
  type EngineGate, type EngineReadout,
} from '@/lib/engineReadout';

// ─── Tooltip ──────────────────────────────────────────────────────────────────

function InfoTip({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative inline-flex">
      <button
        className="inline-flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--brand)] transition-colors"
        onClick={() => setOpen(v => !v)}
        aria-label="Show details"
      >
        <Info className="w-3.5 h-3.5" />
      </button>
      {open && (
        <div className="absolute z-50 bottom-full mb-2 left-1/2 -translate-x-1/2 w-72 rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-dropdown p-3 text-xs text-[var(--text-secondary)] leading-relaxed animate-fade-in">
          <button
            className="absolute top-2 right-2 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            onClick={() => setOpen(false)}
            aria-label="Close"
          >
            <X className="w-3 h-3" />
          </button>
          {text}
        </div>
      )}
    </div>
  );
}

function progressColor(pct: number, complete: boolean) {
  if (complete || pct >= 100) return 'bg-emerald-500';
  if (pct >= 75) return 'bg-amber-400';
  return 'bg-brand-500';
}

/** The engine's label for each open item on a gate (the key when it has none). */
function openItems(gate: EngineGate): Array<{ key: string; label: string }> {
  return gate.blocking_items.map(key => ({
    key,
    label: gate.evidence_detail?.find(e => e.key === key)?.label ?? key.replace(/_/g, ' '),
  }));
}

// ─── Main component ───────────────────────────────────────────────────────────

export function FinanceBankabilityView({ projectId: propProjectId }: { projectId?: string }) {
  const { selectedProjectId, setSelectedProjectId } = useSelectedProject();
  const { projects: visibleProjects } = useVisibleProjects();
  const projectId = propProjectId ?? selectedProjectId;
  const project = visibleProjects.find(p => p.id === projectId);
  const { data: readout, isLoading, isError, error, refetch, isFetching } = useEngineReadout(projectId);

  return (
    <div className="space-y-4 animate-fade-in">
      {/* ── Project selector ── */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-5 py-3.5 shadow-card">
        <div className="min-w-0">
          <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--text-muted)]">Capital Eligibility</div>
          <div className="mt-0.5 font-display font-bold text-[var(--text-primary)] truncate">
            {project?.name ?? projectId}
          </div>
          {project && (
            <div className="text-xs text-[var(--text-muted)]">{project.location} · {project.molecule}</div>
          )}
        </div>
        <select
          value={projectId}
          onChange={e => setSelectedProjectId(e.target.value)}
          className="gex-select text-sm shrink-0"
          aria-label="Select project"
        >
          {visibleProjects.map(p => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-48">
          <div className="h-7 w-7 rounded-full border-2 border-[var(--brand)] border-t-transparent animate-spin" />
        </div>
      ) : isError || !readout ? (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-5 py-4 shadow-card">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            The gate engine did not answer, so no determination is shown.
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
        </div>
      ) : (
        <Readout readout={readout} />
      )}
    </div>
  );
}

function Readout({ readout }: { readout: EngineReadout }) {
  const navigate = useNavigate();
  const stateLabel = useVocabularyLabel('readiness');
  const { data: rules } = useEngineRules();
  const [expanded, setExpanded] = useState<string | null>(null);
  const [expandedGate, setExpandedGate] = useState<string | null>(null);
  const gateRowRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // The finance view's gates are the engine's FINANCE persona gates.
  const financeGateIds = rules?.persona_gates?.FINANCE;
  const financeGates = financeGateIds
    ? readout.gate_evaluations.filter(g => financeGateIds.includes(g.gate_id))
    : readout.gate_evaluations;
  const gates = gatesSatisfied(readout);
  const decisions = applicableDecisions(readout);
  const eligibleCount = decisions.filter(isEligible).length;
  const gateById = (id: string) => readout.gate_evaluations.find(g => g.gate_id === id);
  const blocking = readout.gates_blocking_next_state ?? [];
  const shortfalls = readout.commitments_blocking_next_state ?? [];

  // Open the Data Room on a gate's evidence bucket and the named document.
  const openEvidence = (gateId: string, evidenceKey: string) => {
    const qs = new URLSearchParams({ gate: gateId, evidence: evidenceKey }).toString();
    navigate(`/finance/data-room?${qs}`);
  };

  // Open a gate row and scroll it into view, when it is on this screen.
  const jumpToGate = (gateId: string) => {
    setExpandedGate(gateId);
    requestAnimationFrame(() => {
      gateRowRefs.current[gateId]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  };

  return (
    <>
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-5 py-3 shadow-card">
        <DeclaredVsEvidenced readout={readout} />
      </div>

      {/* ── Engine counts ── */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'Gates satisfied', value: `${gates.satisfied} of ${gates.applicable}` },
          { label: 'Evidence verified', value: `${readout.total_verified} of ${readout.total_evidence}` },
          { label: 'Eligible for a capital decision', value: `${eligibleCount} of ${decisions.length}` },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 shadow-card">
            <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--text-muted)]">{label}</div>
            <div className="mt-1 font-display text-2xl font-extrabold leading-none text-[var(--text-primary)]">{value}</div>
          </div>
        ))}
      </div>

      {readout.regression && (
        <div className="flex gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-800/40 dark:bg-amber-900/15">
          <AlertTriangle className="mt-0.5 w-4 h-4 shrink-0 text-amber-600 dark:text-amber-400" />
          <p className="text-xs text-amber-700 dark:text-amber-300">
            State fell from {stateLabel(readout.regression.from_state)} to {stateLabel(readout.regression.to_state)}
            {readout.regression.reason ? `: ${readout.regression.reason}` : ''}
          </p>
        </div>
      )}

      {/* ── Next state ── */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--brand-light)] px-4 py-2.5">
        <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--brand)]">Next state · </span>
        <span className="text-xs text-[var(--text-secondary)]">
          {readout.next_state
            ? `${stateLabel(readout.next_state)}${readout.next_state_label ? ` (${readout.next_state_label})` : ''}` +
              (blocking.length > 0 ? ` — waiting on ${blocking.map(g => gateName(readout, g)).join(', ')}` : '') +
              (shortfalls.length > 0 ? `; ${shortfalls.map(s => s.message).join('; ')}` : '')
            : 'No further state.'}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* ── Capital decisions ── */}
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
          <div className="flex items-center gap-2 border-b border-[var(--border)] px-5 py-3.5">
            <h3 className="flex-1 text-sm font-bold text-[var(--text-primary)]">Capital decisions</h3>
            {rules?.capital_semantics && <InfoTip text={rules.capital_semantics} />}
          </div>

          <div className="divide-y divide-[var(--border)]">
            {decisions.map(decision => {
              const eligible = isEligible(decision);
              const isOpen = expanded === decision.capital_type;
              const gatingNames = decision.gating_gates.map(g => gateName(readout, g)).join(', ');
              return (
                <div key={decision.capital_type}>
                  <div className="flex items-center gap-3 px-5 py-3.5">
                    <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${eligible ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400' : 'bg-[var(--surface-muted)] text-[var(--text-muted)]'}`}>
                      {eligible ? <CheckCircle className="w-4 h-4" /> : <Clock className="w-4 h-4" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <span className="block text-sm font-semibold text-[var(--text-primary)] truncate">
                        {decision.label ?? humanise(decision.capital_type)}
                      </span>
                      <span className={`mt-0.5 block text-[11px] ${eligible ? 'text-emerald-700 dark:text-emerald-400' : 'text-[var(--text-muted)]'}`}>
                        {eligible ? 'Eligible' : `Waiting on ${gatingNames}`}
                      </span>
                    </div>
                    {decision.gating_gates.length > 0 && (
                      <button
                        className="shrink-0 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                        onClick={() => setExpanded(isOpen ? null : decision.capital_type)}
                        aria-label="Toggle gate details"
                      >
                        {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                      </button>
                    )}
                  </div>

                  {isOpen && (
                    <div className="border-t border-[var(--border)] bg-[var(--surface-muted)] px-5 py-3 space-y-3 animate-fade-in">
                      {decision.gating_gates.map(gid => {
                        const g = gateById(gid);
                        if (!g) return null;
                        const items = openItems(g);
                        const onScreen = financeGates.some(x => x.gate_id === gid);
                        return (
                          <div key={gid} className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
                            <div className="flex items-center justify-between gap-2">
                              {onScreen ? (
                                <button
                                  onClick={() => jumpToGate(gid)}
                                  className="text-xs font-semibold text-[var(--brand)] hover:underline text-left"
                                >
                                  {gateName(readout, gid)} →
                                </button>
                              ) : (
                                <span className="text-xs font-semibold text-[var(--text-primary)]">{gateName(readout, gid)}</span>
                              )}
                              <span className="text-[10px] text-[var(--text-muted)]">
                                {g.verified_count} of {g.total_evidence} verified
                              </span>
                            </div>
                            {items.length > 0 && (
                              <div className="mt-2 space-y-1">
                                <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Still to verify</p>
                                {items.map(item => (
                                  <button
                                    key={item.key}
                                    onClick={() => openEvidence(gid, item.key)}
                                    className="flex w-full items-center gap-2 text-[11px] text-left hover:bg-[var(--surface-muted)] rounded px-1 py-0.5 group"
                                    title={`Open ${item.label} in Data Room`}
                                  >
                                    <span className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0" />
                                    <span className="text-[var(--text-secondary)] group-hover:text-[var(--brand)] group-hover:underline">
                                      {item.label}
                                    </span>
                                    <span className="ml-auto text-[10px] text-[var(--text-muted)] group-hover:text-[var(--brand)]">→ Data Room</span>
                                  </button>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* ── Financial gates ── */}
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card">
          <div className="flex items-center gap-2 border-b border-[var(--border)] px-5 py-3.5">
            <FileCheck className="w-4 h-4 text-[var(--brand)]" />
            <h3 className="flex-1 text-sm font-bold text-[var(--text-primary)]">Financial gates</h3>
            <InfoTip text="The gates a lender reviews, with the engine's determination and how many of each gate's applicable evidence items are verified." />
          </div>

          <div className="divide-y divide-[var(--border)]">
            {financeGates.map(gate => {
              const pct = Math.round(gate.completion_pct);
              const gateOpen = expandedGate === gate.gate_id;
              const items = openItems(gate);
              return (
                <div
                  key={gate.gate_id}
                  ref={(el) => { gateRowRefs.current[gate.gate_id] = el; }}
                  className={`px-5 py-4 transition-colors ${gateOpen ? 'bg-[var(--brand-soft,rgba(14,165,160,0.06))]' : ''}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-[var(--text-primary)] leading-tight">{gateName(readout, gate.gate_id)}</p>
                      {gate.determination && (
                        <p className="text-xs text-[var(--text-muted)] mt-0.5">{humanise(gate.determination)}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {gate.determination === 'SATISFIED'
                        ? <CheckCircle className="w-4 h-4 text-emerald-500" />
                        : <span className="text-[10px] font-mono text-[var(--text-muted)]">{gate.verified_count}/{gate.total_evidence} verified</span>}
                      {items.length > 0 && (
                        <button
                          className="shrink-0 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                          onClick={() => setExpandedGate(gateOpen ? null : gate.gate_id)}
                          aria-label="Toggle open items"
                        >
                          {gateOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-[var(--border)]">
                    <div className={`h-full rounded-full transition-all duration-500 ${progressColor(pct, gate.determination === 'SATISFIED')}`} style={{ width: `${pct}%` }} />
                  </div>

                  {gateOpen && items.length > 0 && (
                    <div className="mt-2 space-y-1 animate-fade-in">
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Still to verify</p>
                      {items.map(item => (
                        <button
                          key={item.key}
                          onClick={() => openEvidence(gate.gate_id, item.key)}
                          className="flex w-full items-center gap-2 text-[11px] text-left hover:bg-[var(--surface-muted)] rounded px-1 py-0.5 group"
                          title={`Open ${item.label} in Data Room`}
                        >
                          <span className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0" />
                          <span className="text-red-600 dark:text-red-400 font-medium group-hover:underline">{item.label}</span>
                          <span className="ml-auto text-[10px] text-[var(--text-muted)] group-hover:text-[var(--brand)]">→ Data Room</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {readout.rules_version && (
        <p className="text-[10px] text-[var(--text-muted)]">Gate engine · evidence rules {readout.rules_version}</p>
      )}
    </>
  );
}
