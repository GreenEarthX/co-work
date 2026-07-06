import type { Node, Edge } from "@xyflow/react";
import { getEdgeHandles } from "./portSystem";

/**
 * Hamburg Green Hydrogen Plant — 10 kt H₂/year, 50 MW PEM
 * Simplified topology: Wind Power → Electrolyzer → Dryer → Compressor → Storage → Offtake
 */

const CLR_ELEC  = "hsl(45, 85%, 45%)";
const CLR_WATER = "hsl(190, 75%, 55%)";
const CLR_H2    = "hsl(152, 50%, 42%)";
const CLR_O2    = "hsl(210, 70%, 65%)";
const CLR_WASTE = "hsl(300, 40%, 55%)";

const BX = 160, BY = 60, BW = 1350, BH = 480;

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
    data: { flowValue: val, flowUnit: unit, ...extra },
  };
};

const feElec = (
  id: string, src: string, tgt: string,
  val: number, unit: string, animated = false,
): Edge => fe(id, src, tgt, CLR_ELEC, val, unit, animated, { isElectricity: true });

export const hamburgNodes: Node[] = [
  { id: "boundary", type: "boundary", position: { x: BX, y: BY }, data: { width: BW, height: BH }, draggable: false, selectable: false, style: { zIndex: -1 } },

  // Input gates
  { id: "g-power", type: "gate", position: { x: 0, y: 160 }, data: { label: "Wind Power", gateType: "input" } },
  { id: "g-water", type: "gate", position: { x: 0, y: 380 }, data: { label: "Water Supply", gateType: "input" } },

  // Output gates
  { id: "g-vent",    type: "gate", position: { x: BX + BW + 60, y: 120 }, data: { label: "Vent (O₂)", gateType: "output" } },
  { id: "g-offtake", type: "gate", position: { x: BX + BW + 60, y: 300 }, data: { label: "Offtake Market", gateType: "output" } },
  { id: "g-waste",   type: "gate", position: { x: BX + BW + 60, y: 460 }, data: { label: "Wastewater", gateType: "output" } },

  // Carriers & Equipment
  { id: "c-elec1",  type: "carrier",   position: { x: 210, y: 170 }, data: { label: "Electricity" } },
  { id: "c-water1", type: "carrier",   position: { x: 210, y: 390 }, data: { label: "Water" } },
  { id: "e-demin",  type: "equipment", position: { x: 340, y: 380 }, data: { label: "Demineralization Unit", id: "demin-01" } },
  { id: "c-water2", type: "carrier",   position: { x: 500, y: 390 }, data: { label: "Demin Water" } },

  { id: "e-electrolyzer", type: "equipment", position: { x: 540, y: 260 }, data: { label: "Electrolyzer", id: "782" } },
  { id: "c-h2-1",   type: "carrier",   position: { x: 720, y: 270 }, data: { label: "Hydrogen" } },
  { id: "e-dryer",   type: "equipment", position: { x: 820, y: 260 }, data: { label: "Dryer Unit", id: "dryer-01" } },
  { id: "c-h2-2",   type: "carrier",   position: { x: 980, y: 270 }, data: { label: "Hydrogen" } },
  { id: "e-comp",    type: "equipment", position: { x: 1080, y: 260 }, data: { label: "H₂ Compressor", id: "794" } },
  { id: "c-h2-3",   type: "carrier",   position: { x: 1240, y: 270 }, data: { label: "Hydrogen" } },
  { id: "e-storage", type: "equipment", position: { x: 1340, y: 260 }, data: { label: "Hydrogen Storage Tank", id: "h2tank-01" } },
  { id: "c-h2-4",   type: "carrier",   position: { x: 1420, y: 270 }, data: { label: "Hydrogen" } },

  { id: "c-o2",     type: "carrier",   position: { x: 720, y: 140 }, data: { label: "Oxygen" } },
  { id: "c-waste",  type: "carrier",   position: { x: 500, y: 460 }, data: { label: "Wastewater" } },
];

export const hamburgEdges: Edge[] = [
  // Power
  feElec("e1", "g-power", "c-elec1", 50, "MW", true),
  feElec("e2", "c-elec1", "e-electrolyzer", 48, "MW"),

  // Water
  fe("e3", "g-water",  "c-water1", CLR_WATER, 30, "m³/h", true),
  fe("e4", "c-water1", "e-demin",  CLR_WATER, 30, "m³/h"),
  fe("e5", "e-demin",  "c-water2", CLR_WATER, 28, "m³/h"),
  fe("e6", "c-water2", "e-electrolyzer", CLR_WATER, 28, "m³/h"),

  // H₂ stream
  fe("e7",  "e-electrolyzer", "c-h2-1",  CLR_H2, 1250, "kg/h"),
  fe("e8",  "c-h2-1",  "e-dryer",        CLR_H2, 1250, "kg/h"),
  fe("e9",  "e-dryer",  "c-h2-2",        CLR_H2, 1245, "kg/h"),
  fe("e10", "c-h2-2",  "e-comp",         CLR_H2, 1245, "kg/h"),
  fe("e11", "e-comp",   "c-h2-3",        CLR_H2, 1245, "kg/h"),
  fe("e12", "c-h2-3",  "e-storage",      CLR_H2, 1245, "kg/h"),
  fe("e13", "e-storage","c-h2-4",        CLR_H2, 1245, "kg/h"),
  fe("e14", "c-h2-4",  "g-offtake",      CLR_H2, 1245, "kg/h", true),

  // O₂ byproduct
  fe("e15", "e-electrolyzer", "c-o2",   CLR_O2, 10000, "kg/h"),
  fe("e16", "c-o2",           "g-vent", CLR_O2, 10000, "kg/h"),

  // Wastewater
  fe("e17", "e-demin",  "c-waste",  CLR_WASTE, 2, "m³/h"),
  fe("e18", "c-waste",  "g-waste",  CLR_WASTE, 2, "m³/h"),
];
