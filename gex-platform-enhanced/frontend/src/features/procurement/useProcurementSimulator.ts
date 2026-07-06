/**
 * Hook that owns the procurement simulator state: preferences, per-equipment
 * constraints, last result, and commit-to-canvas.
 *
 * GEX adaptation: operates standalone without the plant canvas. Equipment
 * list is seeded from a default set or user-defined items. Canvas commit
 * is stubbed until the Plant Canvas is ported.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { runSimulator } from "@/lib/procurement/configurationEngine";
import { filterCandidatesForSlot } from "@/lib/procurement/candidateFilter";
import { familiesForLabel } from "@/lib/procurement/technologyMap";
import { getCatalogForLabel } from "@/lib/equipmentCatalog";
import {
  DEFAULT_GLOBALS,
  type Configuration,
  type EquipmentConstraints,
  type GlobalPreferences,
  type SimulatorResult,
} from "@/lib/procurement/simulatorTypes";

const STORAGE_KEY = (plantId: string) => `procurement-sim:${plantId}`;

/** Default equipment set for standalone mode (no canvas) */
const DEFAULT_EQUIPMENT: Array<{ nodeId: string; label: string }> = [
  { nodeId: "eq-electrolysis", label: "Electrolyzer" },
  { nodeId: "eq-compressor",   label: "Compressor" },
  { nodeId: "eq-water",        label: "Water Treatment" },
  { nodeId: "eq-reactor",      label: "Synthesis Reactor" },
  { nodeId: "eq-tank",         label: "Storage Tank" },
  { nodeId: "eq-heatex",       label: "Heat Exchanger" },
];

function loadFromStorage(plantId: string): {
  globals: GlobalPreferences;
  equipmentOverrides: Record<string, Partial<EquipmentConstraints>>;
} | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY(plantId));
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function saveToStorage(plantId: string, payload: unknown) {
  try {
    localStorage.setItem(STORAGE_KEY(plantId), JSON.stringify(payload));
  } catch {/* ignore */}
}

export function useProcurementSimulator(plantId: string) {
  const initial = useMemo(() => loadFromStorage(plantId), [plantId]);
  const [globals, setGlobals] = useState<GlobalPreferences>(initial?.globals ?? DEFAULT_GLOBALS);

  const [equipmentOverrides, setEquipmentOverrides] = useState<Record<string, Partial<EquipmentConstraints>>>(
    initial?.equipmentOverrides ?? {},
  );

  const equipment = useMemo<EquipmentConstraints[]>(
    () =>
      DEFAULT_EQUIPMENT.map((n) => {
        const fams = familiesForLabel(n.label);
        const ov = equipmentOverrides[n.nodeId] ?? {};
        return {
          nodeId: n.nodeId,
          label: n.label,
          technologies: ov.technologies ?? fams,
          capacity: ov.capacity ?? { unit: "MW" },
          costCapEur: ov.costCapEur,
          override: ov.override,
        };
      }),
    [equipmentOverrides],
  );

  // Persist
  useEffect(() => {
    if (!plantId) return;
    saveToStorage(plantId, { globals, equipmentOverrides });
  }, [plantId, globals, equipmentOverrides]);

  // Run engine on demand
  const [result, setResult] = useState<SimulatorResult | null>(null);

  const liveMatchCounts = useMemo<Record<string, number>>(() => {
    const out: Record<string, number> = {};
    for (const eq of equipment) {
      out[eq.nodeId] = filterCandidatesForSlot(eq, globals).length;
    }
    return out;
  }, [equipment, globals]);

  const totalSlotMatches = useMemo(
    () => Object.values(liveMatchCounts).reduce((a, b) => a + b, 0),
    [liveMatchCounts],
  );

  const totalSlotPool = useMemo(() => {
    let n = 0;
    for (const eq of equipment) {
      const lower = eq.label.toLowerCase().trim();
      const pool = getCatalogForLabel(eq.label);
      const labelMatches = pool.some((e) =>
        e.keywords.some((kw) => lower.includes(kw.toLowerCase())),
      );
      n += labelMatches ? pool.length : 0;
    }
    return n;
  }, [equipment]);

  const run = useCallback(() => {
    if (equipment.length === 0) {
      setResult({ configurations: [], perSlotMatchCount: {}, totalCatalogCount: 0, globallyMatchingCount: 0 });
      return;
    }
    setResult(runSimulator({ globals, equipment }));
  }, [equipment, globals]);

  // Auto-run once
  useEffect(() => {
    if (equipment.length > 0 && result === null) {
      setResult(runSimulator({ globals, equipment }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [equipment.length]);

  const setEquipmentConstraint = useCallback(
    (nodeId: string, patch: Partial<EquipmentConstraints>) => {
      setEquipmentOverrides((prev) => ({
        ...prev,
        [nodeId]: { ...(prev[nodeId] ?? {}), ...patch },
      }));
    },
    [],
  );

  const copyToAllOfType = useCallback(
    (sourceNodeId: string, label: string) => {
      const source = equipmentOverrides[sourceNodeId] ?? {};
      setEquipmentOverrides((prev) => {
        const next = { ...prev };
        for (const eq of equipment) {
          if (eq.label === label && eq.nodeId !== sourceNodeId) {
            next[eq.nodeId] = { ...source };
          }
        }
        return next;
      });
    },
    [equipment, equipmentOverrides],
  );

  /** Stub — canvas commit not available until Plant Canvas is ported. */
  const commitConfiguration = useCallback(
    async (_config: Configuration) => {
      return { ok: false as const, applied: 0 };
    },
    [],
  );

  return {
    canvasLoading: false,
    canvasReady: true,
    equipment,
    globals,
    setGlobals,
    setEquipmentConstraint,
    copyToAllOfType,
    result,
    liveMatchCounts,
    totalSlotMatches,
    totalSlotPool,
    run,
    commitConfiguration,
  };
}
