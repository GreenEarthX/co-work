/**
 * Parameter keys registry — all 110 parameter key definitions.
 * Pure data, no logic.
 */
import type { ParameterKeyDef } from '../types';

// Helper to reduce boilerplate
const g = (
  paramKey: string, displayName: string, description: string,
  unitFamily: string, canonicalUnit: string,
  isUserEditable: boolean, supportsOverride: boolean,
  typicalSource: ParameterKeyDef['typicalSource'],
  derivedByModelId: string | null, notes = ''
): ParameterKeyDef => ({
  scopeType: 'GLOBAL', scopeId: '*', paramKey, displayName, description,
  unitFamily, canonicalUnit, valueType: 'number',
  isUserEditable, supportsOverride, typicalSource, derivedByModelId, notes,
});

const arch = (
  scopeId: string, paramKey: string, displayName: string, description: string,
  unitFamily: string, canonicalUnit: string,
  isUserEditable: boolean, supportsOverride: boolean,
  typicalSource: ParameterKeyDef['typicalSource'],
  derivedByModelId: string | null = null, notes = ''
): ParameterKeyDef => ({
  scopeType: 'ARCHETYPE', scopeId, paramKey, displayName, description,
  unitFamily, canonicalUnit, valueType: 'number',
  isUserEditable, supportsOverride, typicalSource, derivedByModelId, notes,
});

const equip = (
  scopeId: string, paramKey: string, displayName: string, description: string,
  unitFamily: string, canonicalUnit: string,
  isUserEditable: boolean,
  typicalSource: ParameterKeyDef['typicalSource'],
  derivedByModelId: string | null = null, notes = ''
): ParameterKeyDef => ({
  scopeType: 'EQUIPMENT', scopeId, paramKey, displayName, description,
  unitFamily, canonicalUnit, valueType: 'number',
  isUserEditable, supportsOverride: isUserEditable, typicalSource, derivedByModelId, notes,
});

export const PARAMETER_KEYS: readonly ParameterKeyDef[] = [
  // ═══════════════ GLOBAL SCOPE (*) ═══════════════
  g('HOURS_YEAR', 'Operating hours per year', 'Annual operating hours for capacity calculations', 'TIME_PER_YEAR', 'h/year', true, true, 'DEFAULT_LIBRARY', null),
  g('FLOW_MAIN', 'Main throughput flow', 'Primary mass flow through equipment', 'MASS_PER_TIME', 'kg/h', true, true, 'DEFAULT_LIBRARY', 'CAPACITY_HOURS_TO_FLOW_V1', 'Mixed: user or derived'),
  g('CAPACITY_MAIN', 'Annual capacity', 'Annual mass throughput', 'MASS_PER_YEAR', 'kg/year', true, true, 'DEFAULT_LIBRARY', 'CAPACITY_HOURS_TO_FLOW_V1', 'Mixed: user or derived'),
  g('POWER_ELEC', 'Electrical power', 'Electrical power consumption', 'POWER', 'kW', true, true, 'DERIVED', 'THROUGHPUT_SEC_POWER_V1'),
  g('E_YEAR_ELEC', 'Annual electricity', 'Annual electricity consumption', 'ENERGY_PER_YEAR', 'kWh/year', false, false, 'DERIVED', 'POWER_TO_ANNUAL_ENERGY_V1'),
  g('P_BASE', 'Base power (fixed load)', 'Fixed electrical load independent of throughput', 'POWER', 'kW', true, true, 'DEFAULT_LIBRARY', null),
  g('SEC_ELEC', 'SEC electricity (generic)', 'Specific electricity consumption', 'ENERGY_PER_MASS', 'kWh/kg', true, true, 'DEFAULT_LIBRARY', null),
  g('DUTY_TH', 'Thermal duty', 'Thermal heat duty', 'POWER', 'kW', true, true, 'DERIVED', 'THROUGHPUT_SEC_HEAT_V1'),
  g('SEC_TH', 'SEC thermal', 'Specific thermal energy consumption', 'ENERGY_PER_MASS', 'kWh/kg', true, true, 'DEFAULT_LIBRARY', null),
  g('P_TH_BASE', 'Base thermal duty', 'Fixed thermal load independent of throughput', 'POWER', 'kW', true, true, 'DEFAULT_LIBRARY', null),
  g('COOLING_DUTY', 'Cooling load', 'Cooling duty required', 'POWER', 'kW', true, true, 'DEFAULT_LIBRARY', null, 'Mixed source'),
  g('COP_COOL', 'COP for cooling', 'Coefficient of performance for cooling system', 'DIMENSIONLESS', '-', true, true, 'DEFAULT_LIBRARY', null),
  g('E_YEAR_TH', 'Annual thermal energy', 'Annual thermal energy consumption', 'ENERGY_PER_YEAR', 'kWh/year', false, false, 'DERIVED', 'DUTY_TO_ANNUAL_TH_ENERGY_V1'),
  g('FUEL_DUTY', 'Fuel-fired duty', 'Thermal duty from fuel combustion', 'POWER', 'kW', true, true, 'DEFAULT_LIBRARY', 'FUEL_DUTY_V1', 'Mixed source'),
  g('FLOW_FUEL', 'Fuel mass flow', 'Fuel consumption mass flow', 'MASS_PER_TIME', 'kg/h', true, true, 'DEFAULT_LIBRARY', 'FUEL_DUTY_V1', 'Mixed source'),
  g('LHV_FUEL', 'Fuel LHV', 'Lower heating value of fuel', 'ENERGY_PER_MASS', 'kWh/kg', true, true, 'DEFAULT_LIBRARY', null),
  g('EFF_TH', 'Thermal efficiency', 'Thermal conversion efficiency', 'DIMENSIONLESS', '-', true, true, 'DEFAULT_LIBRARY', null),
  g('STEAM_DUTY', 'Steam duty', 'Steam heat duty', 'POWER', 'kW', true, true, 'DEFAULT_LIBRARY', 'STEAM_DUTY_V1', 'Mixed source'),
  g('FLOW_STEAM', 'Steam flow', 'Steam mass flow rate', 'MASS_PER_TIME', 'kg/h', true, true, 'DEFAULT_LIBRARY', 'STEAM_DUTY_V1', 'Mixed source'),
  g('DELTAH_STEAM', 'Steam enthalpy rise', 'Enthalpy change across steam system', 'ENERGY_PER_MASS', 'kWh/kg', true, true, 'DEFAULT_LIBRARY', null),
  g('FLOW_IN', 'Inlet flow (split/removal)', 'Inlet flow for separation/splitting', 'MASS_PER_TIME', 'kg/h', true, true, 'USER', null),
  g('FLOW_OUT', 'Outlet flow (split/removal)', 'Outlet product flow after separation', 'MASS_PER_TIME', 'kg/h', false, false, 'DERIVED', 'SPLIT_RECOVERY_V1'),
  g('FLOW_WASTE', 'Waste flow', 'Waste/reject flow after separation', 'MASS_PER_TIME', 'kg/h', false, false, 'DERIVED', 'SPLIT_RECOVERY_V1'),
  g('RECOVERY', 'Recovery fraction', 'Fraction of feed recovered as product', 'DIMENSIONLESS', '-', true, true, 'DEFAULT_LIBRARY', null),
  g('REMOVAL_EFF', 'Removal efficiency', 'Contaminant removal efficiency', 'DIMENSIONLESS', '-', true, true, 'DEFAULT_LIBRARY', null),
  g('FLOW_REMOVED', 'Removed flow', 'Flow of removed contaminant', 'MASS_PER_TIME', 'kg/h', false, false, 'DERIVED', 'REMOVAL_EFF_V1'),

  // ═══════════════ ARCHETYPE: ELECTROLYSIS_UNIT ═══════════════
  arch('ELECTROLYSIS_UNIT', 'CAPACITY_H2', 'H₂ capacity', 'Annual hydrogen production capacity', 'MASS_PER_YEAR', 'kg/year', true, true, 'USER'),
  arch('ELECTROLYSIS_UNIT', 'FLOW_H2', 'H₂ flow', 'Hydrogen mass flow rate', 'MASS_PER_TIME', 'kg/h', true, true, 'DEFAULT_LIBRARY', 'CAPACITY_HOURS_TO_FLOW_V1'),
  arch('ELECTROLYSIS_UNIT', 'SEC_ELEC_H2', 'SEC electricity H₂', 'Specific electricity consumption for hydrogen', 'ENERGY_PER_MASS', 'kWh/kg', true, true, 'DEFAULT_LIBRARY'),
  arch('ELECTROLYSIS_UNIT', 'WATER_FACTOR', 'Water factor', 'Litres of water per kg H₂', 'DIMENSIONLESS', '-', true, true, 'DEFAULT_LIBRARY'),
  arch('ELECTROLYSIS_UNIT', 'FLOW_H2O', 'Water flow', 'Water consumption flow rate', 'MASS_PER_TIME', 'kg/h', true, true, 'DEFAULT_LIBRARY', 'ELECTROLYSIS_STOICH_V1'),
  arch('ELECTROLYSIS_UNIT', 'FLOW_O2', 'Oxygen flow', 'Oxygen byproduct flow rate', 'MASS_PER_TIME', 'kg/h', true, true, 'DEFAULT_LIBRARY', 'ELECTROLYSIS_STOICH_V1'),

  // ═══════════════ ARCHETYPE: ELEC_POWER_CONVERSION ═══════════════
  arch('ELEC_POWER_CONVERSION', 'P_FIXED', 'Fixed power', 'Fixed electrical power for power conversion', 'POWER', 'kW', true, true, 'USER'),

  // ═══════════════ ARCHETYPE: INSTRUMENTATION_CONTROL ═══════════════
  arch('INSTRUMENTATION_CONTROL', 'P_FIXED', 'Fixed power', 'Fixed electrical power for I&C systems', 'POWER', 'kW', true, true, 'USER'),

  // ═══════════════ ARCHETYPE: ELEC_DISTRIBUTION_PROTECTION ═══════════════
  arch('ELEC_DISTRIBUTION_PROTECTION', 'P_FIXED', 'Fixed power', 'Fixed electrical power for distribution & protection', 'POWER', 'kW', true, true, 'USER'),

  // ═══════════════ ARCHETYPE: ELEC_STORAGE ═══════════════
  arch('ELEC_STORAGE', 'P_RATED', 'BESS rated power', 'Battery energy storage rated power', 'POWER', 'kW', true, true, 'USER'),
  arch('ELEC_STORAGE', 'DURATION_H', 'BESS duration', 'Battery storage duration', 'TIME', 'h', true, true, 'USER'),
  arch('ELEC_STORAGE', 'E_STORAGE', 'BESS energy', 'Battery energy storage capacity', 'ENERGY', 'kWh', true, true, 'DEFAULT_LIBRARY', 'BESS_ENERGY_V1'),

  // ═══════════════ ARCHETYPE: POWER_GENERATION_UNIT ═══════════════
  arch('POWER_GENERATION_UNIT', 'EFF_ELEC', 'Electrical efficiency', 'Generator electrical efficiency', 'DIMENSIONLESS', '-', true, true, 'DEFAULT_LIBRARY'),
  arch('POWER_GENERATION_UNIT', 'LHV_FUEL', 'Fuel LHV', 'Lower heating value of generator fuel', 'ENERGY_PER_MASS', 'kWh/kg', true, true, 'DEFAULT_LIBRARY'),
  arch('POWER_GENERATION_UNIT', 'FLOW_FUEL', 'Fuel flow', 'Generator fuel consumption', 'MASS_PER_TIME', 'kg/h', true, true, 'DEFAULT_LIBRARY', 'GENERATOR_V1'),
  arch('POWER_GENERATION_UNIT', 'P_BASE', 'Base power', 'Generator base power output', 'POWER', 'kW', true, true, 'DEFAULT_LIBRARY'),
  arch('POWER_GENERATION_UNIT', 'POWER_ELEC', 'Generated power', 'Electrical power output', 'POWER', 'kW', true, true, 'DEFAULT_LIBRARY', 'GENERATOR_V1'),

  // ═══════════════ EQUIPMENT: Methanation Reactor ═══════════════
  equip('Methanation Reactor', 'F_CO_IN_KMOL_H', 'CO inlet flow', 'CO feed molar flow', 'MOLAR_FLOW', 'kmol/h', true, 'USER'),
  equip('Methanation Reactor', 'F_CO2_IN_KMOL_H', 'CO₂ inlet flow', 'CO₂ feed molar flow', 'MOLAR_FLOW', 'kmol/h', true, 'USER'),
  equip('Methanation Reactor', 'F_H2_IN_KMOL_H', 'H₂ inlet flow', 'H₂ feed molar flow', 'MOLAR_FLOW', 'kmol/h', true, 'USER'),
  equip('Methanation Reactor', 'F_CH4_IN_KMOL_H', 'CH₄ inlet flow', 'CH₄ feed molar flow', 'MOLAR_FLOW', 'kmol/h', true, 'USER'),
  equip('Methanation Reactor', 'F_H2O_IN_KMOL_H', 'H₂O inlet flow', 'H₂O feed molar flow', 'MOLAR_FLOW', 'kmol/h', true, 'USER'),
  equip('Methanation Reactor', 'X_CO', 'CO conversion', 'CO conversion fraction', 'DIMENSIONLESS', '-', true, 'USER'),
  equip('Methanation Reactor', 'X_CO2', 'CO₂ conversion', 'CO₂ conversion fraction', 'DIMENSIONLESS', '-', true, 'USER'),
  equip('Methanation Reactor', 'F_CO_CONV_KMOL_H', 'CO converted flow', 'CO consumed by reaction', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'SYNTH_STOICH_V1'),
  equip('Methanation Reactor', 'F_CO2_CONV_KMOL_H', 'CO₂ converted flow', 'CO₂ consumed by reaction', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'SYNTH_STOICH_V1'),
  equip('Methanation Reactor', 'F_H2_OUT_KMOL_H', 'H₂ outlet flow', 'H₂ outlet molar flow', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'SYNTH_STOICH_V1'),
  equip('Methanation Reactor', 'F_CH4_OUT_KMOL_H', 'CH₄ outlet flow', 'CH₄ product molar flow', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'SYNTH_STOICH_V1'),
  equip('Methanation Reactor', 'F_H2O_OUT_KMOL_H', 'H₂O outlet flow', 'H₂O outlet molar flow', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'SYNTH_STOICH_V1'),

  // ═══════════════ EQUIPMENT: Methanol Synthesis Reactor ═══════════════
  equip('Methanol Synthesis Reactor', 'F_CO_IN_KMOL_H', 'CO inlet flow', 'CO feed molar flow', 'MOLAR_FLOW', 'kmol/h', true, 'USER'),
  equip('Methanol Synthesis Reactor', 'F_CO2_IN_KMOL_H', 'CO₂ inlet flow', 'CO₂ feed molar flow', 'MOLAR_FLOW', 'kmol/h', true, 'USER'),
  equip('Methanol Synthesis Reactor', 'F_H2_IN_KMOL_H', 'H₂ inlet flow', 'H₂ feed molar flow', 'MOLAR_FLOW', 'kmol/h', true, 'USER'),
  equip('Methanol Synthesis Reactor', 'F_MEOH_IN_KMOL_H', 'MeOH inlet flow', 'Methanol feed molar flow', 'MOLAR_FLOW', 'kmol/h', true, 'USER'),
  equip('Methanol Synthesis Reactor', 'F_H2O_IN_KMOL_H', 'H₂O inlet flow', 'H₂O feed molar flow', 'MOLAR_FLOW', 'kmol/h', true, 'USER'),
  equip('Methanol Synthesis Reactor', 'X_CO', 'CO conversion', 'CO conversion fraction', 'DIMENSIONLESS', '-', true, 'USER'),
  equip('Methanol Synthesis Reactor', 'X_CO2', 'CO₂ conversion', 'CO₂ conversion fraction', 'DIMENSIONLESS', '-', true, 'USER'),
  equip('Methanol Synthesis Reactor', 'F_CO_CONV_KMOL_H', 'CO converted flow', 'CO consumed by reaction', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'SYNTH_STOICH_V1'),
  equip('Methanol Synthesis Reactor', 'F_CO2_CONV_KMOL_H', 'CO₂ converted flow', 'CO₂ consumed by reaction', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'SYNTH_STOICH_V1'),
  equip('Methanol Synthesis Reactor', 'F_H2_OUT_KMOL_H', 'H₂ outlet flow', 'H₂ outlet molar flow', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'SYNTH_STOICH_V1'),
  equip('Methanol Synthesis Reactor', 'F_MEOH_OUT_KMOL_H', 'MeOH outlet flow', 'Methanol product molar flow', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'SYNTH_STOICH_V1'),
  equip('Methanol Synthesis Reactor', 'F_H2O_OUT_KMOL_H', 'H₂O outlet flow', 'H₂O outlet molar flow', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'SYNTH_STOICH_V1'),

  // ═══════════════ EQUIPMENT: DME Reactor ═══════════════
  equip('DME Reactor', 'F_MEOH_IN_KMOL_H', 'MeOH inlet flow', 'Methanol feed molar flow', 'MOLAR_FLOW', 'kmol/h', true, 'USER'),
  equip('DME Reactor', 'F_DME_IN_KMOL_H', 'DME inlet flow', 'DME feed molar flow', 'MOLAR_FLOW', 'kmol/h', true, 'USER'),
  equip('DME Reactor', 'F_H2O_IN_KMOL_H', 'H₂O inlet flow', 'H₂O feed molar flow', 'MOLAR_FLOW', 'kmol/h', true, 'USER'),
  equip('DME Reactor', 'X_MEOH', 'MeOH conversion', 'Methanol conversion fraction', 'DIMENSIONLESS', '-', true, 'USER'),
  equip('DME Reactor', 'F_MEOH_CONV_KMOL_H', 'MeOH converted flow', 'Methanol consumed by reaction', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'SYNTH_STOICH_V1'),
  equip('DME Reactor', 'F_DME_OUT_KMOL_H', 'DME outlet flow', 'DME product molar flow', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'SYNTH_STOICH_V1'),
  equip('DME Reactor', 'F_MEOH_OUT_KMOL_H', 'MeOH outlet flow', 'Unreacted methanol molar flow', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'SYNTH_STOICH_V1'),
  equip('DME Reactor', 'F_H2O_OUT_KMOL_H', 'H₂O outlet flow', 'H₂O outlet molar flow', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'SYNTH_STOICH_V1'),

  // ═══════════════ EQUIPMENT: Ammonia Synthesis Reactor ═══════════════
  equip('Ammonia Synthesis Reactor', 'F_N2_IN_KMOL_H', 'N₂ inlet flow', 'Nitrogen feed molar flow', 'MOLAR_FLOW', 'kmol/h', true, 'USER'),
  equip('Ammonia Synthesis Reactor', 'F_H2_IN_KMOL_H', 'H₂ inlet flow', 'Hydrogen feed molar flow', 'MOLAR_FLOW', 'kmol/h', true, 'USER'),
  equip('Ammonia Synthesis Reactor', 'F_NH3_IN_KMOL_H', 'NH₃ inlet flow', 'Ammonia feed molar flow', 'MOLAR_FLOW', 'kmol/h', true, 'USER'),
  equip('Ammonia Synthesis Reactor', 'X_N2', 'N₂ conversion', 'Nitrogen single-pass conversion', 'DIMENSIONLESS', '-', true, 'USER'),
  equip('Ammonia Synthesis Reactor', 'F_N2_CONV_KMOL_H', 'N₂ converted flow', 'Nitrogen consumed by reaction', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'SYNTH_STOICH_V1'),
  equip('Ammonia Synthesis Reactor', 'F_H2_OUT_KMOL_H', 'H₂ outlet flow', 'Unreacted hydrogen molar flow', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'SYNTH_STOICH_V1'),
  equip('Ammonia Synthesis Reactor', 'F_NH3_OUT_KMOL_H', 'NH₃ outlet flow', 'Ammonia product molar flow', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'SYNTH_STOICH_V1'),

  // ═══════════════ EQUIPMENT: Haber Bosch Loop Skid ═══════════════
  equip('Haber Bosch Loop Skid', 'F_RECYCLE_KMOL_H', 'Recycle flow', 'Recycle loop molar flow', 'MOLAR_FLOW', 'kmol/h', true, 'USER'),
  equip('Haber Bosch Loop Skid', 'PURGE_FRAC', 'Purge fraction', 'Fraction of recycle purged', 'DIMENSIONLESS', '-', true, 'USER'),
  equip('Haber Bosch Loop Skid', 'F_PURGE_KMOL_H', 'Purge flow', 'Purge stream molar flow', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'LOOP_PURGE_V1'),
  equip('Haber Bosch Loop Skid', 'F_RECYCLE_OUT_KMOL_H', 'Recycle outlet flow', 'Recycle loop outlet molar flow', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'LOOP_PURGE_V1'),

  // ═══════════════ EQUIPMENT: Fischer Tropsch Reactor ═══════════════
  equip('Fischer Tropsch Reactor', 'F_CO_IN_KMOL_H', 'CO inlet flow', 'CO feed molar flow', 'MOLAR_FLOW', 'kmol/h', true, 'USER'),
  equip('Fischer Tropsch Reactor', 'F_CO2_IN_KMOL_H', 'CO₂ inlet flow', 'CO₂ feed molar flow', 'MOLAR_FLOW', 'kmol/h', true, 'USER'),
  equip('Fischer Tropsch Reactor', 'F_H2_IN_KMOL_H', 'H₂ inlet flow', 'H₂ feed molar flow', 'MOLAR_FLOW', 'kmol/h', true, 'USER'),
  equip('Fischer Tropsch Reactor', 'F_H2O_IN_KMOL_H', 'H₂O inlet flow', 'H₂O feed molar flow', 'MOLAR_FLOW', 'kmol/h', true, 'USER'),
  equip('Fischer Tropsch Reactor', 'F_CH4_IN_KMOL_H', 'CH₄ inlet flow', 'CH₄ feed molar flow', 'MOLAR_FLOW', 'kmol/h', true, 'USER'),
  equip('Fischer Tropsch Reactor', 'X_CO', 'CO conversion', 'CO single-pass conversion', 'DIMENSIONLESS', '-', true, 'USER'),
  equip('Fischer Tropsch Reactor', 'R_H2_CO', 'H₂/CO ratio', 'Mol H₂ consumed per mol CO consumed', 'DIMENSIONLESS', '-', true, 'USER'),
  equip('Fischer Tropsch Reactor', 'Y_LIQ_KG_PER_KMOLCO', 'FT liquid yield', 'kg FT liquid per kmol CO converted', 'MASS_PER_AMOUNT', 'kg/kmol', true, 'USER'),
  equip('Fischer Tropsch Reactor', 'Y_CO2_PER_CO', 'CO₂ yield per CO', 'CO₂ byproduct yield fraction', 'DIMENSIONLESS', '-', true, 'USER', null, 'Optional byproduct'),
  equip('Fischer Tropsch Reactor', 'Y_CH4_PER_CO', 'CH₄ yield per CO', 'CH₄ byproduct yield fraction', 'DIMENSIONLESS', '-', true, 'USER', null, 'Optional byproduct'),
  equip('Fischer Tropsch Reactor', 'F_CO_CONV_KMOL_H', 'CO converted flow', 'CO consumed by FT reaction', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'SYNTH_YIELD_V1'),
  equip('Fischer Tropsch Reactor', 'F_CO_OUT_KMOL_H', 'CO outlet flow', 'Unreacted CO outlet', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'SYNTH_YIELD_V1'),
  equip('Fischer Tropsch Reactor', 'F_H2_OUT_KMOL_H', 'H₂ outlet flow', 'Unreacted H₂ outlet', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'SYNTH_YIELD_V1'),
  equip('Fischer Tropsch Reactor', 'F_H2O_OUT_KMOL_H', 'H₂O outlet flow', 'H₂O product outlet', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'SYNTH_YIELD_V1'),
  equip('Fischer Tropsch Reactor', 'F_FT_LIQ_KG_H', 'FT liquid flow', 'FT liquid product mass flow', 'MASS_PER_TIME', 'kg/h', false, 'DERIVED', 'SYNTH_YIELD_V1'),
  equip('Fischer Tropsch Reactor', 'F_CO2_OUT_KMOL_H', 'CO₂ outlet flow', 'CO₂ byproduct outlet', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'SYNTH_YIELD_V1', 'Optional'),
  equip('Fischer Tropsch Reactor', 'F_CH4_OUT_KMOL_H', 'CH₄ outlet flow', 'CH₄ byproduct outlet', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'SYNTH_YIELD_V1', 'Optional'),

  // ═══════════════ EQUIPMENT: Polymerization Reactor ═══════════════
  equip('Polymerization Reactor', 'F_MONOMER_IN_KMOL_H', 'Monomer inlet flow', 'Monomer feed molar flow', 'MOLAR_FLOW', 'kmol/h', true, 'USER'),
  equip('Polymerization Reactor', 'X_MONOMER', 'Monomer conversion', 'Monomer conversion fraction', 'DIMENSIONLESS', '-', true, 'USER'),
  equip('Polymerization Reactor', 'MW_MONOMER', 'Monomer molar mass', 'Molecular weight of monomer', 'MASS_PER_AMOUNT', 'kg/kmol', true, 'USER'),
  equip('Polymerization Reactor', 'YIELD_MASS', 'Mass yield', 'Mass yield fraction of polymer', 'DIMENSIONLESS', '-', true, 'USER'),
  equip('Polymerization Reactor', 'F_MONOMER_CONV_KMOL_H', 'Monomer converted flow', 'Monomer consumed by polymerization', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'POLYMERIZATION_V1'),
  equip('Polymerization Reactor', 'F_MONOMER_OUT_KMOL_H', 'Monomer outlet flow', 'Unreacted monomer molar flow', 'MOLAR_FLOW', 'kmol/h', false, 'DERIVED', 'POLYMERIZATION_V1'),
  equip('Polymerization Reactor', 'F_POLYMER_KG_H', 'Polymer product flow', 'Polymer product mass flow', 'MASS_PER_TIME', 'kg/h', false, 'DERIVED', 'POLYMERIZATION_V1'),
] as const;
