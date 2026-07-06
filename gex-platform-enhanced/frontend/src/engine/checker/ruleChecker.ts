/**
 * Rule checker — main entry point for running all consistency & validation checks.
 * Pure functions — never throws, always returns findings.
 */
import type { EquipmentEngineState, RuleFinding, Severity } from '../types';
import {
  ALL_CONSISTENCY_CHECKS,
  ALL_VALIDATION_CHECKS,
  checkMissingInputs,
  checkOverdetermined,
} from './consistencyChecks';
import { ARCHETYPE_PROFILES } from '../registry/archetypeProfiles';
import { getApplicableFormulas } from '../solver/dependencyGraph';

const SEVERITY_ORDER: Record<Severity, number> = {
  ERROR: 0,
  WARNING: 1,
  CONSISTENCY: 2,
  VALIDATION: 3,
  CONTINUITY: 4,
  INFO: 5,
};

/**
 * Run all applicable checks for a single equipment instance.
 */
export function runCheckForEquipment(state: EquipmentEngineState): RuleFinding[] {
  const findings: RuleFinding[] = [];

  // 1. Run all consistency checks (each self-guards on missing params)
  for (const check of ALL_CONSISTENCY_CHECKS) {
    try {
      findings.push(...check(state));
    } catch {
      // Never throw from a check
    }
  }

  // 2. Run validation checks
  for (const check of ALL_VALIDATION_CHECKS) {
    try {
      findings.push(...check(state));
    } catch {
      // Never throw
    }
  }

  // 3. Missing inputs check — determine required keys from archetype formulas
  try {
    const profile = (ARCHETYPE_PROFILES as readonly typeof ARCHETYPE_PROFILES[number][])
      .find(p => p.archetypeId === state.archetypeId);
    if (profile) {
      const modelIds: string[] = [];
      if (profile.throughputModelId !== 'NONE') modelIds.push(profile.throughputModelId);
      if (profile.electricityModelId !== 'NONE') modelIds.push(profile.electricityModelId);
      if (profile.heatModelId !== 'NONE') modelIds.push(profile.heatModelId);

      const formulas = getApplicableFormulas(state.archetypeId, null, modelIds);
      const requiredInputs = new Set<string>();
      const derivedOutputs: string[] = [];
      for (const f of formulas) {
        for (const k of f.inputParamKeys) requiredInputs.add(k);
        derivedOutputs.push(f.outputParamKey);
      }
      // Remove keys that are outputs of other formulas (they'll be derived)
      for (const o of derivedOutputs) requiredInputs.delete(o);

      findings.push(...checkMissingInputs(state, [...requiredInputs]));
      findings.push(...checkOverdetermined(state, derivedOutputs));
    }
  } catch {
    // Never throw
  }

  // Sort by severity
  findings.sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9));

  return findings;
}

/**
 * Run checks across multiple equipment instances.
 */
export function runCheck(equipmentStates: EquipmentEngineState[]): RuleFinding[] {
  const allFindings: RuleFinding[] = [];
  for (const state of equipmentStates) {
    allFindings.push(...runCheckForEquipment(state));
  }
  allFindings.sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9));
  return allFindings;
}
