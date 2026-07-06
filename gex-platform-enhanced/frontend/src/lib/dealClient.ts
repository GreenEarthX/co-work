/**
 * dealClient — typed methods for the gex_pf_engine deal endpoints + helpers
 * to persist src/engine/ run outcomes to Supabase.
 *
 * Builds on engineClient (Sprint 1) for the HTTP transport and auth handling;
 * everything here is just type-safe wrappers + the Supabase persistence side.
 */
import { engineFetch, engineQueryKeys, EngineHttpError } from "./engineClient";
import { supabase } from "@/integrations/supabase/client";
import type {
  DealInputs,
  ComputeOutput,
  EquationEngineRun,
  EngineRunStatus,
  EngineViolation,
  LatestEngineRun,
} from "@/types/deal";

type SupabaseQuery = {
  insert(value: unknown): SupabaseQuery;
  select(columns?: string): SupabaseQuery;
  single(): Promise<{ data: unknown; error: { message: string } | null }>;
  eq(column: string, value: unknown): SupabaseQuery;
  maybeSingle(): Promise<{ data: unknown; error: { message: string } | null }>;
  order(column: string, options?: { ascending: boolean }): SupabaseQuery;
  limit(count: number): Promise<{ data: unknown[] | null; error: { message: string } | null }>;
};

type SupabaseDataClient = typeof supabase & {
  from(table: string): SupabaseQuery;
  rpc(
    fn: string,
    args: Record<string, unknown>,
  ): Promise<{ data: unknown; error: { message: string } | null }>;
};

const db = supabase as SupabaseDataClient;

// ---------------------------------------------------------------------------
// Deal compute
// ---------------------------------------------------------------------------

export interface ComputeRequest {
  inputs: DealInputs;
  scenario?: "worst" | "base" | "best";
}

/**
 * Run the Python phased compute on a deal structure.
 *
 * Pre-conditions enforced by the engine (will raise if not met):
 *   - the plant's latest equation_engine_run.status must be 'clean', else
 *     the engine returns a degraded output with errors[].code='engine_run_not_clean'
 *   - the user_id on the deal must match the authenticated user
 *
 * @throws EngineHttpError on 4xx/5xx
 * @throws EngineUnauthenticated when no Supabase session is available
 */
export async function computeDeal(
  dealStructureId: string,
  request: ComputeRequest,
): Promise<ComputeOutput> {
  return engineFetch<ComputeOutput>({
    path: `/deals/${encodeURIComponent(dealStructureId)}/compute`,
    method: "POST",
    body: request,
  });
}

// React Query keys for the deal compute endpoint
export const dealQueryKeys = {
  all: ["deals"] as const,
  compute: (dealStructureId: string, inputsHash: string) =>
    [...dealQueryKeys.all, "compute", dealStructureId, inputsHash] as const,
  output: (dealStructureId: string) =>
    [...dealQueryKeys.all, "output", dealStructureId] as const,
} as const;

// ---------------------------------------------------------------------------
// Equation engine run persistence — src/engine/ elevation
// ---------------------------------------------------------------------------

/**
 * After src/engine/ finishes a run, call this to persist the outcome.
 * The trigger in migration 130001 will:
 *   - cascade has_deal_killer to plants.deal_killer_flag
 *   - mark the source as 'engine' so a manual deal-killer isn't overwritten
 *
 * The plant cannot be marked CONFIRMED until a clean run exists. The trigger
 * does NOT directly elevate the plant verification state — that remains a
 * user action via transition_verification_state(); this just makes the
 * action possible by satisfying the engine precondition.
 */
export async function persistEngineRun(args: {
  plantId: string;
  engineVersion: string;
  inputsHash: string;
  status: EngineRunStatus;
  formulaDagResolved: boolean;
  massBalanceClosed: boolean;
  energyBalanceClosed: boolean;
  unitCheckPassed: boolean;
  ruleCheckPassed: boolean;
  violations: EngineViolation[];
  warnings?: EngineViolation[];
  metrics?: Record<string, unknown>;
}): Promise<EquationEngineRun> {
  const hasDealKiller = args.violations.some(v => v.severity === "deal_killer");

  const { data, error } = await db
    .from("equation_engine_runs")
    .insert({
      plant_id: args.plantId,
      engine_version: args.engineVersion,
      inputs_hash: args.inputsHash,
      status: args.status,
      formula_dag_resolved: args.formulaDagResolved,
      mass_balance_closed: args.massBalanceClosed,
      energy_balance_closed: args.energyBalanceClosed,
      unit_check_passed: args.unitCheckPassed,
      rule_check_passed: args.ruleCheckPassed,
      violations: args.violations,
      warnings: args.warnings ?? [],
      metrics: args.metrics ?? {},
      has_deal_killer: hasDealKiller,
    })
    .select()
    .single();

  if (error) {
    throw new Error(`Failed to persist engine run: ${error.message}`);
  }
  return data as EquationEngineRun;
}

/** Fetch the most recent engine run for a plant. */
export async function getLatestEngineRun(
  plantId: string,
): Promise<LatestEngineRun | null> {
  const { data, error } = await db
    .from("v_latest_engine_run")
    .select("*")
    .eq("plant_id", plantId)
    .maybeSingle();
  if (error) throw new Error(error.message);
  return (data as LatestEngineRun | null) ?? null;
}

/** Full history of engine runs for a plant. Ordered newest first. */
export async function getEngineRunHistory(
  plantId: string,
  limit = 50,
): Promise<EquationEngineRun[]> {
  const { data, error } = await db
    .from("equation_engine_runs")
    .select("*")
    .eq("plant_id", plantId)
    .order("ran_at", { ascending: false })
    .limit(limit);
  if (error) throw new Error(error.message);
  return (data ?? []) as EquationEngineRun[];
}

// ---------------------------------------------------------------------------
// Verification state transitions — wraps the SQL function
// ---------------------------------------------------------------------------

/**
 * Transition a row's verification state through the audited workflow.
 * Calls transition_verification_state() in Postgres, which:
 *   - enforces the engine precondition (plants → CONFIRMED requires clean run)
 *   - writes an audit row to verification_state_transitions
 *   - rejects backward transitions without a reason
 */
export async function transitionVerificationState(args: {
  targetTable:
    | "plants"
    | "equipment_equations"
    | "project_finance"
    | "deal_structures"
    | "debt_tranches"
    | "offtake_contracts"
    | "equation_engine_runs";
  targetId: string;
  toState: "UNVERIFIED" | "SUBMITTED" | "CONFIRMED" | "AUDITED";
  reason?: string;
  evidenceIds?: string[];
}) {
  const { data, error } = await db.rpc("transition_verification_state", {
    p_target_table: args.targetTable,
    p_target_id: args.targetId,
    p_target_field: "verification_state",
    p_to_state: args.toState,
    p_reason: args.reason ?? null,
    p_evidence_ids: args.evidenceIds ?? null,
  });
  if (error) {
    // Surface the SQL-level rejection (e.g. "no equation engine run exists")
    // verbatim to the caller — these messages are user-facing already.
    throw new Error(error.message);
  }
  return data;
}

// ---------------------------------------------------------------------------
// Re-exports
// ---------------------------------------------------------------------------
export { EngineHttpError, engineQueryKeys };
export type { ComputeOutput, DealInputs };
