import type { Node, Edge } from "@xyflow/react";
import { getEdgeHandles } from "./portSystem";

/**
 * Rotterdam RFNBO Hydrogen Plant — pre-built flow diagram.
 *
 * Uses the same port system and edge helpers as the North Sea plant
 * for consistent stream colors, resource-typed handles, and 4-directional ports.
 */

// — color constants (carrier type) —
const CLR_ELEC  = "hsl(45, 85%, 45%)";
const CLR_WATER = "hsl(190, 75%, 55%)";
const CLR_H2    = "hsl(152, 50%, 42%)";
const CLR_O2    = "hsl(210, 70%, 65%)";

// Plant system boundary node
const BOUNDARY_X = 160;
const BOUNDARY_Y = 60;
const BOUNDARY_W = 1250;
const BOUNDARY_H = 460;

// Edge helper — auto-assigns sourceHandle/targetHandle via port system
const fe = (
  id: string, src: string, tgt: string, clr: string,
  val: number, unit: string, animated = false,
  extra?: Record<string, unknown>,
): Edge => {
  const handles = getEdgeHandles(src, tgt, clr);
  return {
    id, source: src, target: tgt, type: "flowEdge", animated,
    ...handles,
    style: { stroke: clr },
    data: {
      flowValue: val, flowUnit: unit,
      ...extra,
    },
  };
};

/** Electricity edge helper — marks edge as infrastructure */
const feElec = (
  id: string, src: string, tgt: string,
  val: number, unit: string, animated = false,
): Edge => fe(id, src, tgt, CLR_ELEC, val, unit, animated, { isElectricity: true });

/* ════════════════════════════════════════════════════════════
   NODES
   ════════════════════════════════════════════════════════════ */

export const rotterdamNodes: Node[] = [
  // System boundary
  {
    id: "boundary",
    type: "boundary",
    position: { x: BOUNDARY_X, y: BOUNDARY_Y },
    data: { width: BOUNDARY_W, height: BOUNDARY_H },
    draggable: false,
    selectable: false,
    style: { zIndex: -1 },
  },

  // ═══════ INPUT GATES ═══════
  { id: "g-power", type: "gate", position: { x: 0, y: 180 }, data: { label: "Power Supply", gateType: "input" } },
  { id: "g-water", type: "gate", position: { x: 0, y: 380 }, data: { label: "Water Supply", gateType: "input" } },

  // ═══════ OUTPUT GATES ═══════
  { id: "g-vent",    type: "gate", position: { x: BOUNDARY_X + BOUNDARY_W + 60, y: 120 }, data: { label: "Vent", gateType: "output" } },
  { id: "g-offtake", type: "gate", position: { x: BOUNDARY_X + BOUNDARY_W + 60, y: 300 }, data: { label: "Offtake Market", gateType: "output" } },

  // ═══════ CARRIERS & EQUIPMENT ═══════
  { id: "c-elec1",  type: "carrier",   position: { x: 210, y: 190 }, data: { label: "Electricity" } },
  { id: "c-water1", type: "carrier",   position: { x: 210, y: 390 }, data: { label: "Water" } },
  { id: "e-wtu",    type: "equipment", position: { x: 340, y: 380 }, data: { label: "Water Treatment Unit", id: "790" } },
  { id: "c-water2", type: "carrier",   position: { x: 520, y: 390 }, data: { label: "Water" } },

  { id: "e-electrolyzer", type: "equipment", position: { x: 560, y: 270 }, data: { label: "Electrolyzer", id: "782" } },
  { id: "c-h2-1",         type: "carrier",   position: { x: 740, y: 280 }, data: { label: "Hydrogen" } },
  { id: "e-purifier",     type: "equipment", position: { x: 850, y: 270 }, data: { label: "Hydrogen Purifier", id: "793" } },
  { id: "c-h2-2",         type: "carrier",   position: { x: 1020, y: 280 }, data: { label: "Hydrogen" } },
  { id: "e-compressor",   type: "equipment", position: { x: 1130, y: 270 }, data: { label: "H₂ Compressor", id: "794" } },
  { id: "c-h2-3",         type: "carrier",   position: { x: 1310, y: 280 }, data: { label: "Hydrogen" } },
  { id: "c-o2",           type: "carrier",   position: { x: 740, y: 140 }, data: { label: "Oxygen" } },
];

/* ════════════════════════════════════════════════════════════
   EDGES, using port system helpers for consistent handles
   ════════════════════════════════════════════════════════════ */

export const rotterdamEdges: Edge[] = [
  // Power supply → Electricity carrier (134 MW)
  feElec("e1", "g-power", "c-elec1", 134, "MW", true),
  feElec("e2", "c-elec1", "e-electrolyzer", 128, "MW"),

  // Water supply → WTU → Electrolyzer
  fe("e3", "g-water",  "c-water1",       CLR_WATER, 60.5, "m³/h", true),
  fe("e4", "c-water1", "e-wtu",          CLR_WATER, 60.5, "m³/h"),
  fe("e5", "e-wtu",    "c-water2",       CLR_WATER, 56.8, "m³/h"),
  fe("e6", "c-water2", "e-electrolyzer", CLR_WATER, 56.8, "m³/h"),

  // Electrolyzer → H₂ stream (2,520 → purified 2,500 → compressed 2,500 kg/h)
  fe("e7",  "e-electrolyzer", "c-h2-1",      CLR_H2, 2520, "kg/h"),
  fe("e8",  "c-h2-1",         "e-purifier",  CLR_H2, 2520, "kg/h"),
  fe("e9",  "e-purifier",     "c-h2-2",      CLR_H2, 2500, "kg/h"),
  fe("e10", "c-h2-2",         "e-compressor", CLR_H2, 2500, "kg/h"),
  fe("e11", "e-compressor",   "c-h2-3",      CLR_H2, 2500, "kg/h"),
  fe("e12", "c-h2-3",         "g-offtake",   CLR_H2, 2500, "kg/h", true),

  // Oxygen byproduct (stoichiometric: 8× H₂ mass)
  fe("e13", "e-electrolyzer", "c-o2",    CLR_O2, 20000, "kg/h"),
  fe("e14", "c-o2",           "g-vent",  CLR_O2, 20000, "kg/h"),
];
