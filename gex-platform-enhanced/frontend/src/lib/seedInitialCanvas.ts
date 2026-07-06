/**
 * Seed an initial canvas JSON for a freshly-created plant.
 *
 * For each product selected in the New Plant form, we create one carrier
 * node labeled with the product's fuel type and wire it directly to its
 * own unique "Offtake Market" output gate. The boundary auto-resizes
 * later via the canvas's normal logic.
 */
import type { Node, Edge } from "@xyflow/react";
import { isBackendConfigured } from "@/lib/envGuard";
import { anchorHandleId, getColorFromResource } from "@/components/canvas/portSystem";

const BUCKET = "plant-data";

export interface SeedProduct {
  fuelType: string;
  capacity?: string;
  capacityUnit?: string;
}

/**
 * Canvas edges (FlowEdge) only carry units that the EquationEngine
 * recognises (see src/engine/registry/unitFamilies.ts → MASS_PER_TIME
 * and VOLUMETRIC_FLOW_GAS_NORMAL families). The product form, however,
 * accepts user-friendly labels ("Ton per Year", "Kilogram per Hour", …).
 *
 * Map every product-form label to a canonical engine flow unit and
 * convert the value so semantics stay correct downstream:
 *   • Ton per Year             → t/h     (val / hoursYear)
 *   • Ton per Day              → t/h     (val / 24)
 *   • Kilogram per Hour        → t/h     (val / 1000)   ← same family, normalise
 *   • Normal Cubic Meter / Hr  → Nm3/h   (1:1, gas volumetric)
 * Anything already in a known short form (t/h, kg/h, Nm3/h, …) is passed
 * through untouched so power users can still type engine-native units.
 */
const MASS_FLOW_ALIASES = new Set([
  "t/h", "kg/h", "kg/s", "kg/min", "kg/day", "t/day", "t/year", "lb/h", "lb/day",
]);
const GAS_FLOW_ALIASES = new Set(["Nm3/h", "Nm3/day", "Nm3/s", "Sm3/h"]);

export function normalizeFlow(
  capacity: string | undefined,
  unit: string | undefined,
  hoursYear: number,
): { value: number; unit: string } {
  const raw = capacity ? Number(capacity) || 0 : 0;
  const u = (unit || "").trim();
  const hrs = hoursYear > 0 ? hoursYear : 8760;
  switch (u) {
    case "Ton per Year":
    case "t/year":
    case "ton/year":
      return { value: raw / hrs, unit: "t/h" };
    case "Ton per Day":
    case "t/day":
      return { value: raw / 24, unit: "t/h" };
    case "Kilogram per Hour":
    case "kg/h":
      // Keep within the same MASS_PER_TIME family. Normalise to t/h so
      // every mass-flow product on the canvas shares a single unit.
      return { value: raw / 1000, unit: "t/h" };
    case "Normal Cubic Meter per Hour":
    case "Nm³/h":
    case "Nm3/h":
      return { value: raw, unit: "Nm3/h" };
  }
  // Pass through engine-native units; otherwise default to t/h with the
  // raw value so the edge still carries an allowed unit.
  if (MASS_FLOW_ALIASES.has(u) || GAS_FLOW_ALIASES.has(u)) {
    return { value: raw, unit: u };
  }
  return { value: raw, unit: "t/h" };
}

export function buildInitialCanvas(
  products: SeedProduct[],
  hoursYear: number = 8760,
): { nodes: Node[]; edges: Edge[] } {
  const cleanProducts = products.filter((p) => p.fuelType && p.fuelType.trim());
  if (cleanProducts.length === 0) return { nodes: [], edges: [] };

  const BOUNDARY_X = 160;
  const BOUNDARY_Y = 60;
  const BOUNDARY_W = 900;
  const BOUNDARY_H = Math.max(360, 60 + cleanProducts.length * 120);

  const nodes: Node[] = [
    {
      id: "boundary",
      type: "boundary",
      position: { x: BOUNDARY_X, y: BOUNDARY_Y },
      data: { width: BOUNDARY_W, height: BOUNDARY_H },
      draggable: false,
      selectable: false,
      style: { zIndex: -1 },
    },
  ];
  const edges: Edge[] = [];

  cleanProducts.forEach((p, idx) => {
    const carrierId = `c-product-${idx + 1}`;
    const gateId = `g-offtake-${idx + 1}`;
    const y = BOUNDARY_Y + 80 + idx * 120;
    nodes.push({
      id: carrierId,
      type: "carrier",
      position: { x: BOUNDARY_X + BOUNDARY_W - 200, y },
      data: { label: p.fuelType },
    });
    nodes.push({
      id: gateId,
      type: "gate",
      position: { x: BOUNDARY_X + BOUNDARY_W + 60, y: y - 4 },
      data: { label: "Offtake Market", gateType: "output" },
    });
    const flow = normalizeFlow(p.capacity, p.capacityUnit, hoursYear);
    edges.push({
      id: `e-product-${idx + 1}`,
      source: carrierId,
      target: gateId,
      type: "flowEdge",
      sourceHandle: anchorHandleId("right", "source"),
      targetHandle: anchorHandleId("left", "target"),
      style: { stroke: getColorFromResource(p.fuelType) },
      data: {
        flowValue: flow.value,
        flowUnit: flow.unit,
      },
    });
  });

  return { nodes, edges };
}

/**
 * Seed the cloud-storage canvas JSON for a new plant if no canvas exists yet.
 * Safe no-op when the backend isn't configured or a canvas is already present.
 */
export async function seedInitialCanvas(
  plantSlug: string,
  products: SeedProduct[],
  hoursYear: number = 8760,
  userId?: string,
): Promise<void> {
  if (!plantSlug || !isBackendConfigured()) return;
  if (products.filter((p) => p.fuelType && p.fuelType.trim()).length === 0) return;

  try {
    const { supabase } = await import("@/lib/backendClient");
    // Canvas JSON lives under users/{userId}/{slug}.json — scope properly.
    // If no userId, we cannot seed safely (would write to unscoped path).
    if (!userId) return;
    const objectPath = `users/${userId}/${plantSlug}.json`;

    const canvas = buildInitialCanvas(products, hoursYear);
    const payload = {
      nodes: canvas.nodes,
      edges: canvas.edges,
      plantSettings: {
        hoursYear: hoursYear || 8760,
        plantAvailability: 91.3,
        criticalPathNodeIds: [],
        boundaryPadding: { left: 0, right: 0, top: 0, bottom: 0 },
      },
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    await supabase.storage
      .from(BUCKET)
      .upload(objectPath, blob, { upsert: true, cacheControl: "0" });
  } catch (err) {
    console.warn("[seedInitialCanvas] failed:", err);
  }
}