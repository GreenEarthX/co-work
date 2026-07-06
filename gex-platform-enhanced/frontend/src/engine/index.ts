/**
 * Barrel export for the equation engine.
 */

// Types
export type {
  ScopeType,
  ValueSource,
  ValueType,
  Severity,
  ParameterKeyDef,
  UnitFamily,
  FormulaDef,
  IssueCodeDef,
  DefaultLibraryEntry,
  ArchetypeRule9Profile,
  ParameterValue,
  EquipmentEngineState,
  RuleFinding,
} from './types';

// Engine singleton
export { EquationEngine, engineInstance } from './EquationEngine';

// React hooks
export { useEquipmentEngine, useEngineCheck } from './hooks/useEquationEngine';

// Unit conversion
export { convertToCanonical, convertFromCanonical, validateUnit } from './units/converter';

// Solver
export { resolveEquipment } from './solver/formulaResolver';

// Checker
export { runCheck, runCheckForEquipment } from './checker/ruleChecker';

// Registries (for advanced use)
export { PARAMETER_KEYS } from './registry/parameterKeys';
export { UNIT_FAMILIES, getUnitFamily, getParameterDef } from './registry/unitFamilies';
export { FORMULAS } from './registry/formulas';
export { DEFAULT_LIBRARY } from './registry/defaultLibrary';
export { ARCHETYPE_PROFILES } from './registry/archetypeProfiles';
export { ISSUE_CODES } from './registry/issueCodes';
