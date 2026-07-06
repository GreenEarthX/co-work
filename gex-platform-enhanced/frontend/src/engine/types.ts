/**
 * Core type system for the equation engine (Rule 9 — equipment capacity validation).
 * Pure data + types — no logic, no state management, no React.
 */

export type ScopeType = 'GLOBAL' | 'ARCHETYPE' | 'EQUIPMENT' | 'STREAM' | 'GATE' | 'PLANT' | 'MODEL';

export type ValueSource = 'USER' | 'DEFAULT_LIBRARY' | 'ARCHETYPE_PROFILE' | 'DERIVED' | 'OVERRIDE';

export type ValueType = 'number' | 'boolean' | 'enum' | 'string';

export type Severity = 'ERROR' | 'WARNING' | 'INFO' | 'CONSISTENCY' | 'VALIDATION' | 'CONTINUITY';

export interface ParameterKeyDef {
  readonly scopeType: ScopeType;
  readonly scopeId: string;
  readonly paramKey: string;
  readonly displayName: string;
  readonly description: string;
  readonly unitFamily: string;
  readonly canonicalUnit: string;
  readonly valueType: ValueType;
  readonly isUserEditable: boolean;
  readonly supportsOverride: boolean;
  readonly typicalSource: ValueSource;
  readonly derivedByModelId: string | null;
  readonly notes: string;
}

export interface UnitFamily {
  readonly unitFamily: string;
  readonly canonicalUnit: string;
  readonly allowedUnits: readonly string[];
  readonly requiresContext: readonly string[];
  readonly notes: string;
}

export interface FormulaDef {
  readonly formulaId: string;
  readonly scopeType: ScopeType;
  readonly scopeId: string;
  readonly priority: number;
  readonly appliesToModelId: string;
  readonly outputParamKey: string;
  readonly inputParamKeys: readonly string[];
  readonly expressionLatex: string;
  readonly implRef: string;
  readonly notes: string;
}

export interface IssueCodeDef {
  readonly issueCode: string;
  readonly scopeType: string;
  readonly severityPolicy: Severity;
  readonly keysAffected: readonly string[];
  readonly messageTemplate: string;
  readonly resolutionActions: readonly string[];
  readonly notes: string;
}

export interface DefaultLibraryEntry {
  readonly archetypeId: string;
  readonly paramKey: string;
  readonly defaultValue: number;
  readonly unit: string;
  readonly source: string;
  readonly basisNotes: string;
  readonly confidence: 'HIGH' | 'MED' | 'LOW';
  readonly notes: string;
}

export interface ArchetypeRule9Profile {
  readonly archetypeId: string;
  readonly throughputModelId: string;
  readonly electricityModelId: string;
  readonly heatModelId: string;
  readonly hoursParamKey: string;
  readonly supportsUserOverridePower: boolean;
  readonly notes: string;
}

export interface ParameterValue {
  paramKey: string;
  value: number | string | boolean | null;
  unit: string;
  canonicalValue: number | null;
  source: ValueSource;
  isOverridden: boolean;
  isDirty: boolean;
}

export interface EquipmentEngineState {
  equipmentInstanceId: string;
  archetypeId: string;
  parameters: Map<string, ParameterValue>;
  findings: RuleFinding[];
  lastComputedAt: number;
}

export interface RuleFinding {
  issueCode: string;
  severity: Severity;
  message: string;
  keysAffected: string[];
  evidenceJson: Record<string, unknown>;
  equipmentInstanceId: string;
}
