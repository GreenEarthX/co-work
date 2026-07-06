/**
 * Equation library — loads the catalog from /public/equation-library/equations.json
 * and exposes parsed access helpers.
 *
 * The library file groups equations by `component_id` (E1, E2…) — these are
 * canonical equipment archetype IDs. The current Lovable canvas does not yet
 * tag each equipment node with that archetype ID, so the picker exposes ALL
 * formulas (across components) and lets the user select. This is intentional
 * for the first iteration — we want the user to be free to bind any formula
 * they want to any equipment.
 */

export interface EquationDef {
  id: string;
  expression: string;
  description: string;
  input_params: string;
  output_param: string;
  equation_type: string;
}

export interface ComponentEquations {
  component_id: string;
  equations: EquationDef[];
}

let cache: ComponentEquations[] | null = null;
let inflight: Promise<ComponentEquations[]> | null = null;

export async function loadEquationLibrary(): Promise<ComponentEquations[]> {
  if (cache) return cache;
  if (inflight) return inflight;
  inflight = fetch("/equation-library/equations.json")
    .then((r) => {
      if (!r.ok) throw new Error(`Equation library HTTP ${r.status}`);
      return r.json() as Promise<ComponentEquations[]>;
    })
    .then((data) => {
      cache = data;
      return data;
    })
    .finally(() => {
      inflight = null;
    });
  return inflight;
}

export function flattenEquations(lib: ComponentEquations[]): Array<EquationDef & { component_id: string }> {
  const out: Array<EquationDef & { component_id: string }> = [];
  for (const c of lib) {
    for (const eq of c.equations) {
      out.push({ ...eq, component_id: c.component_id });
    }
  }
  return out;
}

export function parseInputParams(input_params: string): string[] {
  return input_params
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}