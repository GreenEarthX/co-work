/**
 * Formula definitions registry — all 61 formulas for the equation engine.
 * Pure data, no logic.
 */
import type { FormulaDef } from '../types';

const gf = (
  formulaId: string, appliesToModelId: string, priority: number,
  outputParamKey: string, inputParamKeys: string[],
  expressionLatex: string, implRef: string, notes = ''
): FormulaDef => ({
  formulaId, scopeType: 'GLOBAL', scopeId: '*', priority,
  appliesToModelId, outputParamKey, inputParamKeys,
  expressionLatex, implRef, notes,
});

const af = (
  scopeId: string, formulaId: string, appliesToModelId: string, priority: number,
  outputParamKey: string, inputParamKeys: string[],
  expressionLatex: string, implRef: string, notes = ''
): FormulaDef => ({
  formulaId, scopeType: 'ARCHETYPE', scopeId, priority,
  appliesToModelId, outputParamKey, inputParamKeys,
  expressionLatex, implRef, notes,
});

const ef = (
  scopeId: string, formulaId: string, appliesToModelId: string, priority: number,
  outputParamKey: string, inputParamKeys: string[],
  expressionLatex: string, implRef: string, notes = ''
): FormulaDef => ({
  formulaId, scopeType: 'EQUIPMENT', scopeId, priority,
  appliesToModelId, outputParamKey, inputParamKeys,
  expressionLatex, implRef, notes,
});

export const FORMULAS: readonly FormulaDef[] = [
  // ═══════════════ GLOBAL SCOPE (priority 10) ═══════════════
  gf('F_FLOW_FROM_CAP_HOURS_V1', 'CAPACITY_HOURS_TO_FLOW_V1', 10,
    'FLOW_MAIN', ['CAPACITY_MAIN', 'HOURS_YEAR'],
    '\\dot{m} = \\frac{C}{H}', 'capacityToFlow', 'Flow = Capacity / Hours'),
  gf('F_CAP_FROM_FLOW_HOURS_V1', 'CAPACITY_HOURS_TO_FLOW_V1', 10,
    'CAPACITY_MAIN', ['FLOW_MAIN', 'HOURS_YEAR'],
    'C = \\dot{m} \\times H', 'flowToCapacity', 'Capacity = Flow × Hours'),
  gf('F_POWER_FROM_FLOW_SEC_PBASE_V1', 'THROUGHPUT_SEC_POWER_V1', 10,
    'POWER_ELEC', ['FLOW_MAIN', 'SEC_ELEC', 'P_BASE'],
    'P = P_{base} + \\dot{m} \\times SEC', 'flowSecToPower', 'P = P_base + Flow × SEC'),
  gf('F_EYEAR_FROM_P_HOURS_V1', 'POWER_TO_ANNUAL_ENERGY_V1', 10,
    'E_YEAR_ELEC', ['POWER_ELEC', 'HOURS_YEAR'],
    'E = P \\times H', 'powerToAnnualEnergy', 'E = P × Hours'),
  gf('F_P_FROM_EYEAR_HOURS_V1', 'POWER_TO_ANNUAL_ENERGY_V1', 10,
    'POWER_ELEC', ['E_YEAR_ELEC', 'HOURS_YEAR'],
    'P = \\frac{E}{H}', 'annualEnergyToPower', 'P = E / Hours'),
  gf('F_DUTY_FROM_FLOW_SEC_PBASE_V1', 'THROUGHPUT_SEC_HEAT_V1', 10,
    'DUTY_TH', ['FLOW_MAIN', 'SEC_TH', 'P_TH_BASE'],
    'Q = Q_{base} + \\dot{m} \\times SEC_{th}', 'flowSecToHeatDuty', 'Q = Q_base + Flow × SEC_th'),
  gf('F_POWER_COOL_FROM_DUTY_COP_V1', 'DUTY_DRIVEN_COOLING_V1', 10,
    'POWER_ELEC', ['COOLING_DUTY', 'COP_COOL', 'P_BASE'],
    'P = P_{base} + \\frac{Q}{COP}', 'coolingDutyToPower', 'P = P_base + Q / COP'),
  gf('F_FUEL_FROM_DUTY_EFF_LHV_V1', 'FUEL_DUTY_V1', 10,
    'FLOW_FUEL', ['FUEL_DUTY', 'EFF_TH', 'LHV_FUEL'],
    '\\dot{m}_{fuel} = \\frac{Q}{\\eta \\times LHV}', 'fuelDutyToFlow', 'm_fuel = Q / (η × LHV)'),
  gf('F_DUTY_FROM_FUEL_EFF_LHV_V1', 'FUEL_DUTY_V1', 10,
    'FUEL_DUTY', ['FLOW_FUEL', 'EFF_TH', 'LHV_FUEL'],
    'Q = \\dot{m}_{fuel} \\times \\eta \\times LHV', 'fuelFlowToDuty', 'Q = m_fuel × η × LHV'),
  gf('F_STEAM_FROM_DUTY_DH_V1', 'STEAM_DUTY_V1', 10,
    'FLOW_STEAM', ['STEAM_DUTY', 'DELTAH_STEAM'],
    '\\dot{m}_{steam} = \\frac{Q}{\\Delta h}', 'steamDutyToFlow', 'm_steam = Q / Δh'),
  gf('F_OUTFLOW_FROM_IN_RECOVERY_V1', 'SPLIT_RECOVERY_V1', 10,
    'FLOW_OUT', ['FLOW_IN', 'RECOVERY'],
    '\\dot{m}_{out} = \\dot{m}_{in} \\times r', 'splitRecoveryOut', 'Out = In × r'),
  gf('F_WASTE_FROM_IN_RECOVERY_V1', 'SPLIT_RECOVERY_V1', 10,
    'FLOW_WASTE', ['FLOW_IN', 'RECOVERY'],
    '\\dot{m}_{waste} = \\dot{m}_{in} \\times (1 - r)', 'splitRecoveryWaste', 'Waste = In × (1-r)'),
  gf('F_REMOVED_FROM_IN_REMOVAL_V1', 'REMOVAL_EFF_V1', 10,
    'FLOW_REMOVED', ['FLOW_IN', 'REMOVAL_EFF'],
    '\\dot{m}_{rem} = \\dot{m}_{in} \\times \\eta', 'removalEffRemoved', 'Removed = In × η'),
  gf('F_OUT_AFTER_REMOVAL_V1', 'REMOVAL_EFF_V1', 10,
    'FLOW_OUT', ['FLOW_IN', 'REMOVAL_EFF'],
    '\\dot{m}_{out} = \\dot{m}_{in} \\times (1 - \\eta)', 'removalEffOut', 'Out = In × (1-η)'),
  gf('F_DUTY_FROM_STEAM_DH_V1', 'STEAM_DUTY_V1', 10,
    'STEAM_DUTY', ['FLOW_STEAM', 'DELTAH_STEAM'],
    'Q = \\dot{m}_{steam} \\times \\Delta h', 'steamFlowToDuty', 'Q = m_steam × Δh'),
  gf('F_DUTY_FROM_POWER_COP_V1', 'DUTY_DRIVEN_COOLING_V1', 10,
    'COOLING_DUTY', ['POWER_ELEC', 'COP_COOL', 'P_BASE'],
    'Q = (P - P_{base}) \\times COP', 'powerToCoolingDuty', 'Q = (P - P_base) × COP'),
  gf('F_POWER_PUMP_FROM_FLOW_DPRHOETA_V1', 'PUMP_HYDRAULIC_V1', 10,
    'POWER_ELEC', ['FLOW_VOL', 'DELTA_P', 'ETA_PUMP', 'P_BASE'],
    'P = P_{base} + \\frac{\\Delta P \\times \\dot{V}}{\\eta}', 'pumpHydraulicPower', 'P = P_base + ΔP × V̇ / η'),
  gf('F_SPLIT_TOP_FROM_IN_V1', 'SPLITTER_V1', 10,
    'FLOW_TOP', ['FLOW_IN', 'SPLIT_FRAC'],
    '\\dot{m}_{top} = \\dot{m}_{in} \\times f', 'splitterTop', 'Top = In × f'),
  gf('F_SPLIT_BOTTOM_FROM_IN_V1', 'SPLITTER_V1', 10,
    'FLOW_BOTTOM', ['FLOW_IN', 'SPLIT_FRAC'],
    '\\dot{m}_{bot} = \\dot{m}_{in} \\times (1 - f)', 'splitterBottom', 'Bottom = In × (1-f)'),
  gf('F_MASS_BALANCE_RESIDUAL_V1', 'CONSERVATION_CHECK_V1', 10,
    'MASS_RESIDUAL', ['SUM_MASS_IN', 'SUM_MASS_OUT'],
    'r = \\sum \\dot{m}_{in} - \\sum \\dot{m}_{out}', 'massBalanceResidual', 'r = Σin - Σout'),

  // ═══════════════ ARCHETYPE: ELECTROLYSIS_UNIT (priority 100) ═══════════════
  af('ELECTROLYSIS_UNIT', 'F_FLOW_H2_FROM_CAP_HOURS_V1', 'CAPACITY_HOURS_TO_FLOW_V1', 100,
    'FLOW_H2', ['CAPACITY_H2', 'HOURS_YEAR'],
    '\\dot{m}_{H_2} = \\frac{C_{H_2}}{H}', 'capacityToFlow', 'H₂ flow from annual capacity'),
  af('ELECTROLYSIS_UNIT', 'F_POWER_FROM_FLOW_H2_SEC_V1', 'THROUGHPUT_SEC_POWER_V1', 100,
    'POWER_ELEC', ['FLOW_H2', 'SEC_ELEC_H2', 'P_BASE'],
    'P = P_{base} + \\dot{m}_{H_2} \\times SEC_{H_2}', 'flowSecToPower', 'Power from H₂ flow and SEC'),
  af('ELECTROLYSIS_UNIT', 'F_EYEAR_ELEC_FROM_P_HOURS_V1', 'POWER_TO_ANNUAL_ENERGY_V1', 100,
    'E_YEAR_ELEC', ['POWER_ELEC', 'HOURS_YEAR'],
    'E = P \\times H', 'powerToAnnualEnergy', 'Annual electricity from power'),
  af('ELECTROLYSIS_UNIT', 'F_H2O_FROM_H2_V1', 'ELECTROLYSIS_STOICH_V1', 100,
    'FLOW_H2O', ['FLOW_H2', 'WATER_FACTOR'],
    '\\dot{m}_{H_2O} = 9 \\times \\dot{m}_{H_2} \\times f_w', 'electrolysisStoichWater', 'H2O = 9 × H2 × water_factor'),
  af('ELECTROLYSIS_UNIT', 'F_O2_FROM_H2_V1', 'ELECTROLYSIS_STOICH_V1', 100,
    'FLOW_O2', ['FLOW_H2'],
    '\\dot{m}_{O_2} = 8 \\times \\dot{m}_{H_2}', 'electrolysisStoichOxygen', 'O2 = 8 × H2'),

  // ═══════════════ ARCHETYPE: ELEC_POWER_CONVERSION (priority 50) ═══════════════
  af('ELEC_POWER_CONVERSION', 'F_POWER_FIXED_V1', 'FIXED_POWER_V1', 50,
    'POWER_ELEC', ['P_FIXED'],
    'P = P_{fixed}', 'fixedPower', 'Direct assignment of fixed power'),

  // ═══════════════ ARCHETYPE: INSTRUMENTATION_CONTROL (priority 50) ═══════════════
  af('INSTRUMENTATION_CONTROL', 'F_POWER_FIXED_V1B', 'FIXED_POWER_V1', 50,
    'POWER_ELEC', ['P_FIXED'],
    'P = P_{fixed}', 'fixedPower', 'I&C fixed power'),

  // ═══════════════ ARCHETYPE: ELEC_DISTRIBUTION_PROTECTION (priority 50) ═══════════════
  af('ELEC_DISTRIBUTION_PROTECTION', 'F_POWER_FIXED_V1C', 'FIXED_POWER_V1', 50,
    'POWER_ELEC', ['P_FIXED'],
    'P = P_{fixed}', 'fixedPower', 'Distribution & protection fixed power'),

  // ═══════════════ ARCHETYPE: ELEC_STORAGE (priority 50) ═══════════════
  af('ELEC_STORAGE', 'F_BESS_E_FROM_P_DURATION_V1', 'BESS_ENERGY_V1', 50,
    'E_STORAGE', ['P_RATED', 'DURATION_H'],
    'E = P_{rated} \\times t', 'bessEnergy', 'BESS energy from power and duration'),
  af('ELEC_STORAGE', 'F_BESS_P_FROM_E_DURATION_V1', 'BESS_ENERGY_V1', 50,
    'P_RATED', ['E_STORAGE', 'DURATION_H'],
    'P_{rated} = \\frac{E}{t}', 'bessPower', 'BESS power from energy and duration'),

  // ═══════════════ ARCHETYPE: POWER_GENERATION_UNIT (priority 50) ═══════════════
  af('POWER_GENERATION_UNIT', 'F_POWER_GEN_FROM_FUEL_EFF_LHV_V1', 'GENERATOR_V1', 50,
    'POWER_ELEC', ['FLOW_FUEL', 'EFF_ELEC', 'LHV_FUEL', 'P_BASE'],
    'P = P_{base} + \\dot{m}_{fuel} \\times \\eta_{el} \\times LHV', 'generatorPower', 'Generated power from fuel'),
  af('POWER_GENERATION_UNIT', 'F_FUEL_FROM_POWER_GEN_EFF_LHV_V1', 'GENERATOR_V1', 50,
    'FLOW_FUEL', ['POWER_ELEC', 'EFF_ELEC', 'LHV_FUEL', 'P_BASE'],
    '\\dot{m}_{fuel} = \\frac{P - P_{base}}{\\eta_{el} \\times LHV}', 'generatorFuel', 'Fuel from generated power'),

  // ═══════════════ EQUIPMENT: Methanation Reactor (priority 1000) ═══════════════
  ef('Methanation Reactor', 'F_METHANATION_CO_CONV_V1', 'SYNTH_STOICH_V1', 1000,
    'F_CO_CONV_KMOL_H', ['F_CO_IN_KMOL_H', 'X_CO'],
    'F_{CO,conv} = F_{CO,in} \\times X_{CO}', 'conversionCalc', 'CO converted'),
  ef('Methanation Reactor', 'F_METHANATION_CO2_CONV_V1', 'SYNTH_STOICH_V1', 1000,
    'F_CO2_CONV_KMOL_H', ['F_CO2_IN_KMOL_H', 'X_CO2'],
    'F_{CO_2,conv} = F_{CO_2,in} \\times X_{CO_2}', 'conversionCalc', 'CO₂ converted'),
  ef('Methanation Reactor', 'F_METHANATION_CH4_PROD_V1', 'SYNTH_STOICH_V1', 1000,
    'F_CH4_OUT_KMOL_H', ['F_CH4_IN_KMOL_H', 'F_CO_CONV_KMOL_H', 'F_CO2_CONV_KMOL_H'],
    'F_{CH_4,out} = F_{CH_4,in} + F_{CO,conv} + F_{CO_2,conv}', 'methanationCH4', 'CH4_out = CH4_in + CO_conv + CO2_conv'),
  ef('Methanation Reactor', 'F_METHANATION_H2O_PROD_V1', 'SYNTH_STOICH_V1', 1000,
    'F_H2O_OUT_KMOL_H', ['F_H2O_IN_KMOL_H', 'F_CO_CONV_KMOL_H', 'F_CO2_CONV_KMOL_H'],
    'F_{H_2O,out} = F_{H_2O,in} + F_{CO,conv} + 2 F_{CO_2,conv}', 'methanationH2O', 'H2O_out = H2O_in + CO_conv + 2×CO2_conv'),
  ef('Methanation Reactor', 'F_METHANATION_H2_CONS_V1', 'SYNTH_STOICH_V1', 1000,
    'F_H2_OUT_KMOL_H', ['F_H2_IN_KMOL_H', 'F_CO_CONV_KMOL_H', 'F_CO2_CONV_KMOL_H'],
    'F_{H_2,out} = F_{H_2,in} - 3 F_{CO,conv} - 4 F_{CO_2,conv}', 'methanationH2', 'H2_out = H2_in - 3×CO_conv - 4×CO2_conv'),

  // ═══════════════ EQUIPMENT: Methanol Synthesis Reactor (priority 1000) ═══════════════
  ef('Methanol Synthesis Reactor', 'F_MEOH_CO_CONV_V1', 'SYNTH_STOICH_V1', 1000,
    'F_CO_CONV_KMOL_H', ['F_CO_IN_KMOL_H', 'X_CO'],
    'F_{CO,conv} = F_{CO,in} \\times X_{CO}', 'conversionCalc', 'CO converted'),
  ef('Methanol Synthesis Reactor', 'F_MEOH_CO2_CONV_V1', 'SYNTH_STOICH_V1', 1000,
    'F_CO2_CONV_KMOL_H', ['F_CO2_IN_KMOL_H', 'X_CO2'],
    'F_{CO_2,conv} = F_{CO_2,in} \\times X_{CO_2}', 'conversionCalc', 'CO₂ converted'),
  ef('Methanol Synthesis Reactor', 'F_MEOH_PROD_V1', 'SYNTH_STOICH_V1', 1000,
    'F_MEOH_OUT_KMOL_H', ['F_MEOH_IN_KMOL_H', 'F_CO_CONV_KMOL_H', 'F_CO2_CONV_KMOL_H'],
    'F_{MeOH,out} = F_{MeOH,in} + F_{CO,conv} + F_{CO_2,conv}', 'methanolProd', 'MeOH_out = MeOH_in + CO_conv + CO2_conv'),
  ef('Methanol Synthesis Reactor', 'F_MEOH_H2O_PROD_V1', 'SYNTH_STOICH_V1', 1000,
    'F_H2O_OUT_KMOL_H', ['F_H2O_IN_KMOL_H', 'F_CO2_CONV_KMOL_H'],
    'F_{H_2O,out} = F_{H_2O,in} + F_{CO_2,conv}', 'methanolH2O', 'H2O_out = H2O_in + CO2_conv (only CO2 path)'),
  ef('Methanol Synthesis Reactor', 'F_MEOH_H2_CONS_V1', 'SYNTH_STOICH_V1', 1000,
    'F_H2_OUT_KMOL_H', ['F_H2_IN_KMOL_H', 'F_CO_CONV_KMOL_H', 'F_CO2_CONV_KMOL_H'],
    'F_{H_2,out} = F_{H_2,in} - 2 F_{CO,conv} - 3 F_{CO_2,conv}', 'methanolH2', 'H2_out = H2_in - 2×CO_conv - 3×CO2_conv'),

  // ═══════════════ EQUIPMENT: DME Reactor (priority 1000) ═══════════════
  ef('DME Reactor', 'F_DME_MEOH_CONV_V1', 'SYNTH_STOICH_V1', 1000,
    'F_MEOH_CONV_KMOL_H', ['F_MEOH_IN_KMOL_H', 'X_MEOH'],
    'F_{MeOH,conv} = F_{MeOH,in} \\times X_{MeOH}', 'conversionCalc', 'MeOH converted'),
  ef('DME Reactor', 'F_DME_PROD_V1', 'SYNTH_STOICH_V1', 1000,
    'F_DME_OUT_KMOL_H', ['F_DME_IN_KMOL_H', 'F_MEOH_CONV_KMOL_H'],
    'F_{DME,out} = F_{DME,in} + 0.5 F_{MeOH,conv}', 'dmeProd', 'DME_out = DME_in + 0.5×MeOH_conv'),
  ef('DME Reactor', 'F_DME_H2O_PROD_V1', 'SYNTH_STOICH_V1', 1000,
    'F_H2O_OUT_KMOL_H', ['F_H2O_IN_KMOL_H', 'F_MEOH_CONV_KMOL_H'],
    'F_{H_2O,out} = F_{H_2O,in} + 0.5 F_{MeOH,conv}', 'dmeH2O', 'H2O_out = H2O_in + 0.5×MeOH_conv'),
  ef('DME Reactor', 'F_DME_MEOH_OUT_V1', 'SYNTH_STOICH_V1', 1000,
    'F_MEOH_OUT_KMOL_H', ['F_MEOH_IN_KMOL_H', 'F_MEOH_CONV_KMOL_H'],
    'F_{MeOH,out} = F_{MeOH,in} - F_{MeOH,conv}', 'dmeUnreactedMeOH', 'MeOH_out = MeOH_in - MeOH_conv'),

  // ═══════════════ EQUIPMENT: Ammonia Synthesis Reactor (priority 1000) ═══════════════
  ef('Ammonia Synthesis Reactor', 'F_NH3_N2_CONV_V1', 'SYNTH_STOICH_V1', 1000,
    'F_N2_CONV_KMOL_H', ['F_N2_IN_KMOL_H', 'X_N2'],
    'F_{N_2,conv} = F_{N_2,in} \\times X_{N_2}', 'conversionCalc', 'N₂ converted'),
  ef('Ammonia Synthesis Reactor', 'F_NH3_PROD_V1', 'SYNTH_STOICH_V1', 1000,
    'F_NH3_OUT_KMOL_H', ['F_NH3_IN_KMOL_H', 'F_N2_CONV_KMOL_H'],
    'F_{NH_3,out} = F_{NH_3,in} + 2 F_{N_2,conv}', 'ammoniaProd', 'NH3_out = NH3_in + 2×N2_conv'),
  ef('Ammonia Synthesis Reactor', 'F_NH3_H2_OUT_V1', 'SYNTH_STOICH_V1', 1000,
    'F_H2_OUT_KMOL_H', ['F_H2_IN_KMOL_H', 'F_N2_CONV_KMOL_H'],
    'F_{H_2,out} = F_{H_2,in} - 3 F_{N_2,conv}', 'ammoniaH2', 'H2_out = H2_in - 3×N2_conv'),

  // ═══════════════ EQUIPMENT: Haber Bosch Loop Skid (priority 1000) ═══════════════
  ef('Haber Bosch Loop Skid', 'F_HB_LOOP_PURGE_V1', 'LOOP_PURGE_V1', 1000,
    'F_PURGE_KMOL_H', ['F_RECYCLE_KMOL_H', 'PURGE_FRAC'],
    'F_{purge} = F_{recycle} \\times f', 'loopPurge', 'purge = recycle × f'),
  ef('Haber Bosch Loop Skid', 'F_HB_LOOP_RECYCLE_OUT_V1', 'LOOP_PURGE_V1', 1000,
    'F_RECYCLE_OUT_KMOL_H', ['F_RECYCLE_KMOL_H', 'F_PURGE_KMOL_H'],
    'F_{recycle,out} = F_{recycle} - F_{purge}', 'loopRecycleOut', 'recycle_out = recycle - purge'),

  // ═══════════════ EQUIPMENT: Fischer Tropsch Reactor (priority 1000) ═══════════════
  ef('Fischer Tropsch Reactor', 'F_FT_CO_CONV_V1', 'SYNTH_YIELD_V1', 1000,
    'F_CO_CONV_KMOL_H', ['F_CO_IN_KMOL_H', 'X_CO'],
    'F_{CO,conv} = F_{CO,in} \\times X_{CO}', 'conversionCalc', 'CO converted'),
  ef('Fischer Tropsch Reactor', 'F_FT_H2_OUT_V1', 'SYNTH_YIELD_V1', 1000,
    'F_H2_OUT_KMOL_H', ['F_H2_IN_KMOL_H', 'F_CO_CONV_KMOL_H', 'R_H2_CO'],
    'F_{H_2,out} = F_{H_2,in} - R \\times F_{CO,conv}', 'ftH2Out', 'H2_out = H2_in - R × CO_conv'),
  ef('Fischer Tropsch Reactor', 'F_FT_H2O_PROD_V1', 'SYNTH_YIELD_V1', 1000,
    'F_H2O_OUT_KMOL_H', ['F_H2O_IN_KMOL_H', 'F_CO_CONV_KMOL_H'],
    'F_{H_2O,out} = F_{H_2O,in} + F_{CO,conv}', 'ftH2O', 'H2O_out = H2O_in + CO_conv'),
  ef('Fischer Tropsch Reactor', 'F_FT_LIQ_PROD_MASS_V1', 'SYNTH_YIELD_V1', 1000,
    'F_FT_LIQ_KG_H', ['F_CO_CONV_KMOL_H', 'Y_LIQ_KG_PER_KMOLCO'],
    '\\dot{m}_{liq} = F_{CO,conv} \\times Y', 'ftLiquid', 'liq = CO_conv × Y'),
  ef('Fischer Tropsch Reactor', 'F_FT_OFFGAS_CO_OUT_V1', 'SYNTH_YIELD_V1', 1000,
    'F_CO_OUT_KMOL_H', ['F_CO_IN_KMOL_H', 'F_CO_CONV_KMOL_H'],
    'F_{CO,out} = F_{CO,in} - F_{CO,conv}', 'ftCOOut', 'CO_out = CO_in - CO_conv'),
  ef('Fischer Tropsch Reactor', 'F_FT_CO2_BYPROD_V1', 'SYNTH_YIELD_V1', 1000,
    'F_CO2_OUT_KMOL_H', ['F_CO2_IN_KMOL_H', 'F_CO_CONV_KMOL_H', 'Y_CO2_PER_CO'],
    'F_{CO_2,out} = F_{CO_2,in} + F_{CO,conv} \\times Y_{CO_2}', 'ftCO2Byproduct', 'CO₂ byproduct'),
  ef('Fischer Tropsch Reactor', 'F_FT_CH4_BYPROD_V1', 'SYNTH_YIELD_V1', 1000,
    'F_CH4_OUT_KMOL_H', ['F_CH4_IN_KMOL_H', 'F_CO_CONV_KMOL_H', 'Y_CH4_PER_CO'],
    'F_{CH_4,out} = F_{CH_4,in} + F_{CO,conv} \\times Y_{CH_4}', 'ftCH4Byproduct', 'CH₄ byproduct'),

  // ═══════════════ EQUIPMENT: Polymerization Reactor (priority 1000) ═══════════════
  ef('Polymerization Reactor', 'F_POLY_MONOMER_CONV_V1', 'POLYMERIZATION_V1', 1000,
    'F_MONOMER_CONV_KMOL_H', ['F_MONOMER_IN_KMOL_H', 'X_MONOMER'],
    'F_{mono,conv} = F_{mono,in} \\times X', 'conversionCalc', 'Monomer converted'),
  ef('Polymerization Reactor', 'F_POLY_PRODUCT_MASS_V1', 'POLYMERIZATION_V1', 1000,
    'F_POLYMER_KG_H', ['F_MONOMER_CONV_KMOL_H', 'MW_MONOMER', 'YIELD_MASS'],
    '\\dot{m}_{poly} = F_{conv} \\times MW \\times Y', 'polyProductMass', 'polymer = conv × MW × yield'),
  ef('Polymerization Reactor', 'F_POLY_MONOMER_OUT_V1', 'POLYMERIZATION_V1', 1000,
    'F_MONOMER_OUT_KMOL_H', ['F_MONOMER_IN_KMOL_H', 'F_MONOMER_CONV_KMOL_H'],
    'F_{mono,out} = F_{mono,in} - F_{mono,conv}', 'polyMonomerOut', 'Unreacted monomer'),
] as const;
