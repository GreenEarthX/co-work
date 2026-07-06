/**
 * Formula resolver — resolves all derived parameters for an equipment instance.
 * Pure function — no side effects, no mutation of inputs.
 */
import type {
  ParameterValue,
  EquipmentEngineState,
  RuleFinding,
  ValueSource,
  FormulaDef,
} from '../types';
import { ARCHETYPE_PROFILES } from '../registry/archetypeProfiles';
import { DEFAULT_LIBRARY } from '../registry/defaultLibrary';
import { getApplicableFormulas, buildGraph } from './dependencyGraph';
import { FORMULAS } from '../registry/formulas';
import { executeFormula } from './formulaImplementations';
import { convertToCanonical } from '../units/converter';
import { getParameterDef } from '../registry/unitFamilies';

/**
 * Resolve all derived parameters for one equipment instance.
 *
 * Override hierarchy: USER > OVERRIDE > DEFAULT_LIBRARY > ARCHETYPE_PROFILE > DERIVED
 */
export function resolveEquipment(
  equipmentInstanceId: string,
  archetypeId: string,
  equipmentName: string | null,
  userValues: Record<string, ParameterValue>,
  plantLevelParams?: Record<string, ParameterValue>,
): EquipmentEngineState {
  const profile = (ARCHETYPE_PROFILES as readonly typeof ARCHETYPE_PROFILES[number][])
    .find(p => p.archetypeId === archetypeId);

  // Collect model IDs: profile models + all models from archetype/equipment-scoped formulas
  const modelIds = new Set<string>();
  if (profile) {
    if (profile.throughputModelId !== 'NONE') modelIds.add(profile.throughputModelId);
    if (profile.electricityModelId !== 'NONE') modelIds.add(profile.electricityModelId);
    if (profile.heatModelId !== 'NONE') modelIds.add(profile.heatModelId);
  }

  // Discover all models referenced by archetype- and equipment-scoped formulas
  for (const f of FORMULAS as readonly FormulaDef[]) {
    if (f.scopeType === 'ARCHETYPE' && f.scopeId === archetypeId) modelIds.add(f.appliesToModelId);
    if (f.scopeType === 'EQUIPMENT' && equipmentName && f.scopeId === equipmentName) modelIds.add(f.appliesToModelId);
  }

  const finalFormulas = getApplicableFormulas(archetypeId, equipmentName, [...modelIds]);

  // Prune formulas whose output is already user-provided (breaks bidirectional cycles)
  const userProvidedKeys = new Set(
    Object.entries(userValues)
      .filter(([, pv]) => pv.value != null)
      .map(([k]) => k),
  );
  if (plantLevelParams) {
    for (const k of Object.keys(plantLevelParams)) userProvidedKeys.add(k);
  }
  const prunedFormulas = finalFormulas.filter(f => !userProvidedKeys.has(f.outputParamKey));

  // Build dependency graph
  const graph = buildGraph(prunedFormulas);

  // Initialize parameter map with deep copies
  const parameters = new Map<string, ParameterValue>();

  // 1. Plant-level inherited values (e.g. HOURS_YEAR)
  if (plantLevelParams) {
    for (const [key, pv] of Object.entries(plantLevelParams)) {
      parameters.set(key, { ...pv, isDirty: false });
    }
  }

  // 2. Default library values
  const defaults = (DEFAULT_LIBRARY as readonly typeof DEFAULT_LIBRARY[number][])
    .filter(d => d.archetypeId === archetypeId);
  for (const def of defaults) {
    if (!parameters.has(def.paramKey)) {
      // Convert default value to canonical unit
      const paramDef = getParameterDef(def.paramKey, archetypeId);
      const unitFamily = paramDef?.unitFamily ?? '';
      const conversion = convertToCanonical(def.defaultValue, def.unit, unitFamily);

      parameters.set(def.paramKey, {
        paramKey: def.paramKey,
        value: def.defaultValue,
        unit: def.unit,
        canonicalValue: conversion.success ? conversion.canonical : def.defaultValue,
        source: 'DEFAULT_LIBRARY' as ValueSource,
        isOverridden: false,
        isDirty: false,
      });
    }
  }

  // 3. User-provided values (highest priority for editable params)
  for (const [key, pv] of Object.entries(userValues)) {
    const existing = parameters.get(key);
    if (pv.value != null) {
      // Convert to canonical
      const paramDef = getParameterDef(key, archetypeId) ?? getParameterDef(key);
      const unitFamily = paramDef?.unitFamily ?? '';
      const conversion = pv.unit
        ? convertToCanonical(pv.value as number, pv.unit, unitFamily)
        : { canonical: pv.value as number, success: true };

      parameters.set(key, {
        ...pv,
        canonicalValue: conversion.success ? conversion.canonical : (pv.value as number),
        source: existing ? 'OVERRIDE' as ValueSource : pv.source,
        isOverridden: existing != null && existing.source !== 'USER',
        isDirty: false,
      });
    }
  }

  // 4. Walk topological execution order and compute derived values
  const findings: RuleFinding[] = [];

  for (const formulaId of graph.executionOrder) {
    const node = graph.nodes.get(formulaId);
    if (!node) continue;

    const formula = finalFormulas.find(f => f.formulaId === formulaId);
    if (!formula) continue;

    // Check if user already provided an override for this output
    const existingOutput = parameters.get(node.outputParamKey);
    if (existingOutput && (existingOutput.source === 'USER' || existingOutput.source === 'OVERRIDE')) {
      // User override takes precedence — skip computation but keep the value
      continue;
    }

    // Gather inputs from resolved parameters (canonical values)
    const inputValues: Record<string, number | null> = {};
    for (const inputKey of node.inputParamKeys) {
      const param = parameters.get(inputKey);
      inputValues[inputKey] = param?.canonicalValue ?? null;
    }

    const result = executeFormula(formula, inputValues);

    if (result != null && isFinite(result)) {
      const paramDef = getParameterDef(node.outputParamKey, archetypeId)
        ?? getParameterDef(node.outputParamKey);

      parameters.set(node.outputParamKey, {
        paramKey: node.outputParamKey,
        value: result,
        unit: paramDef?.canonicalUnit ?? '',
        canonicalValue: result,
        source: 'DERIVED' as ValueSource,
        isOverridden: false,
        isDirty: false,
      });
    }
    // If result is null, skip — inputs not available
  }

  return {
    equipmentInstanceId,
    archetypeId,
    parameters,
    findings,
    lastComputedAt: Date.now(),
  };
}
