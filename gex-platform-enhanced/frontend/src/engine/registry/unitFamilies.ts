/**
 * Unit families registry — all 64 unit family definitions.
 * Pure data, no logic.
 */
import type { UnitFamily, ParameterKeyDef } from '../types';
import { PARAMETER_KEYS } from './parameterKeys';

export const UNIT_FAMILIES: readonly UnitFamily[] = [
  { unitFamily: 'MASS_PER_TIME', canonicalUnit: 'kg/h', allowedUnits: ['kg/h','kg/s','kg/min','kg/day','t/h','t/day','t/year','lb/h','lb/day'], requiresContext: [], notes: 'Mass flow rate' },
  { unitFamily: 'MASS_PER_YEAR', canonicalUnit: 'kg/year', allowedUnits: ['kg/year','t/year','kg/day','t/day','lb/year'], requiresContext: ['days_year'], notes: 'Annual mass throughput' },
  { unitFamily: 'TIME_PER_YEAR', canonicalUnit: 'h/year', allowedUnits: ['h/year','hr/year','days/year'], requiresContext: [], notes: 'Operating hours per year' },
  { unitFamily: 'TIME', canonicalUnit: 's', allowedUnits: ['s','min','h','day','year'], requiresContext: ['year_definition'], notes: 'Duration' },
  { unitFamily: 'MASS', canonicalUnit: 'kg', allowedUnits: ['kg','g','t','tonne','lb'], requiresContext: [], notes: 'Mass' },
  { unitFamily: 'AMOUNT_OF_SUBSTANCE', canonicalUnit: 'kmol', allowedUnits: ['mol','kmol','lbmol'], requiresContext: [], notes: 'Amount of substance' },
  { unitFamily: 'MOLAR_FLOW', canonicalUnit: 'kmol/h', allowedUnits: ['mol/s','mol/min','mol/h','kmol/s','kmol/h','kmol/day'], requiresContext: [], notes: 'Molar flow rate' },
  { unitFamily: 'VOLUMETRIC_FLOW_LIQUID', canonicalUnit: 'm3/h', allowedUnits: ['m3/s','m3/h','m3/day','L/s','L/min','L/h','L/day','gal/min','gal/h','bbl/day'], requiresContext: [], notes: 'Liquid volumetric flow' },
  { unitFamily: 'VOLUMETRIC_FLOW_GAS_ACTUAL', canonicalUnit: 'm3/h', allowedUnits: ['m3/s','m3/h','m3/day','ft3/min','ft3/h'], requiresContext: ['temperature','pressure'], notes: 'Gas volumetric flow at actual conditions' },
  { unitFamily: 'VOLUMETRIC_FLOW_GAS_NORMAL', canonicalUnit: 'Nm3/h', allowedUnits: ['Nm3/h','Nm3/d','Nm3/day','Nm3/y','Nm3/year','Nm3/s'], requiresContext: ['ref_temperature','ref_pressure'], notes: 'Gas volumetric flow at normal conditions' },
  { unitFamily: 'VOLUMETRIC_FLOW_GAS_STANDARD', canonicalUnit: 'Sm3/h', allowedUnits: ['Sm3/h','Sm3/d','Sm3/day','Sm3/y','Sm3/year','Sm3/s'], requiresContext: ['ref_temperature','ref_pressure'], notes: 'Gas volumetric flow at standard conditions' },
  { unitFamily: 'VOLUME', canonicalUnit: 'm3', allowedUnits: ['m3','L','mL','ft3','gal','bbl'], requiresContext: [], notes: 'Volume' },
  { unitFamily: 'DENSITY_MASS', canonicalUnit: 'kg/m3', allowedUnits: ['kg/m3','g/L','g/cm3','t/m3','lb/ft3'], requiresContext: ['temperature','pressure'], notes: 'Mass density' },
  { unitFamily: 'DENSITY_MOLAR', canonicalUnit: 'kmol/m3', allowedUnits: ['mol/m3','kmol/m3'], requiresContext: ['temperature','pressure'], notes: 'Molar density' },
  { unitFamily: 'CONCENTRATION_MASS', canonicalUnit: 'g/L', allowedUnits: ['kg/m3','g/L','mg/L','ug/L','ppm_w','ppb_w'], requiresContext: ['basis_wet_dry'], notes: 'Mass concentration' },
  { unitFamily: 'CONCENTRATION_MOLAR', canonicalUnit: 'mol/L', allowedUnits: ['mol/L','mol/m3','kmol/m3','ppmv','ppbv'], requiresContext: ['temperature','pressure','basis_wet_dry'], notes: 'Molar concentration' },
  { unitFamily: 'MASS_FRACTION', canonicalUnit: '1', allowedUnits: ['wt%','mass%','fraction'], requiresContext: [], notes: 'Mass fraction (dimensionless)' },
  { unitFamily: 'MOLE_FRACTION', canonicalUnit: '1', allowedUnits: ['mol%','vol%','fraction'], requiresContext: ['basis_wet_dry'], notes: 'Mole fraction (dimensionless)' },
  { unitFamily: 'VOLUME_FRACTION', canonicalUnit: '1', allowedUnits: ['vol%','fraction'], requiresContext: ['basis_wet_dry','temperature','pressure'], notes: 'Volume fraction (dimensionless)' },
  { unitFamily: 'PURITY', canonicalUnit: '1', allowedUnits: ['%','fraction'], requiresContext: ['basis_wet_dry'], notes: 'Purity fraction' },
  { unitFamily: 'TEMPERATURE', canonicalUnit: 'K', allowedUnits: ['K','C','°C','F','°F'], requiresContext: [], notes: 'Absolute temperature' },
  { unitFamily: 'PRESSURE_ABSOLUTE', canonicalUnit: 'bar_a', allowedUnits: ['bar(a)','bara','kPa(a)','MPa(a)','Pa(a)','atm','psi(a)'], requiresContext: [], notes: 'Absolute pressure' },
  { unitFamily: 'PRESSURE_GAUGE', canonicalUnit: 'bar_g', allowedUnits: ['barg','bar(g)','kPa(g)','psi(g)'], requiresContext: ['ambient_pressure'], notes: 'Gauge pressure' },
  { unitFamily: 'PRESSURE_DROP', canonicalUnit: 'kPa', allowedUnits: ['Pa','kPa','bar','psi'], requiresContext: [], notes: 'Pressure drop' },
  { unitFamily: 'POWER', canonicalUnit: 'kW', allowedUnits: ['W','kW','MW','GW','hp'], requiresContext: [], notes: 'Power' },
  { unitFamily: 'ENERGY', canonicalUnit: 'kWh', allowedUnits: ['J','kJ','MJ','GJ','kWh','MWh','GWh','BTU'], requiresContext: [], notes: 'Energy' },
  { unitFamily: 'ENERGY_PER_TIME_HEAT_DUTY', canonicalUnit: 'kW', allowedUnits: ['W','kW','MW','GW'], requiresContext: [], notes: 'Heat duty (power equivalent)' },
  { unitFamily: 'ENERGY_PER_MASS', canonicalUnit: 'kWh/kg', allowedUnits: ['kWh/kg','MJ/kg','GJ/t','MWh/t','BTU/lb'], requiresContext: ['lhv_hhv','basis_wet_dry'], notes: 'Specific energy per unit mass' },
  { unitFamily: 'ENERGY_PER_VOLUME', canonicalUnit: 'kWh/m3', allowedUnits: ['kWh/m3','MJ/m3','GJ/Nm3','MJ/Nm3','kWh/Nm3','BTU/scf'], requiresContext: ['ref_temperature','ref_pressure','lhv_hhv','basis_wet_dry'], notes: 'Specific energy per unit volume' },
  { unitFamily: 'SPECIFIC_POWER', canonicalUnit: 'kW/(kg/h)', allowedUnits: ['kW/(kg/h)','kWh/kg'], requiresContext: [], notes: 'Specific electrical consumption' },
  { unitFamily: 'EFFICIENCY', canonicalUnit: '1', allowedUnits: ['%','fraction'], requiresContext: [], notes: 'Efficiency (dimensionless)' },
  { unitFamily: 'CAPACITY_FACTOR', canonicalUnit: '1', allowedUnits: ['%','fraction','h/year'], requiresContext: ['hours_per_year'], notes: 'Capacity factor' },
  { unitFamily: 'HEAT_TRANSFER_COEFF', canonicalUnit: 'W/m2/K', allowedUnits: ['W/m2/K','kW/m2/K','BTU/h/ft2/F'], requiresContext: [], notes: 'Heat transfer coefficient' },
  { unitFamily: 'AREA', canonicalUnit: 'm2', allowedUnits: ['m2','cm2','mm2','ft2'], requiresContext: [], notes: 'Area' },
  { unitFamily: 'LENGTH', canonicalUnit: 'm', allowedUnits: ['m','cm','mm','km','in','ft'], requiresContext: [], notes: 'Length' },
  { unitFamily: 'DIAMETER', canonicalUnit: 'mm', allowedUnits: ['mm','cm','m','in','ft'], requiresContext: [], notes: 'Diameter' },
  { unitFamily: 'VELOCITY', canonicalUnit: 'm/s', allowedUnits: ['m/s','ft/s','km/h'], requiresContext: [], notes: 'Velocity' },
  { unitFamily: 'VISCOSITY_DYNAMIC', canonicalUnit: 'Pa*s', allowedUnits: ['Pa*s','mPa*s','cP'], requiresContext: ['temperature'], notes: 'Dynamic viscosity' },
  { unitFamily: 'VISCOSITY_KINEMATIC', canonicalUnit: 'm2/s', allowedUnits: ['m2/s','cSt','St'], requiresContext: ['temperature'], notes: 'Kinematic viscosity' },
  { unitFamily: 'THERMAL_CONDUCTIVITY', canonicalUnit: 'W/m/K', allowedUnits: ['W/m/K','BTU/h/ft/F'], requiresContext: ['temperature'], notes: 'Thermal conductivity' },
  { unitFamily: 'HEAT_CAPACITY_MASS', canonicalUnit: 'kJ/kg/K', allowedUnits: ['J/kg/K','kJ/kg/K'], requiresContext: ['temperature'], notes: 'Specific heat capacity' },
  { unitFamily: 'ENTHALPY_MASS', canonicalUnit: 'kJ/kg', allowedUnits: ['J/kg','kJ/kg','MJ/kg'], requiresContext: ['temperature','reference_state'], notes: 'Mass-specific enthalpy' },
  { unitFamily: 'ENTHALPY_MOLAR', canonicalUnit: 'kJ/mol', allowedUnits: ['J/mol','kJ/mol','kJ/kmol'], requiresContext: ['temperature','reference_state'], notes: 'Molar enthalpy' },
  { unitFamily: 'GHG_MASS', canonicalUnit: 'kgCO2e', allowedUnits: ['kgCO2e','tCO2e','gCO2e'], requiresContext: ['gwp_version'], notes: 'GHG mass' },
  { unitFamily: 'GHG_RATE', canonicalUnit: 'kgCO2e/h', allowedUnits: ['kgCO2e/s','kgCO2e/h','tCO2e/day','tCO2e/year'], requiresContext: ['days_year'], notes: 'GHG emission rate' },
  { unitFamily: 'EMISSION_FACTOR_ENERGY', canonicalUnit: 'gCO2e/kWh', allowedUnits: ['gCO2e/kWh','kgCO2e/MWh','kgCO2e/GJ'], requiresContext: ['gwp_version'], notes: 'Emission factor per energy' },
  { unitFamily: 'EMISSION_FACTOR_MASS', canonicalUnit: 'kgCO2e/kg', allowedUnits: ['gCO2e/MJ','kgCO2e/t','kgCO2e/kg'], requiresContext: ['gwp_version','lhv_hhv'], notes: 'Emission factor per mass' },
  { unitFamily: 'CARBON_INTENSITY_ENERGY', canonicalUnit: 'gCO2e/MJ', allowedUnits: ['gCO2e/MJ','gCO2e/MJ_LHV','gCO2e/MJ_HHV','kgCO2e/GJ'], requiresContext: ['gwp_version','lhv_hhv'], notes: 'Carbon intensity per energy' },
  { unitFamily: 'WATER_USAGE_FACTOR', canonicalUnit: 'L/kg', allowedUnits: ['L/kg','m3/t','kg/kg'], requiresContext: ['basis_wet_dry'], notes: 'Water usage per unit mass product' },
  { unitFamily: 'COST', canonicalUnit: 'EUR', allowedUnits: ['EUR','USD','GBP','HUF','CHF'], requiresContext: ['fx_rate','price_year'], notes: 'Absolute cost' },
  { unitFamily: 'COST_PER_ENERGY', canonicalUnit: 'EUR/MWh', allowedUnits: ['EUR/MWh','EUR/kWh','USD/MWh','EUR/GJ','EUR/MMBtu'], requiresContext: ['fx_rate','price_year'], notes: 'Specific cost per energy' },
  { unitFamily: 'COST_PER_MASS', canonicalUnit: 'EUR/t', allowedUnits: ['EUR/kg','EUR/t','USD/t','USD/kg'], requiresContext: ['fx_rate','price_year'], notes: 'Specific cost per mass' },
  { unitFamily: 'CAPEX', canonicalUnit: 'EUR', allowedUnits: ['EUR','USD','GBP','HUF'], requiresContext: ['fx_rate','price_year'], notes: 'Capital expenditure' },
  { unitFamily: 'OPEX_PER_YEAR', canonicalUnit: 'EUR/year', allowedUnits: ['EUR/year','EUR/a','USD/year'], requiresContext: ['fx_rate','price_year'], notes: 'Annual operating expenditure' },
  { unitFamily: 'DISCOUNT_RATE', canonicalUnit: '1', allowedUnits: ['%','fraction'], requiresContext: [], notes: 'Discount rate' },
  { unitFamily: 'INTEREST_RATE', canonicalUnit: '1', allowedUnits: ['%','fraction'], requiresContext: [], notes: 'Interest rate' },
  { unitFamily: 'EXCHANGE_RATE', canonicalUnit: '1', allowedUnits: ['USD/EUR','EUR/USD','GBP/EUR'], requiresContext: [], notes: 'Currency exchange rate' },
  { unitFamily: 'LIFETIME', canonicalUnit: 'year', allowedUnits: ['year','years','h','month'], requiresContext: ['hours_per_year'], notes: 'Equipment or project lifetime' },
  { unitFamily: 'AVAILABILITY', canonicalUnit: '1', allowedUnits: ['%','fraction'], requiresContext: [], notes: 'Availability factor' },
  { unitFamily: 'PRODUCTION', canonicalUnit: 't/year', allowedUnits: ['kg/h','kg/day','t/day','t/year','Nm3/h','Nm3/d','Nm3/day','Nm3/year'], requiresContext: ['ref_temperature','ref_pressure','days_year'], notes: 'Production rate' },
  { unitFamily: 'MASS_PER_AMOUNT', canonicalUnit: 'kg/kmol', allowedUnits: ['kg/kmol','g/mol','kg/mol'], requiresContext: [], notes: 'Molar mass' },
  { unitFamily: 'VOLUMETRIC_FLOW_SI', canonicalUnit: 'm3/s', allowedUnits: ['m3/s','m3/h','m3/day','L/s','L/min','L/h','ft3/s','ft3/min'], requiresContext: [], notes: 'Volumetric flow (SI)' },
  { unitFamily: 'DIMENSIONLESS', canonicalUnit: '-', allowedUnits: ['-'], requiresContext: [], notes: 'Dimensionless quantity' },
  { unitFamily: 'DIMENSIONLESS_INDEX', canonicalUnit: '(none)', allowedUnits: ['(none)'], requiresContext: [], notes: 'Dimensionless index' },
  { unitFamily: 'ACID_NUMBER', canonicalUnit: 'mg KOH/g', allowedUnits: ['mg KOH/g','mg KOH/kg'], requiresContext: [], notes: 'Acid number' },
] as const;

export function getUnitFamily(familyName: string): UnitFamily | undefined {
  return UNIT_FAMILIES.find(f => f.unitFamily === familyName);
}

export function getParameterDef(paramKey: string, scopeId?: string): ParameterKeyDef | undefined {
  if (scopeId) {
    const exact = PARAMETER_KEYS.find(p => p.paramKey === paramKey && p.scopeId === scopeId);
    if (exact) return exact;
  }
  return PARAMETER_KEYS.find(p => p.paramKey === paramKey && p.scopeId === '*');
}
