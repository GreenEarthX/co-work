/**
 * Dependency graph builder and topological sorter for formula resolution.
 * Pure functions — no side effects, no state.
 */
import type { FormulaDef, ScopeType } from '../types';
import { FORMULAS } from '../registry/formulas';

export interface DependencyNode {
  formulaId: string;
  outputParamKey: string;
  inputParamKeys: readonly string[];
  priority: number;
  appliesToModelId: string;
}

export interface DependencyGraph {
  nodes: Map<string, DependencyNode>;   // keyed by formulaId
  edges: Map<string, string[]>;          // formulaId -> [formulaIds it depends on]
  executionOrder: string[];              // topologically sorted formula IDs
}

const SCOPE_PRIORITY: Record<ScopeType, number> = {
  EQUIPMENT: 3,
  ARCHETYPE: 2,
  GLOBAL: 1,
  STREAM: 0,
  GATE: 0,
  PLANT: 0,
  MODEL: 0,
};

/**
 * Filter FORMULAS to those applicable for a given archetype + equipment + model set.
 * More specific scope wins; within same scope, lower priority number wins.
 */
export function getApplicableFormulas(
  archetypeId: string,
  equipmentName: string | null,
  modelIds: string[],
): FormulaDef[] {
  const candidates = (FORMULAS as readonly FormulaDef[]).filter(f => {
    if (!modelIds.includes(f.appliesToModelId)) return false;
    switch (f.scopeType) {
      case 'GLOBAL': return f.scopeId === '*';
      case 'ARCHETYPE': return f.scopeId === archetypeId;
      case 'EQUIPMENT': return equipmentName != null && f.scopeId === equipmentName;
      default: return false;
    }
  });

  // Group by outputParamKey, keep most specific / highest priority
  const byOutput = new Map<string, FormulaDef[]>();
  for (const f of candidates) {
    const arr = byOutput.get(f.outputParamKey) ?? [];
    arr.push(f);
    byOutput.set(f.outputParamKey, arr);
  }

  const selected: FormulaDef[] = [];
  for (const [, group] of byOutput) {
    // Sort: highest scope specificity first, then lowest priority number
    group.sort((a, b) => {
      const scopeDiff = SCOPE_PRIORITY[b.scopeType] - SCOPE_PRIORITY[a.scopeType];
      if (scopeDiff !== 0) return scopeDiff;
      return a.priority - b.priority;
    });
    // Take only the winner (first after sort)
    selected.push(group[0]);
  }

  return selected;
}

/**
 * Build a DAG from a set of formulas and return topological execution order.
 * Throws if a cycle is detected.
 */
export function buildGraph(formulas: FormulaDef[]): DependencyGraph {
  // Break bidirectional cycles: if formula A outputs X using Y, and formula B outputs Y using X,
  // keep only the one with higher priority (lower number = higher priority).
  // Detect by checking for mutual output↔input dependency.
  const outputToFormula = new Map<string, FormulaDef>();
  for (const f of formulas) {
    outputToFormula.set(f.outputParamKey, f);
  }

  const dropped = new Set<string>();
  for (const f of formulas) {
    if (dropped.has(f.formulaId)) continue;
    for (const inputKey of f.inputParamKeys) {
      const producer = outputToFormula.get(inputKey);
      if (!producer || producer.formulaId === f.formulaId || dropped.has(producer.formulaId)) continue;
      // Check if producer uses f's output as input (mutual cycle)
      if (producer.inputParamKeys.includes(f.outputParamKey)) {
        // Drop the one with higher priority number (less specific)
        const toDrop = f.priority >= producer.priority ? f : producer;
        dropped.add(toDrop.formulaId);
      }
    }
  }

  const activeFormulas = formulas.filter(f => !dropped.has(f.formulaId));

  const nodes = new Map<string, DependencyNode>();
  const producerOf = new Map<string, string>();

  for (const f of activeFormulas) {
    nodes.set(f.formulaId, {
      formulaId: f.formulaId,
      outputParamKey: f.outputParamKey,
      inputParamKeys: f.inputParamKeys,
      priority: f.priority,
      appliesToModelId: f.appliesToModelId,
    });
    producerOf.set(f.outputParamKey, f.formulaId);
  }

  // Build edges: formulaId -> [formulaIds whose outputs this formula needs]
  const edges = new Map<string, string[]>();
  for (const f of activeFormulas) {
    const deps: string[] = [];
    for (const inputKey of f.inputParamKeys) {
      const producerId = producerOf.get(inputKey);
      if (producerId && producerId !== f.formulaId) {
        deps.push(producerId);
      }
    }
    edges.set(f.formulaId, deps);
  }

  // Kahn's algorithm for topological sort
  const inDegree = new Map<string, number>();
  for (const fId of nodes.keys()) {
    inDegree.set(fId, 0);
  }
  for (const [fId, deps] of edges) {
    inDegree.set(fId, deps.length);
  }

  const queue: string[] = [];
  for (const [fId, deg] of inDegree) {
    if (deg === 0) queue.push(fId);
  }

  const executionOrder: string[] = [];
  const dependents = new Map<string, string[]>();
  for (const [fId, deps] of edges) {
    for (const dep of deps) {
      const arr = dependents.get(dep) ?? [];
      arr.push(fId);
      dependents.set(dep, arr);
    }
  }

  while (queue.length > 0) {
    queue.sort((a, b) => (nodes.get(a)!.priority) - (nodes.get(b)!.priority));
    const current = queue.shift()!;
    executionOrder.push(current);

    for (const dependent of (dependents.get(current) ?? [])) {
      const newDeg = (inDegree.get(dependent) ?? 1) - 1;
      inDegree.set(dependent, newDeg);
      if (newDeg === 0) queue.push(dependent);
    }
  }

  if (executionOrder.length !== nodes.size) {
    const remaining = [...nodes.keys()].filter(id => !executionOrder.includes(id));
    throw new Error(
      `Cycle detected in formula dependency graph. Involved formulas: ${remaining.join(', ')}`
    );
  }

  return { nodes, edges, executionOrder };
}
