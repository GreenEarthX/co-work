/**
 * Consistency & validation checks for all 25 issue codes.
 * Pure functions — never throw, always return findings.
 */
import type { EquipmentEngineState, RuleFinding, Severity } from '../types';

const TOLERANCE = 0.001; // 0.1% relative

function isConsistent(expected: number, actual: number, tolerance = TOLERANCE): boolean {
  if (expected === 0 && actual === 0) return true;
  if (expected === 0) return Math.abs(actual) < tolerance;
  return Math.abs((expected - actual) / expected) < tolerance;
}

function cv(state: EquipmentEngineState, key: string): number | null {
  return state.parameters.get(key)?.canonicalValue ?? null;
}

function has(state: EquipmentEngineState, ...keys: string[]): boolean {
  return keys.every(k => cv(state, k) != null);
}

function finding(
  issueCode: string, severity: Severity, message: string,
  keysAffected: string[], evidence: Record<string, unknown>,
  equipmentInstanceId: string,
): RuleFinding {
  return { issueCode, severity, message, keysAffected, evidenceJson: evidence, equipmentInstanceId };
}

function fmt(n: number): string { return Number(n.toPrecision(6)).toString(); }
function pct(expected: number, actual: number): string {
  if (expected === 0) return 'N/A';
  return fmt(((actual - expected) / expected) * 100);
}

// ─── Consistency checks ───

export function checkCapacityFlow(s: EquipmentEngineState): RuleFinding[] {
  if (!has(s, 'CAPACITY_MAIN', 'HOURS_YEAR', 'FLOW_MAIN')) return [];
  const cap = cv(s, 'CAPACITY_MAIN')!, hrs = cv(s, 'HOURS_YEAR')!, flow = cv(s, 'FLOW_MAIN')!;
  if (hrs === 0) return [];
  const expected = cap / hrs;
  if (isConsistent(expected, flow)) return [];
  const delta = flow - expected;
  return [finding('INCONSISTENT_CAPACITY_FLOW', 'CONSISTENCY',
    `Capacity (${fmt(cap)}) ≠ Flow (${fmt(flow)}) × Hours (${fmt(hrs)}). Δ = ${fmt(delta)} (${pct(expected, flow)}%).`,
    ['CAPACITY_MAIN', 'HOURS_YEAR', 'FLOW_MAIN'], { expected, actual: flow, delta }, s.equipmentInstanceId)];
}

export function checkPowerFromSec(s: EquipmentEngineState): RuleFinding[] {
  if (!has(s, 'FLOW_MAIN', 'SEC_ELEC', 'P_BASE', 'POWER_ELEC')) return [];
  const flow = cv(s, 'FLOW_MAIN')!, sec = cv(s, 'SEC_ELEC')!, pb = cv(s, 'P_BASE')!, p = cv(s, 'POWER_ELEC')!;
  const expected = pb + flow * sec;
  if (isConsistent(expected, p)) return [];
  return [finding('INCONSISTENT_POWER_FROM_SEC', 'CONSISTENCY',
    `Power (${fmt(p)} kW) ≠ P_base (${fmt(pb)}) + Flow (${fmt(flow)}) × SEC (${fmt(sec)}). Δ = ${fmt(p - expected)} kW.`,
    ['FLOW_MAIN', 'SEC_ELEC', 'P_BASE', 'POWER_ELEC'], { expected, actual: p }, s.equipmentInstanceId)];
}

export function checkAnnualEnergy(s: EquipmentEngineState): RuleFinding[] {
  if (!has(s, 'POWER_ELEC', 'HOURS_YEAR', 'E_YEAR_ELEC')) return [];
  const p = cv(s, 'POWER_ELEC')!, hrs = cv(s, 'HOURS_YEAR')!, e = cv(s, 'E_YEAR_ELEC')!;
  const expected = p * hrs;
  if (isConsistent(expected, e)) return [];
  return [finding('INCONSISTENT_ANNUAL_ENERGY', 'CONSISTENCY',
    `Annual energy (${fmt(e)} kWh/yr) ≠ Power (${fmt(p)} kW) × Hours (${fmt(hrs)}). Δ = ${fmt(e - expected)} kWh/yr.`,
    ['POWER_ELEC', 'HOURS_YEAR', 'E_YEAR_ELEC'], { expected, actual: e }, s.equipmentInstanceId)];
}

export function checkThermalDuty(s: EquipmentEngineState): RuleFinding[] {
  if (!has(s, 'FLOW_MAIN', 'SEC_TH', 'P_TH_BASE', 'DUTY_TH')) return [];
  const flow = cv(s, 'FLOW_MAIN')!, sec = cv(s, 'SEC_TH')!, pb = cv(s, 'P_TH_BASE')!, q = cv(s, 'DUTY_TH')!;
  const expected = pb + flow * sec;
  if (isConsistent(expected, q)) return [];
  return [finding('INCONSISTENT_THERMAL_DUTY', 'CONSISTENCY',
    `Thermal duty (${fmt(q)} kW) ≠ Q_base (${fmt(pb)}) + Flow × SEC_th. Δ = ${fmt(q - expected)} kW.`,
    ['FLOW_MAIN', 'SEC_TH', 'P_TH_BASE', 'DUTY_TH'], { expected, actual: q }, s.equipmentInstanceId)];
}

export function checkCoolingPower(s: EquipmentEngineState): RuleFinding[] {
  if (!has(s, 'COOLING_DUTY', 'COP_COOL', 'P_BASE', 'POWER_ELEC')) return [];
  const qc = cv(s, 'COOLING_DUTY')!, cop = cv(s, 'COP_COOL')!, pb = cv(s, 'P_BASE')!, p = cv(s, 'POWER_ELEC')!;
  if (cop === 0) return [];
  const expected = pb + qc / cop;
  if (isConsistent(expected, p)) return [];
  return [finding('INCONSISTENT_COOLING_POWER', 'CONSISTENCY',
    `Cooling power (${fmt(p)} kW) ≠ P_base + Q_cool / COP. Expected ${fmt(expected)} kW. Δ = ${fmt(p - expected)} kW.`,
    ['COOLING_DUTY', 'COP_COOL', 'P_BASE', 'POWER_ELEC'], { expected, actual: p }, s.equipmentInstanceId)];
}

export function checkFuelDuty(s: EquipmentEngineState): RuleFinding[] {
  if (!has(s, 'FUEL_DUTY', 'EFF_TH', 'LHV_FUEL', 'FLOW_FUEL')) return [];
  const q = cv(s, 'FUEL_DUTY')!, eff = cv(s, 'EFF_TH')!, lhv = cv(s, 'LHV_FUEL')!, mf = cv(s, 'FLOW_FUEL')!;
  if (eff * lhv === 0) return [];
  const expected = q / (eff * lhv);
  if (isConsistent(expected, mf)) return [];
  return [finding('INCONSISTENT_FUEL_DUTY', 'CONSISTENCY',
    `Fuel flow (${fmt(mf)} kg/h) ≠ Q / (η × LHV). Expected ${fmt(expected)} kg/h. Δ = ${fmt(mf - expected)} kg/h.`,
    ['FUEL_DUTY', 'EFF_TH', 'LHV_FUEL', 'FLOW_FUEL'], { expected, actual: mf }, s.equipmentInstanceId)];
}

export function checkSteamFlow(s: EquipmentEngineState): RuleFinding[] {
  if (!has(s, 'STEAM_DUTY', 'DELTAH_STEAM', 'FLOW_STEAM')) return [];
  const q = cv(s, 'STEAM_DUTY')!, dh = cv(s, 'DELTAH_STEAM')!, ms = cv(s, 'FLOW_STEAM')!;
  if (dh === 0) return [];
  const expected = q / dh;
  if (isConsistent(expected, ms)) return [];
  return [finding('INCONSISTENT_STEAM_FLOW', 'CONSISTENCY',
    `Steam flow (${fmt(ms)} kg/h) ≠ Q / Δh. Expected ${fmt(expected)} kg/h. Δ = ${fmt(ms - expected)} kg/h.`,
    ['STEAM_DUTY', 'DELTAH_STEAM', 'FLOW_STEAM'], { expected, actual: ms }, s.equipmentInstanceId)];
}

export function checkSplit(s: EquipmentEngineState): RuleFinding[] {
  if (!has(s, 'FLOW_IN', 'RECOVERY', 'FLOW_OUT', 'FLOW_WASTE')) return [];
  const fi = cv(s, 'FLOW_IN')!, r = cv(s, 'RECOVERY')!, fo = cv(s, 'FLOW_OUT')!, fw = cv(s, 'FLOW_WASTE')!;
  const expOut = fi * r, expWaste = fi * (1 - r);
  const ok = isConsistent(expOut, fo) && isConsistent(expWaste, fw);
  if (ok) return [];
  return [finding('INCONSISTENT_SPLIT', 'CONSISTENCY',
    `Split balance: In (${fmt(fi)}) ≠ Out (${fmt(fo)}) + Waste (${fmt(fw)}). Δ = ${fmt(fi - fo - fw)} kg/h.`,
    ['FLOW_IN', 'RECOVERY', 'FLOW_OUT', 'FLOW_WASTE'], { expOut, expWaste, actualOut: fo, actualWaste: fw }, s.equipmentInstanceId)];
}

export function checkRemoval(s: EquipmentEngineState): RuleFinding[] {
  if (!has(s, 'FLOW_IN', 'REMOVAL_EFF', 'FLOW_OUT', 'FLOW_REMOVED')) return [];
  const fi = cv(s, 'FLOW_IN')!, eff = cv(s, 'REMOVAL_EFF')!, fo = cv(s, 'FLOW_OUT')!, fr = cv(s, 'FLOW_REMOVED')!;
  const expOut = fi * (1 - eff), expRem = fi * eff;
  if (isConsistent(expOut, fo) && isConsistent(expRem, fr)) return [];
  return [finding('INCONSISTENT_REMOVAL', 'CONSISTENCY',
    `Removal balance: In (${fmt(fi)}) ≠ Out (${fmt(fo)}) + Removed (${fmt(fr)}). Δ = ${fmt(fi - fo - fr)} kg/h.`,
    ['FLOW_IN', 'REMOVAL_EFF', 'FLOW_OUT', 'FLOW_REMOVED'], { expOut, expRem, actualOut: fo, actualRemoved: fr }, s.equipmentInstanceId)];
}

export function checkBess(s: EquipmentEngineState): RuleFinding[] {
  if (!has(s, 'P_RATED', 'DURATION_H', 'E_STORAGE')) return [];
  const p = cv(s, 'P_RATED')!, d = cv(s, 'DURATION_H')!, e = cv(s, 'E_STORAGE')!;
  const expected = p * d;
  if (isConsistent(expected, e)) return [];
  return [finding('INCONSISTENT_BESS', 'CONSISTENCY',
    `BESS energy (${fmt(e)} kWh) ≠ P_rated (${fmt(p)} kW) × Duration (${fmt(d)} h). Δ = ${fmt(e - expected)} kWh.`,
    ['P_RATED', 'DURATION_H', 'E_STORAGE'], { expected, actual: e }, s.equipmentInstanceId)];
}

export function checkGenerator(s: EquipmentEngineState): RuleFinding[] {
  if (!has(s, 'FLOW_FUEL', 'EFF_ELEC', 'LHV_FUEL', 'POWER_ELEC')) return [];
  const mf = cv(s, 'FLOW_FUEL')!, eff = cv(s, 'EFF_ELEC')!, lhv = cv(s, 'LHV_FUEL')!, p = cv(s, 'POWER_ELEC')!;
  const pb = cv(s, 'P_BASE') ?? 0;
  const expected = pb + mf * lhv * eff;
  if (isConsistent(expected, p)) return [];
  return [finding('INCONSISTENT_GENERATOR', 'CONSISTENCY',
    `Generator power (${fmt(p)} kW) ≠ P_base + m_fuel × η × LHV. Expected ${fmt(expected)} kW. Δ = ${fmt(p - expected)} kW.`,
    ['FLOW_FUEL', 'EFF_ELEC', 'LHV_FUEL', 'POWER_ELEC'], { expected, actual: p }, s.equipmentInstanceId)];
}

export function checkStoichElectrolysis(s: EquipmentEngineState): RuleFinding[] {
  if (!has(s, 'FLOW_H2', 'FLOW_H2O', 'FLOW_O2')) return [];
  const h2 = cv(s, 'FLOW_H2')!, h2o = cv(s, 'FLOW_H2O')!, o2 = cv(s, 'FLOW_O2')!;
  const wf = cv(s, 'WATER_FACTOR') ?? 1;
  const findings: RuleFinding[] = [];
  if (!isConsistent(9 * h2 * wf, h2o) || !isConsistent(8 * h2, o2)) {
    findings.push(finding('INCONSISTENT_STOICH_ELECTROLYSIS', 'CONSISTENCY',
      `Electrolysis stoichiometry violated: H₂O (${fmt(h2o)}) vs expected ${fmt(9 * h2 * wf)}; O₂ (${fmt(o2)}) vs expected ${fmt(8 * h2)}.`,
      ['FLOW_H2', 'FLOW_H2O', 'FLOW_O2'], { expH2O: 9 * h2 * wf, actH2O: h2o, expO2: 8 * h2, actO2: o2 }, s.equipmentInstanceId));
  }
  return findings;
}

// Generic stoich helper: check pairs of (expected, actual)
function stoichCheck(
  s: EquipmentEngineState, issueCode: string, msg: string, keys: string[],
  pairs: [number, number][],
): RuleFinding[] {
  if (pairs.every(([exp, act]) => isConsistent(exp, act))) return [];
  const evidence: Record<string, unknown> = {};
  pairs.forEach(([exp, act], i) => { evidence[`pair${i}_exp`] = exp; evidence[`pair${i}_act`] = act; });
  return [finding(issueCode, 'CONSISTENCY', msg, keys, evidence, s.equipmentInstanceId)];
}

export function checkStoichMethanation(s: EquipmentEngineState): RuleFinding[] {
  const keys = ['F_CO_IN_KMOL_H', 'X_CO', 'F_CO2_IN_KMOL_H', 'X_CO2', 'F_CH4_IN_KMOL_H', 'F_H2O_IN_KMOL_H', 'F_H2_IN_KMOL_H',
    'F_CH4_OUT_KMOL_H', 'F_H2O_OUT_KMOL_H', 'F_H2_OUT_KMOL_H'];
  if (!has(s, ...keys)) return [];
  const coIn = cv(s, 'F_CO_IN_KMOL_H')!, xCo = cv(s, 'X_CO')!, co2In = cv(s, 'F_CO2_IN_KMOL_H')!, xCo2 = cv(s, 'X_CO2')!;
  const ch4In = cv(s, 'F_CH4_IN_KMOL_H')!, h2oIn = cv(s, 'F_H2O_IN_KMOL_H')!, h2In = cv(s, 'F_H2_IN_KMOL_H')!;
  const coConv = coIn * xCo, co2Conv = co2In * xCo2;
  return stoichCheck(s, 'INCONSISTENT_STOICH_METHANATION', 'Methanation molar balance violated.',
    ['F_CH4_OUT_KMOL_H', 'F_H2O_OUT_KMOL_H', 'F_H2_OUT_KMOL_H'], [
      [ch4In + coConv + co2Conv, cv(s, 'F_CH4_OUT_KMOL_H')!],
      [h2oIn + coConv + 2 * co2Conv, cv(s, 'F_H2O_OUT_KMOL_H')!],
      [h2In - 3 * coConv - 4 * co2Conv, cv(s, 'F_H2_OUT_KMOL_H')!],
    ]);
}

export function checkStoichMethanol(s: EquipmentEngineState): RuleFinding[] {
  const req = ['F_CO_IN_KMOL_H', 'X_CO', 'F_CO2_IN_KMOL_H', 'X_CO2', 'F_MEOH_IN_KMOL_H', 'F_H2O_IN_KMOL_H', 'F_H2_IN_KMOL_H',
    'F_MEOH_OUT_KMOL_H', 'F_H2O_OUT_KMOL_H', 'F_H2_OUT_KMOL_H'];
  if (!has(s, ...req)) return [];
  const coConv = cv(s, 'F_CO_IN_KMOL_H')! * cv(s, 'X_CO')!;
  const co2Conv = cv(s, 'F_CO2_IN_KMOL_H')! * cv(s, 'X_CO2')!;
  return stoichCheck(s, 'INCONSISTENT_STOICH_METHANOL', 'Methanol synthesis molar balance violated.',
    ['F_MEOH_OUT_KMOL_H', 'F_H2O_OUT_KMOL_H', 'F_H2_OUT_KMOL_H'], [
      [cv(s, 'F_MEOH_IN_KMOL_H')! + coConv + co2Conv, cv(s, 'F_MEOH_OUT_KMOL_H')!],
      [cv(s, 'F_H2O_IN_KMOL_H')! + co2Conv, cv(s, 'F_H2O_OUT_KMOL_H')!],
      [cv(s, 'F_H2_IN_KMOL_H')! - 2 * coConv - 3 * co2Conv, cv(s, 'F_H2_OUT_KMOL_H')!],
    ]);
}

export function checkStoichDME(s: EquipmentEngineState): RuleFinding[] {
  const req = ['F_MEOH_IN_KMOL_H', 'X_MEOH', 'F_DME_IN_KMOL_H', 'F_H2O_IN_KMOL_H',
    'F_DME_OUT_KMOL_H', 'F_H2O_OUT_KMOL_H', 'F_MEOH_OUT_KMOL_H'];
  if (!has(s, ...req)) return [];
  const meohConv = cv(s, 'F_MEOH_IN_KMOL_H')! * cv(s, 'X_MEOH')!;
  return stoichCheck(s, 'INCONSISTENT_STOICH_DME', 'DME dehydration molar balance violated.',
    ['F_DME_OUT_KMOL_H', 'F_H2O_OUT_KMOL_H', 'F_MEOH_OUT_KMOL_H'], [
      [cv(s, 'F_DME_IN_KMOL_H')! + 0.5 * meohConv, cv(s, 'F_DME_OUT_KMOL_H')!],
      [cv(s, 'F_H2O_IN_KMOL_H')! + 0.5 * meohConv, cv(s, 'F_H2O_OUT_KMOL_H')!],
      [cv(s, 'F_MEOH_IN_KMOL_H')! - meohConv, cv(s, 'F_MEOH_OUT_KMOL_H')!],
    ]);
}

export function checkStoichAmmonia(s: EquipmentEngineState): RuleFinding[] {
  const req = ['F_N2_IN_KMOL_H', 'X_N2', 'F_H2_IN_KMOL_H', 'F_NH3_IN_KMOL_H',
    'F_NH3_OUT_KMOL_H', 'F_H2_OUT_KMOL_H'];
  if (!has(s, ...req)) return [];
  const n2Conv = cv(s, 'F_N2_IN_KMOL_H')! * cv(s, 'X_N2')!;
  return stoichCheck(s, 'INCONSISTENT_STOICH_AMMONIA', 'Ammonia synthesis molar balance violated.',
    ['F_NH3_OUT_KMOL_H', 'F_H2_OUT_KMOL_H'], [
      [cv(s, 'F_NH3_IN_KMOL_H')! + 2 * n2Conv, cv(s, 'F_NH3_OUT_KMOL_H')!],
      [cv(s, 'F_H2_IN_KMOL_H')! - 3 * n2Conv, cv(s, 'F_H2_OUT_KMOL_H')!],
    ]);
}

export function checkStoichFT(s: EquipmentEngineState): RuleFinding[] {
  const req = ['F_CO_IN_KMOL_H', 'X_CO', 'F_H2_IN_KMOL_H', 'R_H2_CO', 'F_H2O_IN_KMOL_H',
    'Y_LIQ_KG_PER_KMOLCO', 'F_H2_OUT_KMOL_H', 'F_H2O_OUT_KMOL_H', 'F_FT_LIQ_KG_H', 'F_CO_OUT_KMOL_H'];
  if (!has(s, ...req)) return [];
  const coConv = cv(s, 'F_CO_IN_KMOL_H')! * cv(s, 'X_CO')!;
  const pairs: [number, number][] = [
    [cv(s, 'F_H2_IN_KMOL_H')! - cv(s, 'R_H2_CO')! * coConv, cv(s, 'F_H2_OUT_KMOL_H')!],
    [cv(s, 'F_H2O_IN_KMOL_H')! + coConv, cv(s, 'F_H2O_OUT_KMOL_H')!],
    [coConv * cv(s, 'Y_LIQ_KG_PER_KMOLCO')!, cv(s, 'F_FT_LIQ_KG_H')!],
    [cv(s, 'F_CO_IN_KMOL_H')! - coConv, cv(s, 'F_CO_OUT_KMOL_H')!],
  ];
  return stoichCheck(s, 'INCONSISTENT_STOICH_FT', 'Fischer-Tropsch yield balance violated.',
    ['F_H2_OUT_KMOL_H', 'F_H2O_OUT_KMOL_H', 'F_FT_LIQ_KG_H', 'F_CO_OUT_KMOL_H'], pairs);
}

export function checkPolymerization(s: EquipmentEngineState): RuleFinding[] {
  const req = ['F_MONOMER_IN_KMOL_H', 'X_MONOMER', 'MW_MONOMER', 'YIELD_MASS',
    'F_MONOMER_CONV_KMOL_H', 'F_POLYMER_KG_H', 'F_MONOMER_OUT_KMOL_H'];
  if (!has(s, ...req)) return [];
  const monIn = cv(s, 'F_MONOMER_IN_KMOL_H')!, x = cv(s, 'X_MONOMER')!;
  const mw = cv(s, 'MW_MONOMER')!, y = cv(s, 'YIELD_MASS')!;
  const conv = monIn * x;
  return stoichCheck(s, 'INCONSISTENT_POLYMERIZATION', 'Polymerization mass balance violated.',
    ['F_MONOMER_CONV_KMOL_H', 'F_POLYMER_KG_H', 'F_MONOMER_OUT_KMOL_H'], [
      [conv, cv(s, 'F_MONOMER_CONV_KMOL_H')!],
      [conv * mw * y, cv(s, 'F_POLYMER_KG_H')!],
      [monIn - conv, cv(s, 'F_MONOMER_OUT_KMOL_H')!],
    ]);
}

export function checkLoopPurge(s: EquipmentEngineState): RuleFinding[] {
  if (!has(s, 'F_RECYCLE_KMOL_H', 'PURGE_FRAC', 'F_PURGE_KMOL_H', 'F_RECYCLE_OUT_KMOL_H')) return [];
  const rec = cv(s, 'F_RECYCLE_KMOL_H')!, f = cv(s, 'PURGE_FRAC')!;
  const purge = cv(s, 'F_PURGE_KMOL_H')!, recOut = cv(s, 'F_RECYCLE_OUT_KMOL_H')!;
  return stoichCheck(s, 'INCONSISTENT_LOOP_PURGE',
    `Loop purge balance violated: recycle (${fmt(rec)}) ≠ purge + recycle_out. Δ = ${fmt(rec - purge - recOut)} kmol/h.`,
    ['F_RECYCLE_KMOL_H', 'PURGE_FRAC', 'F_PURGE_KMOL_H', 'F_RECYCLE_OUT_KMOL_H'], [
      [rec * f, purge],
      [rec - rec * f, recOut],
    ]);
}

// ─── Validation checks ───

const NON_NEGATIVE_KEYS = [
  'FLOW_MAIN', 'FLOW_H2', 'FLOW_H2O', 'FLOW_O2', 'FLOW_FUEL', 'FLOW_STEAM',
  'FLOW_IN', 'FLOW_OUT', 'FLOW_WASTE', 'FLOW_REMOVED',
  'POWER_ELEC', 'DUTY_TH', 'COOLING_DUTY', 'FUEL_DUTY', 'STEAM_DUTY',
  'E_YEAR_ELEC', 'E_STORAGE', 'P_RATED', 'CAPACITY_MAIN', 'CAPACITY_H2',
];

export function checkNegativeValues(s: EquipmentEngineState): RuleFinding[] {
  const findings: RuleFinding[] = [];
  for (const key of NON_NEGATIVE_KEYS) {
    const v = cv(s, key);
    if (v != null && v < 0) {
      const unit = s.parameters.get(key)?.unit ?? '';
      findings.push(finding('INVALID_NEGATIVE_VALUE', 'VALIDATION',
        `Parameter ${key} has negative value (${fmt(v)} ${unit}) which is physically invalid.`,
        [key], { paramKey: key, value: v }, s.equipmentInstanceId));
    }
  }
  return findings;
}

export function checkEfficiencyRange(s: EquipmentEngineState): RuleFinding[] {
  const findings: RuleFinding[] = [];
  for (const key of ['EFF_TH', 'EFF_ELEC']) {
    const v = cv(s, key);
    if (v != null && (v < 0 || v > 1)) {
      findings.push(finding('INVALID_EFFICIENCY_RANGE', 'VALIDATION',
        `Efficiency ${key} = ${fmt(v)} is outside valid range [0, 1].`,
        [key], { paramKey: key, value: v }, s.equipmentInstanceId));
    }
  }
  return findings;
}

export function checkCopRange(s: EquipmentEngineState): RuleFinding[] {
  const v = cv(s, 'COP_COOL');
  if (v == null) return [];
  if (v <= 0 || v > 10) {
    return [finding('INVALID_COP_RANGE', 'VALIDATION',
      `COP (${fmt(v)}) is outside expected range [1, 10].`,
      ['COP_COOL'], { value: v }, s.equipmentInstanceId)];
  }
  return [];
}

export function checkMissingInputs(s: EquipmentEngineState, requiredKeys: string[]): RuleFinding[] {
  const missing = requiredKeys.filter(k => cv(s, k) == null);
  if (missing.length === 0) return [];
  return [finding('MISSING_REQUIRED_INPUTS', 'VALIDATION',
    `Equipment ${s.equipmentInstanceId} (${s.archetypeId}) is missing required input(s): ${missing.join(', ')}.`,
    missing, { missingKeys: missing, equipmentId: s.equipmentInstanceId, archetypeId: s.archetypeId }, s.equipmentInstanceId)];
}

export function checkOverdetermined(s: EquipmentEngineState, derivedOutputKeys: string[]): RuleFinding[] {
  const conflicts: string[] = [];
  for (const key of derivedOutputKeys) {
    const pv = s.parameters.get(key);
    if (pv && pv.source === 'USER' && pv.isOverridden) {
      conflicts.push(key);
    }
  }
  if (conflicts.length === 0) return [];
  return [finding('OVERDETERMINED_CONFLICT', 'CONSISTENCY',
    `Equipment ${s.equipmentInstanceId} has conflicting user-entered values for ${conflicts.join(', ')}.`,
    conflicts, { conflictingKeys: conflicts, equipmentId: s.equipmentInstanceId }, s.equipmentInstanceId)];
}

/** All consistency check functions */
export const ALL_CONSISTENCY_CHECKS = [
  checkCapacityFlow, checkPowerFromSec, checkAnnualEnergy, checkThermalDuty,
  checkCoolingPower, checkFuelDuty, checkSteamFlow, checkSplit, checkRemoval,
  checkBess, checkGenerator, checkStoichElectrolysis, checkStoichMethanation,
  checkStoichMethanol, checkStoichDME, checkStoichAmmonia, checkStoichFT,
  checkPolymerization, checkLoopPurge,
] as const;

/** All validation check functions (that don't need extra context) */
export const ALL_VALIDATION_CHECKS = [
  checkNegativeValues, checkEfficiencyRange, checkCopRange,
] as const;
