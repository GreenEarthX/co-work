/**
 * Unit conversion functions for the equation engine.
 * Pure functions — no side effects, no state.
 */
import { getUnitFamily } from '../registry/unitFamilies';
import { CONVERSION_MAP } from './conversionFactors';

export interface ConversionResult {
  canonical: number;
  success: boolean;
  error?: string;
}

export interface ReverseConversionResult {
  value: number;
  success: boolean;
  error?: string;
}

export interface ValidationResult {
  valid: boolean;
  error?: string;
}

/**
 * Convert a value from `fromUnit` to the canonical unit of `unitFamily`.
 */
export function convertToCanonical(
  value: number,
  fromUnit: string,
  unitFamily: string,
): ConversionResult {
  const family = getUnitFamily(unitFamily);
  if (!family) {
    return { canonical: NaN, success: false, error: `Unknown unit family: ${unitFamily}` };
  }

  if (!family.allowedUnits.includes(fromUnit) && fromUnit !== family.canonicalUnit) {
    return { canonical: NaN, success: false, error: `Unit "${fromUnit}" is not allowed in family ${unitFamily}` };
  }

  if (fromUnit === family.canonicalUnit) {
    return { canonical: value, success: true };
  }

  const entries = CONVERSION_MAP.get(unitFamily);
  if (!entries) {
    // Check if the family requires context
    if (family.requiresContext.length > 0) {
      return { canonical: NaN, success: false, error: `Context required for conversion: ${family.requiresContext.join(', ')}` };
    }
    return { canonical: NaN, success: false, error: `No conversions registered for family ${unitFamily}` };
  }

  const entry = entries.find(e => e.from === fromUnit);
  if (!entry) {
    // Might be a context-dependent unit
    if (family.requiresContext.length > 0) {
      return { canonical: NaN, success: false, error: `Context required for conversion: ${family.requiresContext.join(', ')}` };
    }
    return { canonical: NaN, success: false, error: `No conversion found from "${fromUnit}" to "${family.canonicalUnit}" in family ${unitFamily}` };
  }

  return { canonical: entry.convert(value), success: true };
}

/**
 * Convert a canonical value back to `toUnit` within `unitFamily`.
 */
export function convertFromCanonical(
  canonicalValue: number,
  toUnit: string,
  unitFamily: string,
): ReverseConversionResult {
  const family = getUnitFamily(unitFamily);
  if (!family) {
    return { value: NaN, success: false, error: `Unknown unit family: ${unitFamily}` };
  }

  if (!family.allowedUnits.includes(toUnit) && toUnit !== family.canonicalUnit) {
    return { value: NaN, success: false, error: `Unit "${toUnit}" is not allowed in family ${unitFamily}` };
  }

  if (toUnit === family.canonicalUnit) {
    return { value: canonicalValue, success: true };
  }

  const entries = CONVERSION_MAP.get(unitFamily);
  if (!entries) {
    if (family.requiresContext.length > 0) {
      return { value: NaN, success: false, error: `Context required for conversion: ${family.requiresContext.join(', ')}` };
    }
    return { value: NaN, success: false, error: `No conversions registered for family ${unitFamily}` };
  }

  const entry = entries.find(e => e.from === toUnit);
  if (!entry) {
    if (family.requiresContext.length > 0) {
      return { value: NaN, success: false, error: `Context required for conversion: ${family.requiresContext.join(', ')}` };
    }
    return { value: NaN, success: false, error: `No conversion found for "${toUnit}" in family ${unitFamily}` };
  }

  // For non-linear conversions (temperature), we need to invert numerically.
  // Temperature special cases:
  if (unitFamily === 'TEMPERATURE') {
    return invertTemperature(canonicalValue, toUnit);
  }

  // For linear conversions: canonical = value * factor  →  value = canonical / factor
  // We find the factor by converting 1 unit: factor = entry.convert(1)
  // But for offset-based this is wrong. Since only TEMPERATURE is offset-based
  // and handled above, all remaining are linear: value = canonical / convert(1).
  const factor = entry.convert(1);
  if (factor === 0) {
    return { value: NaN, success: false, error: `Degenerate conversion factor for "${toUnit}"` };
  }
  return { value: canonicalValue / factor, success: true };
}

function invertTemperature(kelvin: number, toUnit: string): ReverseConversionResult {
  switch (toUnit) {
    case 'C':
    case '°C':
      return { value: kelvin - 273.15, success: true };
    case 'F':
    case '°F':
      return { value: (kelvin - 273.15) * 9 / 5 + 32, success: true };
    default:
      return { value: NaN, success: false, error: `Unknown temperature unit "${toUnit}"` };
  }
}

/**
 * Validate that a unit string is allowed within a unit family.
 */
export function validateUnit(unit: string, unitFamily: string): ValidationResult {
  const family = getUnitFamily(unitFamily);
  if (!family) {
    return { valid: false, error: `Unknown unit family: ${unitFamily}` };
  }

  if (unit === family.canonicalUnit || family.allowedUnits.includes(unit)) {
    return { valid: true };
  }

  return {
    valid: false,
    error: `Unit "${unit}" is not valid for family ${unitFamily}. Allowed: ${[family.canonicalUnit, ...family.allowedUnits].join(', ')}`,
  };
}
