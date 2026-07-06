/**
 * React hooks for the equation engine.
 * useSyncExternalStore for tear-free reads; debounced updates for typing.
 */
import { useCallback, useMemo, useRef, useSyncExternalStore } from 'react';
import type { RuleFinding, ValueSource } from '../types';
import { engineInstance } from '../EquationEngine';
import { getParameterDef } from '../registry/unitFamilies';

/* ── Helpers ── */

function useEngineSnapshot() {
  return useSyncExternalStore(
    (cb) => engineInstance.subscribe(() => cb()),
    () => engineInstance.getAllStates(),
    () => engineInstance.getAllStates(),
  );
}

interface ResolvedParam {
  value: number | null;
  displayValue: string;
  unit: string;
  source: ValueSource;
  isOverridden: boolean;
  isDerived: boolean;
  isEditable: boolean;
}

interface FieldMeta {
  displayName: string;
  description: string;
  allowedUnits: string[];
  canonicalUnit: string;
  isUserEditable: boolean;
  supportsOverride: boolean;
  isDerived: boolean;
}

/* ── useEquipmentEngine ── */

export function useEquipmentEngine(
  instanceId: string,
  archetypeId: string,
  equipmentName?: string,
) {
  const states = useEngineSnapshot();
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const state = states.get(instanceId) ?? null;

  const parameters: Record<string, ResolvedParam> = useMemo(() => {
    if (!state) return {};
    const result: Record<string, ResolvedParam> = {};
    for (const [key, pv] of state.parameters) {
      const def = getParameterDef(key, archetypeId) ?? getParameterDef(key);
      const isDerived = pv.source === 'DERIVED';
      result[key] = {
        value: pv.canonicalValue,
        displayValue: pv.canonicalValue != null ? Number(pv.canonicalValue.toPrecision(6)).toString() : '',
        unit: pv.unit,
        source: pv.source,
        isOverridden: pv.isOverridden,
        isDerived,
        isEditable: def?.isUserEditable ?? !isDerived,
      };
    }
    return result;
  }, [state, archetypeId]);

  const updateField = useCallback((paramKey: string, value: number | null, unit: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      engineInstance.updateParameter(instanceId, paramKey, value, unit);
    }, 150);
  }, [instanceId]);

  const updateFieldImmediate = useCallback((paramKey: string, value: number | null, unit: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    engineInstance.updateParameter(instanceId, paramKey, value, unit);
  }, [instanceId]);

  const toggleOverride = useCallback((paramKey: string, overrideValue?: number) => {
    const pv = state?.parameters.get(paramKey);
    if (!pv) return;
    if (pv.source === 'DERIVED') {
      // Switch to user override
      engineInstance.updateParameter(instanceId, paramKey, overrideValue ?? pv.canonicalValue, pv.unit);
    } else if (pv.source === 'USER' || pv.source === 'OVERRIDE') {
      // Clear override — set to null so engine re-derives
      engineInstance.updateParameter(instanceId, paramKey, null, pv.unit);
    }
  }, [instanceId, state]);

  const findings = useMemo(() => {
    if (!state) return [];
    return engineInstance.runCheckForEquipment(instanceId);
  }, [state, instanceId]);

  const runCheckFn = useCallback(() => {
    return engineInstance.runCheckForEquipment(instanceId);
  }, [instanceId]);

  const getFieldMeta = useCallback((paramKey: string): FieldMeta | null => {
    return engineInstance.getParameterMeta(paramKey, archetypeId);
  }, [archetypeId]);

  // Auto-register on first render if not already registered
  useMemo(() => {
    if (!states.has(instanceId)) {
      engineInstance.setEquipmentInstance(instanceId, archetypeId, equipmentName ?? null, {});
    }
  }, [instanceId, archetypeId, equipmentName, states]);

  return {
    parameters,
    updateField,
    updateFieldImmediate,
    toggleOverride,
    findings,
    runCheck: runCheckFn,
    getFieldMeta,
    isResolving: false, // synchronous engine, always resolved
  };
}

/* ── useEngineCheck ── */

export function useEngineCheck() {
  const states = useEngineSnapshot();

  const findings = useMemo(() => {
    return engineInstance.runCheck();
  }, [states]);

  const findingsByEquipment = useMemo(() => {
    const map = new Map<string, RuleFinding[]>();
    for (const f of findings) {
      const arr = map.get(f.equipmentInstanceId) ?? [];
      arr.push(f);
      map.set(f.equipmentInstanceId, arr);
    }
    return map;
  }, [findings]);

  const runFullCheck = useCallback(() => engineInstance.runCheck(), []);

  return {
    runFullCheck,
    findings,
    findingsByEquipment,
    hasErrors: findings.some(f => f.severity === 'ERROR'),
    hasWarnings: findings.some(f => f.severity === 'WARNING'),
  };
}
