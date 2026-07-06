import { describe, it, expect, beforeEach } from 'vitest';
import { EquationEngine } from '../EquationEngine';

describe('EquationEngine, Electrolysis Unit', () => {
  let engine: EquationEngine;

  beforeEach(() => {
    engine = new EquationEngine();
    engine.setPlantParameter('HOURS_YEAR', 8000, 'h/year');
  });

  it('derives FLOW_H2 from CAPACITY_H2 and HOURS_YEAR', () => {
    const state = engine.setEquipmentInstance('elx-1', 'ELECTROLYSIS_UNIT', null, {
      CAPACITY_H2: { value: 16_000_000, unit: 'kg/year' },
    });

    const flowH2 = state.parameters.get('FLOW_H2');
    expect(flowH2).toBeDefined();
    // 16 000 000 / 8000 = 2000 kg/h
    expect(flowH2!.canonicalValue).toBeCloseTo(2000, 1);
    expect(flowH2!.source).toBe('DERIVED');
  });

  it('derives POWER_ELEC from FLOW_H2 and default SEC_ELEC_H2', () => {
    const state = engine.setEquipmentInstance('elx-1', 'ELECTROLYSIS_UNIT', null, {
      CAPACITY_H2: { value: 16_000_000, unit: 'kg/year' },
    });

    const power = state.parameters.get('POWER_ELEC');
    expect(power).toBeDefined();
    // Default SEC_ELEC_H2 = 52 kWh/kg, P_BASE = 150 kW, FLOW_H2 = 2000
    // POWER_ELEC = 150 + 2000 × 52 = 104 150 kW
    expect(power!.canonicalValue).toBeCloseTo(104_150, 0);
    expect(power!.source).toBe('DERIVED');
  });

  it('derives E_YEAR_ELEC from POWER_ELEC and HOURS_YEAR', () => {
    const state = engine.setEquipmentInstance('elx-1', 'ELECTROLYSIS_UNIT', null, {
      CAPACITY_H2: { value: 16_000_000, unit: 'kg/year' },
    });

    const eYear = state.parameters.get('E_YEAR_ELEC');
    expect(eYear).toBeDefined();
    // 104 150 × 8000 = 833 200 000 kWh/year
    expect(eYear!.canonicalValue).toBeCloseTo(833_200_000, -3);
  });

  it('derives stoichiometric water and oxygen flows', () => {
    const state = engine.setEquipmentInstance('elx-1', 'ELECTROLYSIS_UNIT', null, {
      CAPACITY_H2: { value: 16_000_000, unit: 'kg/year' },
    });

    const flowH2O = state.parameters.get('FLOW_H2O');
    const flowO2 = state.parameters.get('FLOW_O2');
    // FLOW_H2 = 2000, WATER_FACTOR default = 1.05
    // H2O = 9 × 2000 × 1.05 = 18 900 kg/h
    expect(flowH2O?.canonicalValue).toBeCloseTo(18_900, 0);
    // O2 = 8 × 2000 = 16 000 kg/h
    expect(flowO2?.canonicalValue).toBeCloseTo(16_000, 0);
  });

  it('recalculates POWER_ELEC when SEC_ELEC_H2 is updated', () => {
    engine.setEquipmentInstance('elx-1', 'ELECTROLYSIS_UNIT', null, {
      CAPACITY_H2: { value: 16_000_000, unit: 'kg/year' },
    });

    const updated = engine.updateParameter('elx-1', 'SEC_ELEC_H2', 55, 'kWh/kg');
    expect(updated).not.toBeNull();

    const power = updated!.parameters.get('POWER_ELEC');
    // POWER_ELEC = 150 + 2000 × 55 = 110 150 kW
    expect(power!.canonicalValue).toBeCloseTo(110_150, 0);
  });

  it('recalculates downstream E_YEAR_ELEC after SEC_ELEC_H2 update', () => {
    engine.setEquipmentInstance('elx-1', 'ELECTROLYSIS_UNIT', null, {
      CAPACITY_H2: { value: 16_000_000, unit: 'kg/year' },
    });

    const updated = engine.updateParameter('elx-1', 'SEC_ELEC_H2', 55, 'kWh/kg');
    const eYear = updated!.parameters.get('E_YEAR_ELEC');
    // 110 150 × 8000 = 881 200 000
    expect(eYear!.canonicalValue).toBeCloseTo(881_200_000, -3);
  });

  it('allows user override of a derived field', () => {
    engine.setEquipmentInstance('elx-1', 'ELECTROLYSIS_UNIT', null, {
      CAPACITY_H2: { value: 16_000_000, unit: 'kg/year' },
    });

    const updated = engine.updateParameter('elx-1', 'POWER_ELEC', 100_000, 'kW');
    const power = updated!.parameters.get('POWER_ELEC');
    expect(power!.canonicalValue).toBeCloseTo(100_000, 0);
    // Source should be OVERRIDE (user overriding a normally-derived field)
    expect(['USER', 'OVERRIDE']).toContain(power!.source);
  });

  it('re-resolves all equipment when plant parameter changes', () => {
    engine.setEquipmentInstance('elx-1', 'ELECTROLYSIS_UNIT', null, {
      CAPACITY_H2: { value: 16_000_000, unit: 'kg/year' },
    });

    engine.setPlantParameter('HOURS_YEAR', 7500, 'h/year');

    const state = engine.getEquipmentState('elx-1');
    const flowH2 = state!.parameters.get('FLOW_H2');
    // 16 000 000 / 7500 ≈ 2133.33
    expect(flowH2!.canonicalValue).toBeCloseTo(2133.33, 0);
  });

  it('returns null for updateParameter on unknown instance', () => {
    const result = engine.updateParameter('nonexistent', 'FLOW_H2', 100, 'kg/h');
    expect(result).toBeNull();
  });

  it('notifies subscribers on state change', () => {
    let callCount = 0;
    engine.subscribe(() => { callCount++; });

    engine.setEquipmentInstance('elx-1', 'ELECTROLYSIS_UNIT', null, {
      CAPACITY_H2: { value: 16_000_000, unit: 'kg/year' },
    });

    expect(callCount).toBeGreaterThanOrEqual(1);
  });
});
