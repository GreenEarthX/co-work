import type { Node, Edge } from "@xyflow/react";
import { getEdgeHandles } from "./portSystem";

/**
 * Marseille eFuel Pilot — 5 kt eMeOH/year, 25 MW
 * Topology: Solar Power → Electrolyzer → H₂ Purifier → MeOH Reactor → Distillation → Offtake
 *           DAC → CO₂ Purification → MeOH Reactor
 */

const CLR_ELEC  = "hsl(45, 85%, 45%)";
const CLR_WATER = "hsl(190, 75%, 55%)";
const CLR_H2    = "hsl(152, 50%, 42%)";
const CLR_O2    = "hsl(210, 70%, 65%)";
const CLR_CO2   = "hsl(30, 50%, 45%)";
const CLR_MEOH  = "hsl(270, 45%, 55%)";
const CLR_AIR   = "hsl(200, 40%, 60%)";
const CLR_WASTE = "hsl(300, 40%, 55%)";

const BX = 160, BY = 40, BW = 1550, BH = 560;

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

export const marseilleNodes: Node[] = [
  { id: "boundary", type: "boundary", position: { x: BX, y: BY }, data: { width: BW, height: BH }, draggable: false, selectable: false, style: { zIndex: -1 } },

  // Input gates
  { id: "g-power", type: "gate", position: { x: 0, y: 120 }, data: { label: "Solar Power", gateType: "input" } },
  { id: "g-water", type: "gate", position: { x: 0, y: 340 }, data: { label: "Water Supply", gateType: "input" } },
  { id: "g-air",   type: "gate", position: { x: 0, y: 500 }, data: { label: "Air Intake", gateType: "input" } },

  // Output gates
  { id: "g-vent",    type: "gate", position: { x: BX + BW + 60, y: 80 },  data: { label: "Vent (O₂)", gateType: "output" } },
  { id: "g-offtake", type: "gate", position: { x: BX + BW + 60, y: 260 }, data: { label: "eMeOH Offtake", gateType: "output" } },
  { id: "g-waste",   type: "gate", position: { x: BX + BW + 60, y: 460 }, data: { label: "Wastewater", gateType: "output" } },

  // Electricity bus
  { id: "c-elec1", type: "carrier", position: { x: 210, y: 130 }, data: { label: "Electricity" } },

  // Water treatment
  { id: "c-water1", type: "carrier",   position: { x: 210, y: 350 }, data: { label: "Water" } },
  { id: "e-ro",     type: "equipment", position: { x: 340, y: 340 }, data: { label: "Reverse Osmosis Unit", id: "ro-01" } },
  { id: "c-water2", type: "carrier",   position: { x: 500, y: 350 }, data: { label: "Demin Water" } },

  // Electrolyzer
  { id: "e-electrolyzer", type: "equipment", position: { x: 540, y: 220 }, data: { label: "Electrolyzer", id: "782" } },
  { id: "c-h2-1",   type: "carrier",   position: { x: 720, y: 230 }, data: { label: "Hydrogen" } },
  { id: "e-purif",   type: "equipment", position: { x: 810, y: 220 }, data: { label: "Hydrogen Purifier", id: "793" } },
  { id: "c-h2-2",   type: "carrier",   position: { x: 970, y: 230 }, data: { label: "Hydrogen" } },
  { id: "c-o2",     type: "carrier",   position: { x: 720, y: 100 }, data: { label: "Oxygen" } },

  // DAC branch
  { id: "c-air1",   type: "carrier",   position: { x: 210, y: 510 }, data: { label: "Air" } },
  { id: "e-dac",     type: "equipment", position: { x: 340, y: 490 }, data: { label: "DAC Contactor", id: "dac-01" } },
  { id: "c-co2-1",  type: "carrier",   position: { x: 520, y: 500 }, data: { label: "CO₂" } },
  { id: "e-co2pur",  type: "equipment", position: { x: 620, y: 490 }, data: { label: "CO₂ Purification Unit", id: "co2pur-01" } },
  { id: "c-co2-2",  type: "carrier",   position: { x: 800, y: 500 }, data: { label: "CO₂" } },

  // Methanol synthesis
  { id: "e-meoh",    type: "equipment", position: { x: 1050, y: 300 }, data: { label: "Methanol Synthesis Reactor", id: "meoh-01" } },
  { id: "c-meoh1",  type: "carrier",   position: { x: 1240, y: 310 }, data: { label: "Methanol" } },
  { id: "e-distill", type: "equipment", position: { x: 1340, y: 300 }, data: { label: "Distillation Column", id: "dist-01" } },
  { id: "c-meoh2",  type: "carrier",   position: { x: 1520, y: 310 }, data: { label: "Methanol" } },

  // Wastewater
  { id: "c-waste",   type: "carrier",   position: { x: 1340, y: 460 }, data: { label: "Wastewater" } },
];

export const marseilleEdges: Edge[] = [
  // Power
  feElec("e1", "g-power", "c-elec1", 25, "MW", true),
  feElec("e2", "c-elec1", "e-electrolyzer", 22, "MW"),
  feElec("e2b", "c-elec1", "e-dac", 2.5, "MW"),

  // Water
  fe("e3", "g-water",  "c-water1", CLR_WATER, 18, "m³/h", true),
  fe("e4", "c-water1", "e-ro",     CLR_WATER, 18, "m³/h"),
  fe("e5", "e-ro",     "c-water2", CLR_WATER, 15, "m³/h"),
  fe("e6", "c-water2", "e-electrolyzer", CLR_WATER, 15, "m³/h"),

  // H₂ stream
  fe("e7",  "e-electrolyzer", "c-h2-1",  CLR_H2, 625, "kg/h"),
  fe("e8",  "c-h2-1",  "e-purif",        CLR_H2, 625, "kg/h"),
  fe("e9",  "e-purif",  "c-h2-2",        CLR_H2, 620, "kg/h"),
  fe("e10", "c-h2-2",  "e-meoh",         CLR_H2, 620, "kg/h"),

  // O₂ byproduct
  fe("e11", "e-electrolyzer", "c-o2",   CLR_O2, 5000, "kg/h"),
  fe("e12", "c-o2",           "g-vent", CLR_O2, 5000, "kg/h"),

  // DAC → CO₂
  fe("e13", "g-air",   "c-air1",   CLR_AIR, 8500, "m³/h", true),
  fe("e14", "c-air1",  "e-dac",    CLR_AIR, 8500, "m³/h"),
  fe("e15", "e-dac",   "c-co2-1",  CLR_CO2, 480,  "kg/h"),
  fe("e16", "c-co2-1", "e-co2pur", CLR_CO2, 480,  "kg/h"),
  fe("e17", "e-co2pur","c-co2-2",  CLR_CO2, 470,  "kg/h"),
  fe("e18", "c-co2-2", "e-meoh",   CLR_CO2, 470,  "kg/h"),

  // Methanol synthesis → distillation → offtake
  fe("e19", "e-meoh",    "c-meoh1",  CLR_MEOH, 720, "kg/h"),
  fe("e20", "c-meoh1",   "e-distill", CLR_MEOH, 720, "kg/h"),
  fe("e21", "e-distill", "c-meoh2",  CLR_MEOH, 700, "kg/h"),
  fe("e22", "c-meoh2",   "g-offtake", CLR_MEOH, 700, "kg/h", true),

  // Wastewater
  fe("e23", "e-distill", "c-waste", CLR_WASTE, 3, "m³/h"),
  fe("e24", "c-waste",   "g-waste", CLR_WASTE, 3, "m³/h"),
];
