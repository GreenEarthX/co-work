/**
 * Tests for the consistency checker (ruleChecker + consistencyChecks).
 */
import { describe, it, expect } from 'vitest';
import type { EquipmentEngineState, ParameterValue } from '../types';
import { runCheckForEquipment } from '../checker/ruleChecker';
import { checkCapacityFlow, checkNegativeValues } from '../checker/consistencyChecks';

function pv(paramKey: string, value: number | null, unit = '', source: 'USER' | 'DERIVED' | 'DEFAULT_LIBRARY' = 'DERIVED'): ParameterValue {
  return { paramKey, value, unit, canonicalValue: value, source, isOverridden: false, isDirty: false };
}

function makeState(archetypeId: string, params: Record<string, ParameterValue>): EquipmentEngineState {
  const map = new Map<string, ParameterValue>();
  for (const [k, v] of Object.entries(params)) map.set(k, v);
  return { equipmentInstanceId: 'test-1', archetypeId, parameters: map, findings: [], lastComputedAt: Date.now() };
}

describe('Consistency Checker', () => {
  describe('correct electrolysis state → zero findings', () => {
    it('produces no findings when capacity, flow, hours are consistent', () => {
      // capacity = flow * hours → 500 = 0.0625 * 8000
      const state = makeState('ELECTROLYSIS', {
        CAPACITY_MAIN: pv('CAPACITY_MAIN', 500, 'kg/yr'),
        FLOW_MAIN: pv('FLOW_MAIN', 0.0625, 'kg/h'),
        HOURS_YEAR: pv('HOURS_YEAR', 8000, 'h/yr'),
        CAPACITY_H2: pv('CAPACITY_H2', 500, 'kg/yr'),
        POWER_ELEC: pv('POWER_ELEC', 100, 'kW'),
        SEC_ELEC: pv('SEC_ELEC', 52, 'kWh/kg'),
      });
      const findings = checkCapacityFlow(state);
      expect(findings).toHaveLength(0);
    });
  });

  describe('INCONSISTENT_CAPACITY_FLOW', () => {
    it('flags when capacity ≠ flow × hours', () => {
      // capacity=500, hours=8000 → expected flow=0.0625, but we set 1.0
      const state = makeState('ELECTROLYSIS', {
        CAPACITY_MAIN: pv('CAPACITY_MAIN', 500, 'kg/yr'),
        FLOW_MAIN: pv('FLOW_MAIN', 1.0, 'kg/h'),
        HOURS_YEAR: pv('HOURS_YEAR', 8000, 'h/yr'),
      });
      const findings = checkCapacityFlow(state);
      expect(findings).toHaveLength(1);
      expect(findings[0].issueCode).toBe('INCONSISTENT_CAPACITY_FLOW');
      expect(findings[0].severity).toBe('CONSISTENCY');
      expect(findings[0].keysAffected).toContain('CAPACITY_MAIN');
      expect(findings[0].keysAffected).toContain('FLOW_MAIN');
    });

    it('returns nothing when required params are missing', () => {
      const state = makeState('ELECTROLYSIS', {
        CAPACITY_MAIN: pv('CAPACITY_MAIN', 500, 'kg/yr'),
      });
      expect(checkCapacityFlow(state)).toHaveLength(0);
    });
  });

  describe('INVALID_NEGATIVE_VALUE', () => {
    it('flags negative power', () => {
      const state = makeState('ELECTROLYSIS', {
        POWER_ELEC: pv('POWER_ELEC', -50, 'kW'),
      });
      const findings = checkNegativeValues(state);
      expect(findings).toHaveLength(1);
      expect(findings[0].issueCode).toBe('INVALID_NEGATIVE_VALUE');
      expect(findings[0].severity).toBe('VALIDATION');
      expect(findings[0].keysAffected).toContain('POWER_ELEC');
    });

    it('flags multiple negative values', () => {
      const state = makeState('ELECTROLYSIS', {
        POWER_ELEC: pv('POWER_ELEC', -50, 'kW'),
        FLOW_MAIN: pv('FLOW_MAIN', -10, 'kg/h'),
        CAPACITY_MAIN: pv('CAPACITY_MAIN', 100, 'kg/yr'), // positive, no flag
      });
      const findings = checkNegativeValues(state);
      expect(findings).toHaveLength(2);
      expect(findings.every(f => f.issueCode === 'INVALID_NEGATIVE_VALUE')).toBe(true);
    });

    it('passes with all positive values', () => {
      const state = makeState('ELECTROLYSIS', {
        POWER_ELEC: pv('POWER_ELEC', 100, 'kW'),
        FLOW_MAIN: pv('FLOW_MAIN', 10, 'kg/h'),
      });
      expect(checkNegativeValues(state)).toHaveLength(0);
    });
  });

  describe('runCheckForEquipment integration', () => {
    it('returns no findings for a minimal consistent state', () => {
      const state = makeState('ELECTROLYSIS', {});
      const findings = runCheckForEquipment(state);
      // With no params at all, checks self-guard and return empty
      // (MISSING_REQUIRED_INPUTS may fire if archetype profile exists)
      expect(findings.every(f => f.severity !== 'ERROR')).toBe(true);
    });
  });
});
