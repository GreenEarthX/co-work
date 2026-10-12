// Screen: Shared (no screen)
/**
 * The gate engine's readout for one project, as the platform proxy returns it
 * (GET /api/v1/bankability/projects/{id}/bankability/EXECUTIVE, all twelve gates).
 *
 * /projects, State & Blockers and Capital Eligibility read every gate, state and
 * capital figure from this object, never from the customerProjects.ts fixture.
 * Field names are the engine's (gex_pf_engine bankability_engine.evaluate).
 */

export interface EngineEvidenceItem {
  key: string;
  label?: string;
  status?: string;
  severity?: string;
  applicable?: boolean;
}

export interface EngineGate {
  gate_id: string;
  gate_name: string;
  determination?: "SATISFIED" | "INCOMPLETE" | "BLOCKED" | "WAIVED";
  is_complete: boolean;
  verified_count: number;
  total_evidence: number;
  completion_pct: number;
  blocking_items: string[];
  blocked_reasons?: string[];
  deal_killers_blocked?: string[];
  evidence_detail?: EngineEvidenceItem[];
  financing_applicable?: boolean;
}

export interface EngineCapitalDecision {
  capital_type: string;
  label?: string;
  decision_eligible?: boolean;
  /** The engine's deprecated alias of decision_eligible. */
  is_unlocked?: boolean;
  financing_applicable?: boolean;
  gating_gates: string[];
}

export interface EngineLevel {
  level: string;
  reasons?: string[];
  coverage_pct?: number | null;
  effective?: boolean;
}

export interface EngineShortfall {
  gate?: string;
  kind?: string;
  message: string;
}

export interface EngineReadout {
  project_id: string;
  rules_version?: string;
  /** The phase the engine was told: the project context, or null. */
  project_phase?: string | null;
  current_state: string;
  state_label?: string | null;
  next_state?: string | null;
  next_state_label?: string | null;
  gates_blocking_next_state?: string[];
  commitments_blocking_next_state?: EngineShortfall[];
  gate_evaluations: EngineGate[];
  capital_unlocks: EngineCapitalDecision[];
  total_verified: number;
  total_evidence: number;
  offtake?: EngineLevel;
  epc?: EngineLevel;
  regression?: {
    from_state: string;
    to_state: string;
    trigger_gate?: string;
    reason?: string;
  } | null;
}

/** "G0_SITE_RIGHTS" → "G0". */
export function gateShortId(gateId: string): string {
  return gateId.split("_")[0];
}

/** The engine's name for a gate, e.g. "G0 Site Rights & Social License". */
export function gateName(readout: EngineReadout, gateId: string): string {
  const gate = readout.gate_evaluations.find((g) => g.gate_id === gateId);
  return gate ? `${gateShortId(gateId)} ${gate.gate_name}` : gateId;
}

export function isEligible(decision: EngineCapitalDecision): boolean {
  return decision.decision_eligible ?? decision.is_unlocked ?? false;
}

/** Capital decisions that apply to this project (balance-sheet funding drops the lender ones). */
export function applicableDecisions(readout: EngineReadout): EngineCapitalDecision[] {
  return readout.capital_unlocks.filter((c) => c.financing_applicable !== false);
}

/** Capital decisions a gate makes the project eligible for. */
export function decisionsGatedBy(readout: EngineReadout, gateId: string): EngineCapitalDecision[] {
  return applicableDecisions(readout).filter((c) => c.gating_gates.includes(gateId));
}

/** Gates the engine says block the next state, in its order. */
export function blockingGates(readout: EngineReadout): EngineGate[] {
  return (readout.gates_blocking_next_state ?? [])
    .map((id) => readout.gate_evaluations.find((g) => g.gate_id === id))
    .filter((g): g is EngineGate => !!g);
}

/** The engine's deal-killer items still open on a gate, by the engine's label. */
export function openDealKillers(gate: EngineGate): string[] {
  const keys = gate.deal_killers_blocked ?? [];
  return keys.map(
    (k) => gate.evidence_detail?.find((e) => e.key === k)?.label ?? k.replace(/_/g, " "),
  );
}

export function gatesSatisfied(readout: EngineReadout): { satisfied: number; applicable: number } {
  const applicable = readout.gate_evaluations.filter((g) => g.determination !== "WAIVED");
  return {
    satisfied: applicable.filter((g) => g.determination === "SATISFIED").length,
    applicable: applicable.length,
  };
}

/**
 * The server's reason for a refusal (4xx) is the user's to read; an outage's
 * (5xx, or no response) is not: it names internals such as a port. Null means
 * "say only that the engine did not answer".
 */
export function refusalReason(error: unknown): string | null {
  const status = (error as { status?: number } | null)?.status;
  return error instanceof Error && typeof status === "number" && status < 500 ? error.message : null;
}

/**
 * Display fallback while the vocabulary loads or if it cannot: the canonical
 * value itself, readable ("TECHNICALLY_PLAUSIBLE" → "Technically plausible").
 * The same words the vocabulary serves; not a second label map.
 */
export function humanise(value: string): string {
  const s = value.replace(/_/g, " ").toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
}
