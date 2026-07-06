/**
 * Stateful equation engine — manages all equipment instances,
 * resolves formulas, and notifies subscribers on change.
 * Synchronous for real-time form updates (< 16ms target).
 */
import type {
  EquipmentEngineState,
  ParameterValue,
  RuleFinding,
  ValueSource,
} from './types';
import { resolveEquipment } from './solver/formulaResolver';
import { runCheck, runCheckForEquipment } from './checker/ruleChecker';
import { convertToCanonical, convertFromCanonical } from './units/converter';
import { getParameterDef, getUnitFamily } from './registry/unitFamilies';

type Listener = (states: Map<string, EquipmentEngineState>) => void;

interface EquipmentMeta {
  archetypeId: string;
  equipmentName: string | null;
  userValues: Record<string, { value: number | null; unit: string }>;
}

export class EquationEngine {
  private equipmentStates: Map<string, EquipmentEngineState> = new Map();
  private equipmentMeta: Map<string, EquipmentMeta> = new Map();
  private plantParams: Map<string, ParameterValue> = new Map();
  private listeners: Set<Listener> = new Set();

  /** Register or fully update an equipment instance. */
  setEquipmentInstance(
    instanceId: string,
    archetypeId: string,
    equipmentName: string | null,
    userValues: Record<string, { value: number | null; unit: string }>,
  ): EquipmentEngineState {
    this.equipmentMeta.set(instanceId, { archetypeId, equipmentName, userValues });

    const pvMap = this.buildParameterValues(archetypeId, userValues);
    const plantRecord = this.plantParamsAsRecord();

    const state = resolveEquipment(instanceId, archetypeId, equipmentName, pvMap, plantRecord);
    this.equipmentStates.set(instanceId, state);
    this.notify();
    return state;
  }

  /** Update a single parameter (real-time, fast path). */
  updateParameter(
    instanceId: string,
    paramKey: string,
    value: number | null,
    unit: string,
  ): EquipmentEngineState | null {
    const meta = this.equipmentMeta.get(instanceId);
    if (!meta) return null;

    // Update the stored user values
    meta.userValues = { ...meta.userValues, [paramKey]: { value, unit } };

    const pvMap = this.buildParameterValues(meta.archetypeId, meta.userValues);
    const plantRecord = this.plantParamsAsRecord();

    const state = resolveEquipment(
      instanceId, meta.archetypeId, meta.equipmentName, pvMap, plantRecord,
    );
    this.equipmentStates.set(instanceId, state);
    this.notify();
    return state;
  }

  /** Run consistency/validation checks on all equipment. */
  runCheck(): RuleFinding[] {
    return runCheck([...this.equipmentStates.values()]);
  }

  /** Run checks for a single equipment instance. */
  runCheckForEquipment(instanceId: string): RuleFinding[] {
    const state = this.equipmentStates.get(instanceId);
    if (!state) return [];
    return runCheckForEquipment(state);
  }

  getEquipmentState(instanceId: string): EquipmentEngineState | null {
    return this.equipmentStates.get(instanceId) ?? null;
  }

  getAllStates(): Map<string, EquipmentEngineState> {
    return this.equipmentStates;
  }

  /** Get a resolved value, optionally converted to a desired display unit. */
  getResolvedValue(
    instanceId: string,
    paramKey: string,
    desiredUnit?: string,
  ): { value: number | null; unit: string; source: ValueSource; isOverridden: boolean } | null {
    const state = this.equipmentStates.get(instanceId);
    if (!state) return null;
    const pv = state.parameters.get(paramKey);
    if (!pv) return null;

    if (!desiredUnit || desiredUnit === pv.unit || pv.canonicalValue == null) {
      return { value: pv.canonicalValue, unit: pv.unit, source: pv.source, isOverridden: pv.isOverridden };
    }

    const meta = this.equipmentMeta.get(instanceId);
    const paramDef = getParameterDef(paramKey, meta?.archetypeId) ?? getParameterDef(paramKey);
    if (!paramDef) {
      return { value: pv.canonicalValue, unit: pv.unit, source: pv.source, isOverridden: pv.isOverridden };
    }

    const result = convertFromCanonical(pv.canonicalValue, desiredUnit, paramDef.unitFamily);
    return {
      value: result.success ? result.value : pv.canonicalValue,
      unit: result.success ? desiredUnit : pv.unit,
      source: pv.source,
      isOverridden: pv.isOverridden,
    };
  }

  /** Get parameter metadata for UI rendering. */
  getParameterMeta(paramKey: string, archetypeId: string): {
    displayName: string;
    description: string;
    isUserEditable: boolean;
    supportsOverride: boolean;
    typicalSource: ValueSource;
    isDerived: boolean;
    canonicalUnit: string;
    allowedUnits: string[];
  } | null {
    const def = getParameterDef(paramKey, archetypeId) ?? getParameterDef(paramKey);
    if (!def) return null;

    const family = getUnitFamily(def.unitFamily);
    return {
      displayName: def.displayName,
      description: def.description,
      isUserEditable: def.isUserEditable,
      supportsOverride: def.supportsOverride,
      typicalSource: def.typicalSource,
      isDerived: def.derivedByModelId != null,
      canonicalUnit: def.canonicalUnit,
      allowedUnits: family ? [...family.allowedUnits] : [def.canonicalUnit],
    };
  }

  removeEquipment(instanceId: string): void {
    this.equipmentStates.delete(instanceId);
    this.equipmentMeta.delete(instanceId);
    this.notify();
  }

  /** Set a plant-level parameter shared across all equipment (e.g. HOURS_YEAR). */
  setPlantParameter(paramKey: string, value: number, unit: string): void {
    const paramDef = getParameterDef(paramKey);
    const unitFamily = paramDef?.unitFamily ?? '';
    const conversion = convertToCanonical(value, unit, unitFamily);

    this.plantParams.set(paramKey, {
      paramKey,
      value,
      unit,
      canonicalValue: conversion.success ? conversion.canonical : value,
      source: 'USER',
      isOverridden: false,
      isDirty: false,
    });

    // Re-resolve all equipment with updated plant params
    for (const [id, meta] of this.equipmentMeta) {
      const pvMap = this.buildParameterValues(meta.archetypeId, meta.userValues);
      const state = resolveEquipment(id, meta.archetypeId, meta.equipmentName, pvMap, this.plantParamsAsRecord());
      this.equipmentStates.set(id, state);
    }
    this.notify();
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  }

  private notify(): void {
    for (const fn of this.listeners) {
      try { fn(this.equipmentStates); } catch { /* swallow */ }
    }
  }

  private buildParameterValues(
    archetypeId: string,
    userValues: Record<string, { value: number | null; unit: string }>,
  ): Record<string, ParameterValue> {
    const result: Record<string, ParameterValue> = {};
    for (const [key, uv] of Object.entries(userValues)) {
      if (uv.value == null) continue;
      const paramDef = getParameterDef(key, archetypeId) ?? getParameterDef(key);
      const unitFamily = paramDef?.unitFamily ?? '';
      const conversion = convertToCanonical(uv.value, uv.unit, unitFamily);
      result[key] = {
        paramKey: key,
        value: uv.value,
        unit: uv.unit,
        canonicalValue: conversion.success ? conversion.canonical : uv.value,
        source: 'USER',
        isOverridden: false,
        isDirty: true,
      };
    }
    return result;
  }

  private plantParamsAsRecord(): Record<string, ParameterValue> {
    const rec: Record<string, ParameterValue> = {};
    for (const [k, v] of this.plantParams) rec[k] = v;
    return rec;
  }
}

/** Singleton for app-wide use. */
export const engineInstance = new EquationEngine();
