/**
 * Formula implementations — pure functions for every implRef and formulaId.
 * No side effects, no state.
 */
import type { FormulaDef } from '../types';

type FormulaFn = (inputs: Record<string, number>) => number;

/* ── Generic model implementations (keyed by implRef) ── */

const IMPL_BY_REF: Record<string, FormulaFn> = {
  // Capacity ↔ flow (generic: works with any capacity/flow param name)
  capacityToFlow: (i) => {
    const keys = Object.keys(i);
    const cap = i[keys.find(k => k !== 'HOURS_YEAR')!];
    return cap / i.HOURS_YEAR;
  },
  flowToCapacity: (i) => {
    const keys = Object.keys(i);
    const flow = i[keys.find(k => k !== 'HOURS_YEAR')!];
    return flow * i.HOURS_YEAR;
  },

  // Power from throughput
  flowSecToPower: (i) => (i.P_BASE ?? 0) + (i.FLOW_MAIN ?? i.FLOW_H2 ?? 0) * (i.SEC_ELEC ?? i.SEC_ELEC_H2 ?? 0),

  // Annual energy
  powerToAnnualEnergy: ({ POWER_ELEC, HOURS_YEAR }) => POWER_ELEC * HOURS_YEAR,
  annualEnergyToPower: ({ E_YEAR_ELEC, HOURS_YEAR }) => E_YEAR_ELEC / HOURS_YEAR,

  // Thermal duty
  flowSecToHeatDuty: ({ FLOW_MAIN, SEC_TH, P_TH_BASE }) => (P_TH_BASE ?? 0) + FLOW_MAIN * SEC_TH,

  // Cooling
  coolingDutyToPower: ({ COOLING_DUTY, COP_COOL, P_BASE }) => (P_BASE ?? 0) + COOLING_DUTY / COP_COOL,
  powerToCoolingDuty: ({ POWER_ELEC, COP_COOL, P_BASE }) => (POWER_ELEC - (P_BASE ?? 0)) * COP_COOL,

  // Fuel
  fuelDutyToFlow: ({ FUEL_DUTY, EFF_TH, LHV_FUEL }) => FUEL_DUTY / (EFF_TH * LHV_FUEL),
  fuelFlowToDuty: ({ FLOW_FUEL, EFF_TH, LHV_FUEL }) => FLOW_FUEL * EFF_TH * LHV_FUEL,

  // Steam
  steamDutyToFlow: ({ STEAM_DUTY, DELTAH_STEAM }) => STEAM_DUTY / DELTAH_STEAM,
  steamFlowToDuty: ({ FLOW_STEAM, DELTAH_STEAM }) => FLOW_STEAM * DELTAH_STEAM,

  // Split / recovery
  splitRecoveryOut: ({ FLOW_IN, RECOVERY }) => FLOW_IN * RECOVERY,
  splitRecoveryWaste: ({ FLOW_IN, RECOVERY }) => FLOW_IN * (1 - RECOVERY),

  // Removal
  removalEffRemoved: ({ FLOW_IN, REMOVAL_EFF }) => FLOW_IN * REMOVAL_EFF,
  removalEffOut: ({ FLOW_IN, REMOVAL_EFF }) => FLOW_IN * (1 - REMOVAL_EFF),

  // Pump
  pumpHydraulicPower: ({ FLOW_VOL, DELTA_P, ETA_PUMP, P_BASE }) => (P_BASE ?? 0) + (DELTA_P * FLOW_VOL) / ETA_PUMP,

  // Splitter
  splitterTop: ({ FLOW_IN, SPLIT_FRAC }) => FLOW_IN * SPLIT_FRAC,
  splitterBottom: ({ FLOW_IN, SPLIT_FRAC }) => FLOW_IN * (1 - SPLIT_FRAC),

  // Mass balance
  massBalanceResidual: ({ SUM_MASS_IN, SUM_MASS_OUT }) => SUM_MASS_IN - SUM_MASS_OUT,

  // Electrolysis stoichiometry
  electrolysisStoichWater: ({ FLOW_H2, WATER_FACTOR }) => 9 * FLOW_H2 * WATER_FACTOR,
  electrolysisStoichOxygen: ({ FLOW_H2 }) => 8 * FLOW_H2,

  // Fixed power
  fixedPower: ({ P_FIXED }) => P_FIXED,

  // BESS
  bessEnergy: ({ P_RATED, DURATION_H }) => P_RATED * DURATION_H,
  bessPower: ({ E_STORAGE, DURATION_H }) => E_STORAGE / DURATION_H,

  // Generator
  generatorPower: ({ FLOW_FUEL, EFF_ELEC, LHV_FUEL, P_BASE }) => (P_BASE ?? 0) + FLOW_FUEL * LHV_FUEL * EFF_ELEC,
  generatorFuel: ({ POWER_ELEC, EFF_ELEC, LHV_FUEL, P_BASE }) => (POWER_ELEC - (P_BASE ?? 0)) / (EFF_ELEC * LHV_FUEL),

  // Generic conversion: output = input × conversion_factor
  conversionCalc: (inputs) => {
    const keys = Object.keys(inputs);
    return keys.reduce((acc, k) => acc * inputs[k], 1);
  },
};

/* ── Stoichiometric formulas dispatched by formulaId ── */

const IMPL_BY_FORMULA_ID: Record<string, FormulaFn> = {
  // ── Methanation ──
  F_METHANATION_CO_CONV_V1:  (i) => i.F_CO_IN_KMOL_H * i.X_CO,
  F_METHANATION_CO2_CONV_V1: (i) => i.F_CO2_IN_KMOL_H * i.X_CO2,
  F_METHANATION_CH4_PROD_V1: (i) => i.F_CH4_IN_KMOL_H + i.F_CO_CONV_KMOL_H + i.F_CO2_CONV_KMOL_H,
  F_METHANATION_H2O_PROD_V1: (i) => i.F_H2O_IN_KMOL_H + i.F_CO_CONV_KMOL_H + 2 * i.F_CO2_CONV_KMOL_H,
  F_METHANATION_H2_CONS_V1:  (i) => i.F_H2_IN_KMOL_H - 3 * i.F_CO_CONV_KMOL_H - 4 * i.F_CO2_CONV_KMOL_H,

  // ── Methanol Synthesis ──
  F_MEOH_CO_CONV_V1:  (i) => i.F_CO_IN_KMOL_H * i.X_CO,
  F_MEOH_CO2_CONV_V1: (i) => i.F_CO2_IN_KMOL_H * i.X_CO2,
  F_MEOH_PROD_V1:     (i) => i.F_MEOH_IN_KMOL_H + i.F_CO_CONV_KMOL_H + i.F_CO2_CONV_KMOL_H,
  F_MEOH_H2O_PROD_V1: (i) => i.F_H2O_IN_KMOL_H + i.F_CO2_CONV_KMOL_H,
  F_MEOH_H2_CONS_V1:  (i) => i.F_H2_IN_KMOL_H - 2 * i.F_CO_CONV_KMOL_H - 3 * i.F_CO2_CONV_KMOL_H,

  // ── DME ──
  F_DME_MEOH_CONV_V1: (i) => i.F_MEOH_IN_KMOL_H * i.X_MEOH,
  F_DME_PROD_V1:      (i) => i.F_DME_IN_KMOL_H + 0.5 * i.F_MEOH_CONV_KMOL_H,
  F_DME_H2O_PROD_V1:  (i) => i.F_H2O_IN_KMOL_H + 0.5 * i.F_MEOH_CONV_KMOL_H,
  F_DME_MEOH_OUT_V1:   (i) => i.F_MEOH_IN_KMOL_H - i.F_MEOH_CONV_KMOL_H,

  // ── Ammonia ──
  F_NH3_N2_CONV_V1: (i) => i.F_N2_IN_KMOL_H * i.X_N2,
  F_NH3_PROD_V1:    (i) => i.F_NH3_IN_KMOL_H + 2 * i.F_N2_CONV_KMOL_H,
  F_NH3_H2_OUT_V1:  (i) => i.F_H2_IN_KMOL_H - 3 * i.F_N2_CONV_KMOL_H,

  // ── Haber-Bosch Loop ──
  F_HB_LOOP_PURGE_V1:       (i) => i.F_RECYCLE_KMOL_H * i.PURGE_FRAC,
  F_HB_LOOP_RECYCLE_OUT_V1: (i) => i.F_RECYCLE_KMOL_H - i.F_PURGE_KMOL_H,

  // ── Fischer-Tropsch ──
  F_FT_CO_CONV_V1:       (i) => i.F_CO_IN_KMOL_H * i.X_CO,
  F_FT_H2_OUT_V1:        (i) => i.F_H2_IN_KMOL_H - i.R_H2_CO * i.F_CO_CONV_KMOL_H,
  F_FT_H2O_PROD_V1:      (i) => i.F_H2O_IN_KMOL_H + i.F_CO_CONV_KMOL_H,
  F_FT_LIQ_PROD_MASS_V1: (i) => i.F_CO_CONV_KMOL_H * i.Y_LIQ_KG_PER_KMOLCO,
  F_FT_OFFGAS_CO_OUT_V1:  (i) => i.F_CO_IN_KMOL_H - i.F_CO_CONV_KMOL_H,
  F_FT_CO2_BYPROD_V1:     (i) => i.F_CO2_IN_KMOL_H + i.F_CO_CONV_KMOL_H * i.Y_CO2_PER_CO,
  F_FT_CH4_BYPROD_V1:     (i) => i.F_CH4_IN_KMOL_H + i.F_CO_CONV_KMOL_H * i.Y_CH4_PER_CO,

  // ── Polymerization ──
  F_POLY_MONOMER_CONV_V1:   (i) => i.F_MONOMER_IN_KMOL_H * i.X_MONOMER,
  F_POLY_PRODUCT_MASS_V1:   (i) => i.F_MONOMER_CONV_KMOL_H * i.MW_MONOMER * i.YIELD_MASS,
  F_POLY_MONOMER_OUT_V1:    (i) => i.F_MONOMER_IN_KMOL_H - i.F_MONOMER_CONV_KMOL_H,
};

/**
 * Execute a single formula given its definition and input values.
 * Returns null if any required input is missing.
 */
export function executeFormula(
  formula: FormulaDef,
  inputValues: Record<string, number | null>,
): number | null {
  // Build the input record, checking for missing values
  const inputs: Record<string, number> = {};
  for (const key of formula.inputParamKeys) {
    const val = inputValues[key];
    if (val == null || !isFinite(val)) return null;
    inputs[key] = val;
  }

  // Try formulaId-specific implementation first (for stoichiometric)
  const byId = IMPL_BY_FORMULA_ID[formula.formulaId];
  if (byId) return byId(inputs);

  // Fall back to implRef-based dispatch
  const byRef = IMPL_BY_REF[formula.implRef];
  if (byRef) return byRef(inputs);

  // Unknown implementation
  return null;
}
