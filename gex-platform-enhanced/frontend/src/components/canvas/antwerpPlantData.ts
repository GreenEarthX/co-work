import type { Node, Edge } from "@xyflow/react";
import { getEdgeHandles } from "./portSystem";

/**
 * Antwerp Green Methanol — 15 kt eMeOH/year, 75 MW
 * Topology: Grid Power → Electrolyzer → H₂ Compressor → MeOH Reactor → Distillation → Storage → Offtake
 *           CO₂ Capture (industrial flue gas) → CO₂ Compressor → MeOH Reactor
 */

const CLR_ELEC  = "hsl(45, 85%, 45%)";
const CLR_WATER = "hsl(190, 75%, 55%)";
const CLR_H2    = "hsl(152, 50%, 42%)";
const CLR_O2    = "hsl(210, 70%, 65%)";
const CLR_CO2   = "hsl(30, 50%, 45%)";
const CLR_MEOH  = "hsl(270, 45%, 55%)";
const CLR_WASTE = "hsl(300, 40%, 55%)";
const CLR_HEAT  = "hsl(0, 65%, 50%)";

const BX = 160, BY = 40, BW = 1650, BH = 580;

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

export const antwerpNodes: Node[] = [
  { id: "boundary", type: "boundary", position: { x: BX, y: BY }, data: { width: BW, height: BH }, draggable: false, selectable: false, style: { zIndex: -1 } },

  // Input gates
  { id: "g-power",  type: "gate", position: { x: 0, y: 120 }, data: { label: "Grid Power", gateType: "input" } },
  { id: "g-water",  type: "gate", position: { x: 0, y: 320 }, data: { label: "Water Supply", gateType: "input" } },
  { id: "g-fluegas", type: "gate", position: { x: 0, y: 500 }, data: { label: "Industrial Flue Gas", gateType: "input" } },

  // Output gates
  { id: "g-vent",    type: "gate", position: { x: BX + BW + 60, y: 80 },  data: { label: "Vent (O₂)", gateType: "output" } },
  { id: "g-offtake", type: "gate", position: { x: BX + BW + 60, y: 280 }, data: { label: "eMeOH Offtake", gateType: "output" } },
  { id: "g-waste",   type: "gate", position: { x: BX + BW + 60, y: 480 }, data: { label: "Wastewater", gateType: "output" } },

  // Electricity bus
  { id: "c-elec1", type: "carrier", position: { x: 210, y: 130 }, data: { label: "Electricity" } },

  // Water treatment
  { id: "c-water1", type: "carrier",   position: { x: 210, y: 330 }, data: { label: "Water" } },
  { id: "e-wtu",    type: "equipment", position: { x: 340, y: 320 }, data: { label: "Water Treatment Unit", id: "790" } },
  { id: "c-water2", type: "carrier",   position: { x: 500, y: 330 }, data: { label: "Demin Water" } },

  // Electrolyzer
  { id: "e-electrolyzer", type: "equipment", position: { x: 540, y: 210 }, data: { label: "Electrolyzer", id: "782" } },
  { id: "c-h2-1",   type: "carrier",   position: { x: 720, y: 220 }, data: { label: "Hydrogen" } },
  { id: "e-h2comp", type: "equipment", position: { x: 820, y: 210 }, data: { label: "H₂ Compressor", id: "794" } },
  { id: "c-h2-2",   type: "carrier",   position: { x: 980, y: 220 }, data: { label: "Hydrogen" } },
  { id: "c-o2",     type: "carrier",   position: { x: 720, y: 100 }, data: { label: "Oxygen" } },

  // CO₂ capture branch
  { id: "c-flue1",  type: "carrier",   position: { x: 210, y: 510 }, data: { label: "Flue Gas" } },
  { id: "e-co2cap", type: "equipment", position: { x: 340, y: 490 }, data: { label: "CO₂ Capture Unit", id: "co2cap-01" } },
  { id: "c-co2-1",  type: "carrier",   position: { x: 520, y: 500 }, data: { label: "CO₂" } },
  { id: "e-co2comp", type: "equipment", position: { x: 620, y: 490 }, data: { label: "CO₂ Compressor", id: "co2comp-01" } },
  { id: "c-co2-2",  type: "carrier",   position: { x: 800, y: 500 }, data: { label: "CO₂" } },

  // Methanol synthesis
  { id: "e-meoh",    type: "equipment", position: { x: 1060, y: 310 }, data: { label: "Methanol Synthesis Reactor", id: "meoh-01" } },
  { id: "c-meoh1",  type: "carrier",   position: { x: 1250, y: 320 }, data: { label: "Crude Methanol" } },
  { id: "e-distill", type: "equipment", position: { x: 1350, y: 310 }, data: { label: "Distillation Column", id: "dist-01" } },
  { id: "c-meoh2",  type: "carrier",   position: { x: 1520, y: 320 }, data: { label: "Methanol" } },
  { id: "e-storage", type: "equipment", position: { x: 1620, y: 310 }, data: { label: "Methanol Storage Tank", id: "meohtank-01" } },
  { id: "c-meoh3",  type: "carrier",   position: { x: 1720, y: 320 }, data: { label: "Methanol" } },

  // Heat recovery
  { id: "c-heat",   type: "carrier",   position: { x: 1250, y: 160 }, data: { label: "Heat" } },

  // Wastewater
  { id: "c-waste",  type: "carrier",   position: { x: 1520, y: 480 }, data: { label: "Wastewater" } },
];

export const antwerpEdges: Edge[] = [
  // Power
  feElec("e1", "g-power", "c-elec1", 75, "MW", true),
  feElec("e2", "c-elec1", "e-electrolyzer", 68, "MW"),
  feElec("e2b", "c-elec1", "e-co2cap", 3, "MW"),
  feElec("e2c", "c-elec1", "e-co2comp", 2, "MW"),

  // Water
  fe("e3", "g-water",  "c-water1", CLR_WATER, 42, "m³/h", true),
  fe("e4", "c-water1", "e-wtu",    CLR_WATER, 42, "m³/h"),
  fe("e5", "e-wtu",    "c-water2", CLR_WATER, 39, "m³/h"),
  fe("e6", "c-water2", "e-electrolyzer", CLR_WATER, 39, "m³/h"),

  // H₂ stream
  fe("e7",  "e-electrolyzer", "c-h2-1",  CLR_H2, 1875, "kg/h"),
  fe("e8",  "c-h2-1",  "e-h2comp",       CLR_H2, 1875, "kg/h"),
  fe("e9",  "e-h2comp","c-h2-2",         CLR_H2, 1875, "kg/h"),
  fe("e10", "c-h2-2",  "e-meoh",         CLR_H2, 1875, "kg/h"),

  // O₂ byproduct
  fe("e11", "e-electrolyzer", "c-o2",   CLR_O2, 15000, "kg/h"),
  fe("e12", "c-o2",           "g-vent", CLR_O2, 15000, "kg/h"),

  // CO₂ capture
  fe("e13", "g-fluegas", "c-flue1",   CLR_CO2, 12000, "m³/h", true),
  fe("e14", "c-flue1",   "e-co2cap",  CLR_CO2, 12000, "m³/h"),
  fe("e15", "e-co2cap",  "c-co2-1",   CLR_CO2, 1400, "kg/h"),
  fe("e16", "c-co2-1",   "e-co2comp", CLR_CO2, 1400, "kg/h"),
  fe("e17", "e-co2comp", "c-co2-2",   CLR_CO2, 1400, "kg/h"),
  fe("e18", "c-co2-2",   "e-meoh",    CLR_CO2, 1400, "kg/h"),

  // Methanol synthesis → distillation → storage → offtake
  fe("e19", "e-meoh",    "c-meoh1",   CLR_MEOH, 2100, "kg/h"),
  fe("e20", "c-meoh1",   "e-distill", CLR_MEOH, 2100, "kg/h"),
  fe("e21", "e-distill", "c-meoh2",   CLR_MEOH, 2050, "kg/h"),
  fe("e22", "c-meoh2",   "e-storage", CLR_MEOH, 2050, "kg/h"),
  fe("e23", "e-storage", "c-meoh3",   CLR_MEOH, 2050, "kg/h"),
  fe("e24", "c-meoh3",   "g-offtake", CLR_MEOH, 2050, "kg/h", true),

  // Heat recovery from reactor
  fe("e25", "e-meoh",  "c-heat",  CLR_HEAT, 4.5, "MW"),

  // Wastewater
  fe("e26", "e-distill", "c-waste", CLR_WASTE, 5, "m³/h"),
  fe("e27", "c-waste",   "g-waste", CLR_WASTE, 5, "m³/h"),
];
