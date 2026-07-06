/**
 * Scalar conversion factor registry for all unit families.
 * Pure data — no side effects, no state.
 */

export type ConversionFn = (value: number) => number;

export interface ConversionEntry {
  readonly from: string;
  readonly to: string;
  readonly convert: ConversionFn;
}

const identity: ConversionFn = v => v;

/* ── helper to build entries ── */
function linear(from: string, to: string, factor: number): ConversionEntry {
  return { from, to, convert: v => v * factor };
}

function offset(from: string, to: string, fn: ConversionFn): ConversionEntry {
  return { from, to, convert: fn };
}

/* ══════════════════════════════════════════════
   Conversion entries grouped by unit family
   ══════════════════════════════════════════════ */

const MASS_PER_TIME: ConversionEntry[] = [
  { from: 'kg/h', to: 'kg/h', convert: identity },
  linear('kg/s', 'kg/h', 3600),
  linear('kg/min', 'kg/h', 60),
  linear('kg/day', 'kg/h', 1 / 24),
  linear('t/h', 'kg/h', 1000),
  linear('t/day', 'kg/h', 1000 / 24),
  linear('t/year', 'kg/h', 1000 / 8760),
  linear('lb/h', 'kg/h', 0.453592),
  linear('lb/day', 'kg/h', 0.453592 / 24),
];

const MASS_PER_YEAR: ConversionEntry[] = [
  { from: 'kg/year', to: 'kg/year', convert: identity },
  linear('t/year', 'kg/year', 1000),
  linear('kg/day', 'kg/year', 365),
  linear('t/day', 'kg/year', 365000),
  linear('lb/year', 'kg/year', 0.453592),
];

const TIME_PER_YEAR: ConversionEntry[] = [
  { from: 'h/year', to: 'h/year', convert: identity },
  linear('hr/year', 'h/year', 1),
  linear('days/year', 'h/year', 24),
];

const TIME: ConversionEntry[] = [
  { from: 's', to: 's', convert: identity },
  linear('min', 's', 60),
  linear('h', 's', 3600),
  linear('day', 's', 86400),
  linear('year', 's', 31536000),
];

const MASS: ConversionEntry[] = [
  { from: 'kg', to: 'kg', convert: identity },
  linear('g', 'kg', 0.001),
  linear('t', 'kg', 1000),
  linear('tonne', 'kg', 1000),
  linear('lb', 'kg', 0.453592),
];

const AMOUNT_OF_SUBSTANCE: ConversionEntry[] = [
  { from: 'kmol', to: 'kmol', convert: identity },
  linear('mol', 'kmol', 0.001),
  linear('lbmol', 'kmol', 0.453592),
];

const MOLAR_FLOW: ConversionEntry[] = [
  { from: 'kmol/h', to: 'kmol/h', convert: identity },
  linear('mol/s', 'kmol/h', 3.6),
  linear('mol/min', 'kmol/h', 0.06),
  linear('mol/h', 'kmol/h', 0.001),
  linear('kmol/s', 'kmol/h', 3600),
  linear('kmol/day', 'kmol/h', 1 / 24),
];

const VOLUMETRIC_FLOW_LIQUID: ConversionEntry[] = [
  { from: 'm3/h', to: 'm3/h', convert: identity },
  linear('m3/s', 'm3/h', 3600),
  linear('m3/day', 'm3/h', 1 / 24),
  linear('L/s', 'm3/h', 3.6),
  linear('L/min', 'm3/h', 0.06),
  linear('L/h', 'm3/h', 0.001),
  linear('L/day', 'm3/h', 1 / 24000),
  linear('gal/min', 'm3/h', 0.227125),
  linear('gal/h', 'm3/h', 0.00378541),
  linear('bbl/day', 'm3/h', 0.158987 / 24),
];

const VOLUMETRIC_FLOW_SI: ConversionEntry[] = [
  { from: 'm3/s', to: 'm3/s', convert: identity },
  linear('m3/h', 'm3/s', 1 / 3600),
  linear('m3/day', 'm3/s', 1 / 86400),
  linear('L/s', 'm3/s', 0.001),
  linear('L/min', 'm3/s', 1 / 60000),
  linear('L/h', 'm3/s', 1 / 3600000),
  linear('ft3/s', 'm3/s', 0.0283168),
  linear('ft3/min', 'm3/s', 0.0283168 / 60),
];

const VOLUME: ConversionEntry[] = [
  { from: 'm3', to: 'm3', convert: identity },
  linear('L', 'm3', 0.001),
  linear('mL', 'm3', 1e-6),
  linear('ft3', 'm3', 0.0283168),
  linear('gal', 'm3', 0.00378541),
  linear('bbl', 'm3', 0.158987),
];

const TEMPERATURE: ConversionEntry[] = [
  { from: 'K', to: 'K', convert: identity },
  offset('C', 'K', v => v + 273.15),
  offset('°C', 'K', v => v + 273.15),
  offset('F', 'K', v => (v - 32) * 5 / 9 + 273.15),
  offset('°F', 'K', v => (v - 32) * 5 / 9 + 273.15),
];

const PRESSURE_ABSOLUTE: ConversionEntry[] = [
  { from: 'bar_a', to: 'bar_a', convert: identity },
  linear('bara', 'bar_a', 1),
  linear('bar(a)', 'bar_a', 1),
  linear('kPa(a)', 'bar_a', 0.01),
  linear('MPa(a)', 'bar_a', 10),
  linear('Pa(a)', 'bar_a', 1e-5),
  linear('atm', 'bar_a', 1.01325),
  linear('psi(a)', 'bar_a', 0.0689476),
];

const PRESSURE_GAUGE: ConversionEntry[] = [
  { from: 'bar_g', to: 'bar_g', convert: identity },
  linear('barg', 'bar_g', 1),
  linear('bar(g)', 'bar_g', 1),
  linear('kPa(g)', 'bar_g', 0.01),
  linear('psi(g)', 'bar_g', 0.0689476),
];

const PRESSURE_DROP: ConversionEntry[] = [
  { from: 'kPa', to: 'kPa', convert: identity },
  linear('Pa', 'kPa', 0.001),
  linear('bar', 'kPa', 100),
  linear('psi', 'kPa', 6.89476),
];

const POWER: ConversionEntry[] = [
  { from: 'kW', to: 'kW', convert: identity },
  linear('W', 'kW', 0.001),
  linear('MW', 'kW', 1000),
  linear('GW', 'kW', 1e6),
  linear('hp', 'kW', 0.7457),
];

const ENERGY: ConversionEntry[] = [
  { from: 'kWh', to: 'kWh', convert: identity },
  linear('J', 'kWh', 1 / 3.6e6),
  linear('kJ', 'kWh', 1 / 3600),
  linear('MJ', 'kWh', 1 / 3.6),
  linear('GJ', 'kWh', 1 / 0.0036),
  linear('MWh', 'kWh', 1000),
  linear('GWh', 'kWh', 1e6),
  linear('BTU', 'kWh', 0.000293071),
];

const ENERGY_PER_TIME_HEAT_DUTY: ConversionEntry[] = [
  { from: 'kW', to: 'kW', convert: identity },
  linear('W', 'kW', 0.001),
  linear('MW', 'kW', 1000),
  linear('GW', 'kW', 1e6),
];

const ENERGY_PER_MASS: ConversionEntry[] = [
  { from: 'kWh/kg', to: 'kWh/kg', convert: identity },
  linear('MJ/kg', 'kWh/kg', 1 / 3.6),
  linear('GJ/t', 'kWh/kg', 1 / 3.6),
  linear('MWh/t', 'kWh/kg', 1),
  linear('BTU/lb', 'kWh/kg', 0.000646112),
];

const SPECIFIC_POWER: ConversionEntry[] = [
  { from: 'kW/(kg/h)', to: 'kW/(kg/h)', convert: identity },
  linear('kWh/kg', 'kW/(kg/h)', 1),
];

const EFFICIENCY: ConversionEntry[] = [
  { from: '1', to: '1', convert: identity },
  linear('%', '1', 0.01),
  linear('fraction', '1', 1),
];

const CAPACITY_FACTOR: ConversionEntry[] = [
  { from: '1', to: '1', convert: identity },
  linear('%', '1', 0.01),
  linear('fraction', '1', 1),
  linear('h/year', '1', 1 / 8760),
];

const MASS_FRACTION: ConversionEntry[] = [
  { from: '1', to: '1', convert: identity },
  linear('wt%', '1', 0.01),
  linear('mass%', '1', 0.01),
  linear('fraction', '1', 1),
];

const MOLE_FRACTION: ConversionEntry[] = [
  { from: '1', to: '1', convert: identity },
  linear('mol%', '1', 0.01),
  linear('vol%', '1', 0.01),
  linear('fraction', '1', 1),
];

const VOLUME_FRACTION: ConversionEntry[] = [
  { from: '1', to: '1', convert: identity },
  linear('vol%', '1', 0.01),
  linear('fraction', '1', 1),
];

const PURITY: ConversionEntry[] = [
  { from: '1', to: '1', convert: identity },
  linear('%', '1', 0.01),
  linear('fraction', '1', 1),
];

const DISCOUNT_RATE: ConversionEntry[] = [
  { from: '1', to: '1', convert: identity },
  linear('%', '1', 0.01),
  linear('fraction', '1', 1),
];

const INTEREST_RATE: ConversionEntry[] = [
  { from: '1', to: '1', convert: identity },
  linear('%', '1', 0.01),
  linear('fraction', '1', 1),
];

const AVAILABILITY: ConversionEntry[] = [
  { from: '1', to: '1', convert: identity },
  linear('%', '1', 0.01),
  linear('fraction', '1', 1),
];

const HEAT_TRANSFER_COEFF: ConversionEntry[] = [
  { from: 'W/m2/K', to: 'W/m2/K', convert: identity },
  linear('kW/m2/K', 'W/m2/K', 1000),
  linear('BTU/h/ft2/F', 'W/m2/K', 5.67826),
];

const AREA: ConversionEntry[] = [
  { from: 'm2', to: 'm2', convert: identity },
  linear('cm2', 'm2', 1e-4),
  linear('mm2', 'm2', 1e-6),
  linear('ft2', 'm2', 0.092903),
];

const LENGTH: ConversionEntry[] = [
  { from: 'm', to: 'm', convert: identity },
  linear('cm', 'm', 0.01),
  linear('mm', 'm', 0.001),
  linear('km', 'm', 1000),
  linear('in', 'm', 0.0254),
  linear('ft', 'm', 0.3048),
];

const DIAMETER: ConversionEntry[] = [
  { from: 'mm', to: 'mm', convert: identity },
  linear('cm', 'mm', 10),
  linear('m', 'mm', 1000),
  linear('in', 'mm', 25.4),
  linear('ft', 'mm', 304.8),
];

const VELOCITY: ConversionEntry[] = [
  { from: 'm/s', to: 'm/s', convert: identity },
  linear('ft/s', 'm/s', 0.3048),
  linear('km/h', 'm/s', 1 / 3.6),
];

const GHG_MASS: ConversionEntry[] = [
  { from: 'kgCO2e', to: 'kgCO2e', convert: identity },
  linear('tCO2e', 'kgCO2e', 1000),
  linear('gCO2e', 'kgCO2e', 0.001),
];

const GHG_RATE: ConversionEntry[] = [
  { from: 'kgCO2e/h', to: 'kgCO2e/h', convert: identity },
  linear('kgCO2e/s', 'kgCO2e/h', 3600),
  linear('tCO2e/day', 'kgCO2e/h', 1000 / 24),
  linear('tCO2e/year', 'kgCO2e/h', 1000 / 8760),
];

const EMISSION_FACTOR_ENERGY: ConversionEntry[] = [
  { from: 'gCO2e/kWh', to: 'gCO2e/kWh', convert: identity },
  linear('kgCO2e/MWh', 'gCO2e/kWh', 1),
  linear('kgCO2e/GJ', 'gCO2e/kWh', 3.6),
];

const EMISSION_FACTOR_MASS: ConversionEntry[] = [
  { from: 'kgCO2e/kg', to: 'kgCO2e/kg', convert: identity },
  linear('gCO2e/MJ', 'kgCO2e/kg', 0.001 * 3.6), // context-dependent but scalar approx
  linear('kgCO2e/t', 'kgCO2e/kg', 0.001),
];

const CARBON_INTENSITY_ENERGY: ConversionEntry[] = [
  { from: 'gCO2e/MJ', to: 'gCO2e/MJ', convert: identity },
  linear('gCO2e/MJ_LHV', 'gCO2e/MJ', 1),
  linear('gCO2e/MJ_HHV', 'gCO2e/MJ', 1), // basis flag, not a scalar difference
  linear('kgCO2e/GJ', 'gCO2e/MJ', 1),
];

const WATER_USAGE_FACTOR: ConversionEntry[] = [
  { from: 'L/kg', to: 'L/kg', convert: identity },
  linear('m3/t', 'L/kg', 1),
  linear('kg/kg', 'L/kg', 1), // water density ≈ 1 kg/L
];

const COST: ConversionEntry[] = [
  { from: 'EUR', to: 'EUR', convert: identity },
  // Cross-currency needs fx_rate context; identity placeholders for same-currency aliases
  linear('USD', 'EUR', 1),   // placeholder, real conversion requires fx_rate context
  linear('GBP', 'EUR', 1),
  linear('HUF', 'EUR', 1),
  linear('CHF', 'EUR', 1),
];

const COST_PER_ENERGY: ConversionEntry[] = [
  { from: 'EUR/MWh', to: 'EUR/MWh', convert: identity },
  linear('EUR/kWh', 'EUR/MWh', 1000),
  linear('USD/MWh', 'EUR/MWh', 1),
  linear('EUR/GJ', 'EUR/MWh', 3.6),
  linear('EUR/MMBtu', 'EUR/MWh', 3.412),
];

const COST_PER_MASS: ConversionEntry[] = [
  { from: 'EUR/t', to: 'EUR/t', convert: identity },
  linear('EUR/kg', 'EUR/t', 1000),
  linear('USD/t', 'EUR/t', 1),
  linear('USD/kg', 'EUR/t', 1000),
];

const CAPEX: ConversionEntry[] = [
  { from: 'EUR', to: 'EUR', convert: identity },
  linear('USD', 'EUR', 1),
  linear('GBP', 'EUR', 1),
  linear('HUF', 'EUR', 1),
];

const OPEX_PER_YEAR: ConversionEntry[] = [
  { from: 'EUR/year', to: 'EUR/year', convert: identity },
  linear('EUR/a', 'EUR/year', 1),
  linear('USD/year', 'EUR/year', 1),
];

const EXCHANGE_RATE: ConversionEntry[] = [
  { from: '1', to: '1', convert: identity },
  linear('USD/EUR', '1', 1),
  linear('EUR/USD', '1', 1),
  linear('GBP/EUR', '1', 1),
];

const LIFETIME: ConversionEntry[] = [
  { from: 'year', to: 'year', convert: identity },
  linear('years', 'year', 1),
  linear('h', 'year', 1 / 8760),
  linear('month', 'year', 1 / 12),
];

const PRODUCTION: ConversionEntry[] = [
  { from: 't/year', to: 't/year', convert: identity },
  linear('kg/h', 't/year', 8.76),       // kg/h × 8760 h / 1000
  linear('kg/day', 't/year', 0.365),     // kg/day × 365 / 1000
  linear('t/day', 't/year', 365),
  // Nm3 conversions require ref conditions — context-dependent
];

const MASS_PER_AMOUNT: ConversionEntry[] = [
  { from: 'kg/kmol', to: 'kg/kmol', convert: identity },
  linear('g/mol', 'kg/kmol', 1),
  linear('kg/mol', 'kg/kmol', 1000),
];

const HEAT_CAPACITY_MASS: ConversionEntry[] = [
  { from: 'kJ/kg/K', to: 'kJ/kg/K', convert: identity },
  linear('J/kg/K', 'kJ/kg/K', 0.001),
];

const ENTHALPY_MASS: ConversionEntry[] = [
  { from: 'kJ/kg', to: 'kJ/kg', convert: identity },
  linear('J/kg', 'kJ/kg', 0.001),
  linear('MJ/kg', 'kJ/kg', 1000),
];

const ENTHALPY_MOLAR: ConversionEntry[] = [
  { from: 'kJ/mol', to: 'kJ/mol', convert: identity },
  linear('J/mol', 'kJ/mol', 0.001),
  linear('kJ/kmol', 'kJ/mol', 0.001),
];

const DIMENSIONLESS: ConversionEntry[] = [
  { from: '-', to: '-', convert: identity },
];

const DIMENSIONLESS_INDEX: ConversionEntry[] = [
  { from: '(none)', to: '(none)', convert: identity },
];

const ACID_NUMBER: ConversionEntry[] = [
  { from: 'mg KOH/g', to: 'mg KOH/g', convert: identity },
  linear('mg KOH/kg', 'mg KOH/g', 0.001),
];

/* ── Build the master map ── */

const familyEntries: [string, ConversionEntry[]][] = [
  ['MASS_PER_TIME', MASS_PER_TIME],
  ['MASS_PER_YEAR', MASS_PER_YEAR],
  ['TIME_PER_YEAR', TIME_PER_YEAR],
  ['TIME', TIME],
  ['MASS', MASS],
  ['AMOUNT_OF_SUBSTANCE', AMOUNT_OF_SUBSTANCE],
  ['MOLAR_FLOW', MOLAR_FLOW],
  ['VOLUMETRIC_FLOW_LIQUID', VOLUMETRIC_FLOW_LIQUID],
  ['VOLUMETRIC_FLOW_SI', VOLUMETRIC_FLOW_SI],
  ['VOLUME', VOLUME],
  ['TEMPERATURE', TEMPERATURE],
  ['PRESSURE_ABSOLUTE', PRESSURE_ABSOLUTE],
  ['PRESSURE_GAUGE', PRESSURE_GAUGE],
  ['PRESSURE_DROP', PRESSURE_DROP],
  ['POWER', POWER],
  ['ENERGY', ENERGY],
  ['ENERGY_PER_TIME_HEAT_DUTY', ENERGY_PER_TIME_HEAT_DUTY],
  ['ENERGY_PER_MASS', ENERGY_PER_MASS],
  ['SPECIFIC_POWER', SPECIFIC_POWER],
  ['EFFICIENCY', EFFICIENCY],
  ['CAPACITY_FACTOR', CAPACITY_FACTOR],
  ['MASS_FRACTION', MASS_FRACTION],
  ['MOLE_FRACTION', MOLE_FRACTION],
  ['VOLUME_FRACTION', VOLUME_FRACTION],
  ['PURITY', PURITY],
  ['DISCOUNT_RATE', DISCOUNT_RATE],
  ['INTEREST_RATE', INTEREST_RATE],
  ['AVAILABILITY', AVAILABILITY],
  ['HEAT_TRANSFER_COEFF', HEAT_TRANSFER_COEFF],
  ['AREA', AREA],
  ['LENGTH', LENGTH],
  ['DIAMETER', DIAMETER],
  ['VELOCITY', VELOCITY],
  ['GHG_MASS', GHG_MASS],
  ['GHG_RATE', GHG_RATE],
  ['EMISSION_FACTOR_ENERGY', EMISSION_FACTOR_ENERGY],
  ['EMISSION_FACTOR_MASS', EMISSION_FACTOR_MASS],
  ['CARBON_INTENSITY_ENERGY', CARBON_INTENSITY_ENERGY],
  ['WATER_USAGE_FACTOR', WATER_USAGE_FACTOR],
  ['COST', COST],
  ['COST_PER_ENERGY', COST_PER_ENERGY],
  ['COST_PER_MASS', COST_PER_MASS],
  ['CAPEX', CAPEX],
  ['OPEX_PER_YEAR', OPEX_PER_YEAR],
  ['EXCHANGE_RATE', EXCHANGE_RATE],
  ['LIFETIME', LIFETIME],
  ['PRODUCTION', PRODUCTION],
  ['MASS_PER_AMOUNT', MASS_PER_AMOUNT],
  ['HEAT_CAPACITY_MASS', HEAT_CAPACITY_MASS],
  ['ENTHALPY_MASS', ENTHALPY_MASS],
  ['ENTHALPY_MOLAR', ENTHALPY_MOLAR],
  ['DIMENSIONLESS', DIMENSIONLESS],
  ['DIMENSIONLESS_INDEX', DIMENSIONLESS_INDEX],
  ['ACID_NUMBER', ACID_NUMBER],
];

export const CONVERSION_MAP: Map<string, ConversionEntry[]> = new Map(familyEntries);
