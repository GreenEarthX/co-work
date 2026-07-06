/**
 * Default library — all 21 default parameter values for archetypes.
 * Pure data, no logic.
 */
import type { DefaultLibraryEntry } from '../types';

export const DEFAULT_LIBRARY: readonly DefaultLibraryEntry[] = [
  // ELECTROLYSIS_UNIT
  { archetypeId: 'ELECTROLYSIS_UNIT', paramKey: 'SEC_ELEC_H2', defaultValue: 52, unit: 'kWh/kg', source: 'IRENA 2024 / IEA GHR 2023', basisNotes: 'PEM stack system-level SEC including auxiliaries', confidence: 'MED', notes: 'Range 48–58 kWh/kg depending on technology and scale' },
  { archetypeId: 'ELECTROLYSIS_UNIT', paramKey: 'P_BASE', defaultValue: 150, unit: 'kW', source: 'Engineering estimate', basisNotes: 'BOP base load: cooling pumps, controls, N₂ purge', confidence: 'LOW', notes: 'Highly plant-specific' },
  { archetypeId: 'ELECTROLYSIS_UNIT', paramKey: 'WATER_FACTOR', defaultValue: 1.05, unit: '-', source: 'Nel / thyssenkrupp data sheets', basisNotes: 'Stoichiometric water × 1.05 for losses and cooling makeup', confidence: 'MED', notes: 'Stoichiometric = 9 kg H₂O per kg H₂' },

  // COOLING_SYSTEM
  { archetypeId: 'COOLING_SYSTEM', paramKey: 'COP_COOL', defaultValue: 3.5, unit: '-', source: 'ASHRAE Handbook', basisNotes: 'Typical COP for industrial chiller at 7°C supply', confidence: 'MED', notes: 'Range 2.5–5.0 depending on ambient and technology' },

  // STEAM_SYSTEM
  { archetypeId: 'STEAM_SYSTEM', paramKey: 'DELTAH_STEAM', defaultValue: 0.75, unit: 'kWh/kg', source: 'Steam tables (saturated 10 bar)', basisNotes: 'Enthalpy rise from 105°C feedwater to 180°C saturated steam', confidence: 'MED', notes: '~2700 kJ/kg ≈ 0.75 kWh/kg' },

  // THERMAL_HEATER
  { archetypeId: 'THERMAL_HEATER', paramKey: 'EFF_TH', defaultValue: 0.85, unit: '-', source: 'API 560 / industrial practice', basisNotes: 'Fired heater thermal efficiency (LHV basis)', confidence: 'HIGH', notes: 'Range 0.80–0.92 for modern gas-fired heaters' },
  { archetypeId: 'THERMAL_HEATER', paramKey: 'LHV_FUEL', defaultValue: 13.9, unit: 'kWh/kg', source: 'Natural gas (methane) standard', basisNotes: 'CH₄ LHV = 50.0 MJ/kg = 13.9 kWh/kg', confidence: 'HIGH', notes: 'Adjust for H₂ (33.3 kWh/kg) or other fuels' },

  // COMPRESSOR_GAS
  { archetypeId: 'COMPRESSOR_GAS', paramKey: 'SEC_ELEC', defaultValue: 0.18, unit: 'kWh/kg', source: 'Siemens Energy / Atlas Copco', basisNotes: 'Multi-stage reciprocating compressor, 30→350 bar H₂', confidence: 'MED', notes: 'Range 0.12–0.30 depending on pressure ratio and gas' },

  // PUMP_LIQUID
  { archetypeId: 'PUMP_LIQUID', paramKey: 'ETA_PUMP', defaultValue: 0.7, unit: '-', source: 'Hydraulic Institute standards', basisNotes: 'Combined pump + motor efficiency', confidence: 'MED', notes: 'Range 0.60–0.85 depending on pump type and size' },

  // METHANATION_REACTOR
  { archetypeId: 'METHANATION_REACTOR', paramKey: 'X_CO', defaultValue: 0.85, unit: '-', source: 'Haldor Topsøe / literature', basisNotes: 'Single-pass CO conversion in fixed-bed methanation', confidence: 'MED', notes: 'Multi-stage can achieve >95% overall' },
  { archetypeId: 'METHANATION_REACTOR', paramKey: 'X_CO2', defaultValue: 0.75, unit: '-', source: 'Haldor Topsøe / literature', basisNotes: 'Single-pass CO₂ conversion via Sabatier reaction', confidence: 'MED', notes: 'Lower than CO due to thermodynamic equilibrium' },

  // METHANOL_SYNTHESIS_REACTOR
  { archetypeId: 'METHANOL_SYNTHESIS_REACTOR', paramKey: 'X_CO', defaultValue: 0.2, unit: '-', source: 'Johnson Matthey / Lurgi data', basisNotes: 'Single-pass CO conversion at 50–80 bar, 230–270°C', confidence: 'MED', notes: 'Low per-pass, high with recycle loop' },
  { archetypeId: 'METHANOL_SYNTHESIS_REACTOR', paramKey: 'X_CO2', defaultValue: 0.15, unit: '-', source: 'Johnson Matthey / Lurgi data', basisNotes: 'Single-pass CO₂ conversion', confidence: 'MED', notes: 'CO₂-to-MeOH pathway less favoured kinetically' },

  // AMMONIA_SYNTHESIS_REACTOR
  { archetypeId: 'AMMONIA_SYNTHESIS_REACTOR', paramKey: 'X_N2', defaultValue: 0.15, unit: '-', source: 'KBR / Haldor Topsøe', basisNotes: 'Single-pass N₂ conversion at 150–250 bar, 400–500°C', confidence: 'HIGH', notes: 'Well-established Haber-Bosch equilibrium data' },

  // HABER_BOSCH_LOOP_SKID
  { archetypeId: 'HABER_BOSCH_LOOP_SKID', paramKey: 'PURGE_FRAC', defaultValue: 0.03, unit: '-', source: 'KBR / Uhde design practice', basisNotes: 'Fraction of recycle purged to prevent inert buildup', confidence: 'MED', notes: 'Range 0.02–0.05 depending on feed purity' },

  // FISCHER_TROPSCH_REACTOR
  { archetypeId: 'FISCHER_TROPSCH_REACTOR', paramKey: 'X_CO', defaultValue: 0.7, unit: '-', source: 'Sasol / Shell SMDS data', basisNotes: 'Single-pass CO conversion in slurry or fixed-bed FT', confidence: 'MED', notes: 'Range 0.5–0.85 depending on reactor type' },
  { archetypeId: 'FISCHER_TROPSCH_REACTOR', paramKey: 'R_H2_CO', defaultValue: 2.1, unit: '-', source: 'FT stoichiometry (cobalt catalyst)', basisNotes: 'H₂/CO usage ratio for cobalt-based low-temp FT', confidence: 'MED', notes: 'Iron catalyst typically ~1.7' },
  { archetypeId: 'FISCHER_TROPSCH_REACTOR', paramKey: 'Y_LIQ_KG_PER_KMOLCO', defaultValue: 85, unit: 'kg/kmol', source: 'Shell SMDS yield data', basisNotes: 'kg of C5+ liquid per kmol CO converted', confidence: 'MED', notes: 'Depends on chain growth probability (alpha)' },
  { archetypeId: 'FISCHER_TROPSCH_REACTOR', paramKey: 'Y_CO2_PER_CO', defaultValue: 0.05, unit: '-', source: 'Literature / Sasol', basisNotes: 'CO₂ byproduct yield as fraction of CO converted', confidence: 'LOW', notes: 'Higher for iron catalyst (~0.3 via WGS)' },
  { archetypeId: 'FISCHER_TROPSCH_REACTOR', paramKey: 'Y_CH4_PER_CO', defaultValue: 0.07, unit: '-', source: 'Literature / Sasol', basisNotes: 'CH₄ byproduct yield as fraction of CO converted', confidence: 'LOW', notes: 'Undesirable, minimized by catalyst and temp control' },

  // POLYMERIZATION_REACTOR
  { archetypeId: 'POLYMERIZATION_REACTOR', paramKey: 'YIELD_MASS', defaultValue: 0.98, unit: '-', source: 'Borealis / LyondellBasell data', basisNotes: 'Mass yield fraction: polymer out / monomer consumed', confidence: 'HIGH', notes: 'Very high for modern Ziegler-Natta or metallocene catalysts' },
] as const;
