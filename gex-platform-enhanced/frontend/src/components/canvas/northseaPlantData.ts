import type { Node, Edge } from "@xyflow/react";
import { getEdgeHandles, pickClosestAnchor, anchorHandleId } from "./portSystem";

/**
 * North Sea Hydrogen 10 MW Plant — pre-built flow diagram.
 *
 * TOPOLOGY RULES:
 *   1. A carrier connects a Gate to Equipment, or Equipment to Equipment.
 *   2. NO carrier-to-carrier edges — every carrier has exactly one role.
 *   3. Every edge carries flow data (value + unit).
 *   4. Gates sit outside the boundary; equipment/carriers inside.
 *   5. Electricity bus: single carrier distributes to all equipment directly.
 *   6. All downstream carriers (connecting to output gates) are vertically aligned.
 *   7. Equipment and gate nodes use resource-typed port handles.
 */

// — color constants (carrier type) —
const CLR_SEA     = "hsl(220, 60%, 55%)";
const CLR_ULTRA   = "hsl(190, 75%, 55%)";
const CLR_H2      = "hsl(152, 50%, 42%)";
const CLR_ELEC    = "hsl(45, 85%, 45%)";
const CLR_WASTE_W = "hsl(300, 40%, 55%)";
const CLR_HEAT    = "hsl(0, 65%, 50%)";
const CLR_CO2     = "hsl(30, 50%, 45%)";
const CLR_MEOH    = "hsl(270, 45%, 55%)";
const CLR_O2      = "hsl(210, 70%, 65%)";
const CLR_AIR     = "hsl(200, 40%, 60%)";
const CLR_COOL    = "hsl(195, 60%, 50%)";

// ── Grid columns (x) — 240px spacing for clearance ──
const C = (n: number) => n * 240;

// ── Grid rows (y) — 160px spacing for readable vertical gaps ──
const R = (n: number) => 180 + n * 160;

// ── Downstream output carrier column — all vertically aligned ──
const OUT_X = C(17);

// Boundary — tight fit around plant components
const BX = C(1) - 10;
const BY = 60;
const BW = OUT_X + 140 - BX;
const BH = R(6) + 120 - BY;

// Helper — auto-assigns sourceHandle/targetHandle for equipment/gate nodes
const fe = (
  id: string, src: string, tgt: string, clr: string,
  val: number, unit: string, animated = false, labelOffset?: [number, number],
  extra?: Record<string, unknown>,
): Edge => {
  const handles = getEdgeHandles(src, tgt, clr);
  return {
    id, source: src, target: tgt, type: "flowEdge", animated,
    ...handles,
    style: { stroke: clr },
    data: {
      flowValue: val, flowUnit: unit,
      ...(labelOffset ? { labelOffsetX: labelOffset[0], labelOffsetY: labelOffset[1] } : {}),
      ...extra,
    },
  };
};

/** Electricity edge helper — marks edge as infrastructure */
const feElec = (
  id: string, src: string, tgt: string,
  val: number, unit: string, animated = false, labelOffset?: [number, number],
): Edge => fe(id, src, tgt, CLR_ELEC, val, unit, animated, labelOffset, { isElectricity: true });

/* ════════════════════════════════════════════════════════════
   NODES
   ════════════════════════════════════════════════════════════ */

export const northseaNodes: Node[] = [
  // ── System boundary ──
  { id: "boundary", type: "boundary", position: { x: BX, y: BY }, data: { width: BW, height: BH }, draggable: false, selectable: false, style: { zIndex: -1 } },

  // ═══════ INPUT GATES (outside boundary, left) ═══════
  { id: "g-power", type: "gate", position: { x: C(0) - 60, y: 60 },   data: { label: "Power Supply", gateType: "input" } },
  { id: "g-water", type: "gate", position: { x: C(0) - 60, y: R(3) }, data: { label: "Water Supply", gateType: "input" } },
  { id: "g-air",   type: "gate", position: { x: C(0) - 60, y: R(5) }, data: { label: "Air Intake", gateType: "input" } },

  // ═══════ OUTPUT GATES (outside boundary, right — vertically aligned) ═══════
  { id: "g-vent",          type: "gate", position: { x: C(18) + 60, y: R(0) },  data: { label: "Vent", gateType: "output" } },
  { id: "g-offtake-elec",  type: "gate", position: { x: C(18) + 60, y: R(1) },  data: { label: "Offtake Market", gateType: "output" } },
  
  // Heat Offtake removed — heat is redistributed to desalination units
  { id: "g-waste-water",   type: "gate", position: { x: C(18) + 60, y: R(4) },  data: { label: "Water Discharge", gateType: "output" } },
  { id: "g-offtake-meoh",  type: "gate", position: { x: C(18) + 60, y: R(5) + 40 }, data: { label: "MeOH Offtake", gateType: "output" } },

  // ═══════ ELECTRICITY — single bus carrier ═══════
  { id: "c-elec", type: "carrier", position: { x: C(4), y: 70 }, data: { label: "Electricity" } },

  // ═══════ INPUT CARRIERS ═══════
  { id: "c-seawater", type: "carrier", position: { x: C(1) + 60, y: R(3) }, data: { label: "Seawater" } },
  { id: "c-air",      type: "carrier", position: { x: C(1) + 60, y: R(5) }, data: { label: "Air" } },

  // ═══════ PUMP (col 2) — receives seawater, produces water ═══════
  { id: "e-pump", type: "equipment", position: { x: C(2), y: R(3) }, data: { label: "Pump", subtitle: "156 m³/h" } },

  // Water carrier out of pump — offset right to avoid overlapping pump (equipment width=150)
  { id: "c-pump-water", type: "carrier", position: { x: C(2) + 190, y: R(3) }, data: { label: "Water" } },

  // ═══════ DESALINATION (col 3) ═══════
  { id: "e-mvcd", type: "equipment", position: { x: C(3) + 40, y: R(2) },  data: { label: "Mechanical Vapor Compression Distillation", subtitle: "9.0 m³/h", customEquipment: true } },
  { id: "e-med",  type: "equipment", position: { x: C(3) + 40, y: R(3) },  data: { label: "Multi Effect Distillation", subtitle: "133 m³/h", customEquipment: true } },
  { id: "e-meh",  type: "equipment", position: { x: C(3) + 40, y: R(4) },  data: { label: "Multi Effect Humidification", subtitle: "14.8 m³/h", customEquipment: true } },

  // Water carriers out of desalination — offset right for clearance
  { id: "c-ultra-1", type: "carrier", position: { x: C(4) + 60, y: R(2) },       data: { label: "Water" } },
  { id: "c-ultra-2", type: "carrier", position: { x: C(4) + 60, y: R(3) + 60 },  data: { label: "Water" } },
  { id: "c-waste-w", type: "carrier", position: { x: C(12), y: R(4) + 60 },  data: { label: "Wastewater" } },

  // ═══════ VALVE (col 5) ═══════
  { id: "e-valve1", type: "equipment", position: { x: C(5) + 60, y: R(2) }, data: { label: "Valve" } },

  // Water after valve
  { id: "c-ultra-v1", type: "carrier", position: { x: C(6) + 60, y: R(2) }, data: { label: "Water" } },

  // ═══════ ELECTROLYZERS (col 7) ═══════
  { id: "e-ely1", type: "equipment", position: { x: C(7), y: R(1) }, data: { label: "Electrolyzer 1", subtitle: "40 bar" } },
  { id: "e-ely2", type: "equipment", position: { x: C(7), y: R(3) }, data: { label: "Electrolyzer 2", subtitle: "30 bar" } },

  // Hydrogen out of electrolyzers — clear of equipment
  { id: "c-h2-raw1", type: "carrier", position: { x: C(8) + 60, y: R(1) }, data: { label: "Hydrogen" } },
  { id: "c-h2-raw2", type: "carrier", position: { x: C(8) + 60, y: R(3) }, data: { label: "Hydrogen" } },

  // Oxygen (row 0) and Heat (row 4) — clear separation
  { id: "c-o2",   type: "carrier", position: { x: C(8) + 60, y: R(0) }, data: { label: "Oxygen" } },
  { id: "c-heat", type: "carrier", position: { x: C(5) + 60, y: R(3) - 40 }, data: { label: "Heat" } },

  // ═══════ DEOXIDATION (col 9) ═══════
  { id: "e-deoxo1", type: "equipment", position: { x: C(9) + 40, y: R(1) }, data: { label: "Deoxidation Unit" } },
  { id: "e-deoxo2", type: "equipment", position: { x: C(9) + 40, y: R(3) }, data: { label: "Deoxidation Unit" } },

  // Hydrogen after deoxo
  { id: "c-h2-deox1", type: "carrier", position: { x: C(10) + 60, y: R(1) }, data: { label: "Hydrogen" } },
  { id: "c-h2-deox2", type: "carrier", position: { x: C(10) + 60, y: R(3) }, data: { label: "Hydrogen" } },

  // ═══════ DRYERS (col 11) ═══════
  { id: "e-dryer1", type: "equipment", position: { x: C(11) + 40, y: R(1) }, data: { label: "Dryer Unit" } },
  { id: "e-dryer2", type: "equipment", position: { x: C(11) + 40, y: R(3) }, data: { label: "Dryer Unit" } },

  // Hydrogen after dryers
  { id: "c-h2-1", type: "carrier", position: { x: C(12) + 60, y: R(1) }, data: { label: "Hydrogen" } },
  { id: "c-h2-2", type: "carrier", position: { x: C(12) + 60, y: R(3) }, data: { label: "Hydrogen" } },

  // ═══════ HYDROGEN MERGE: Valve + Compressor (col 13) ═══════
  { id: "e-valve2",     type: "equipment", position: { x: C(13), y: R(1) + 40 }, data: { label: "Valve", subtitle: "40→35 bar" } },
  { id: "e-compressor", type: "equipment", position: { x: C(13), y: R(3) - 40 }, data: { label: "Hydrogen Compressor", subtitle: "30→35 bar" } },

  // Hydrogen after valve/compressor — clear of equipment
  { id: "c-h2-v2",   type: "carrier", position: { x: C(13) + 200, y: R(1) + 40 }, data: { label: "Hydrogen" } },
  { id: "c-h2-comp", type: "carrier", position: { x: C(13) + 200, y: R(3) - 40 }, data: { label: "Hydrogen" } },

  // ═══════ H2 STORAGE (col 15) ═══════
  { id: "e-h2-storage", type: "equipment", position: { x: C(15), y: R(2) }, data: { label: "Hydrogen Storage Tank", subtitle: "110 bar" } },

  // Stored hydrogen — clear offset
  { id: "c-h2-stored", type: "carrier", position: { x: C(15) + 200, y: R(2) }, data: { label: "Hydrogen" } },

  // ═══════ RE-ELECTRIFICATION (col 16) ═══════
  { id: "e-fuel-cell", type: "equipment", position: { x: C(16) + 20, y: R(0) + 40 }, data: { label: "Fuel Cell", subtitle: "1.5 MW" } },
  { id: "e-h2-motor",  type: "equipment", position: { x: C(16) + 20, y: R(1) + 40 }, data: { label: "Hydrogen Motor", subtitle: "0.8 MW" } },

  // ═══════ DOWNSTREAM OUTPUT CARRIERS — all at OUT_X, vertically parallel ═══════
  { id: "c-out-o2",      type: "carrier", position: { x: OUT_X, y: R(0) },       data: { label: "Oxygen" } },
  { id: "c-out-elec-fc", type: "carrier", position: { x: OUT_X, y: R(0) + 80 },  data: { label: "Electricity" } },
  { id: "c-out-elec-m",  type: "carrier", position: { x: OUT_X, y: R(1) + 40 },  data: { label: "Electricity" } },
  
  // c-out-heat removed — heat is redistributed internally
  // c-out-waste removed — wastewater goes directly to gate
  { id: "c-out-meoh",    type: "carrier", position: { x: OUT_X, y: R(5) + 40 },   data: { label: "Methanol" } },

  // ═══════ METHANOL PATH (rows 5–6) — spaced to avoid CO₂/mixer overlap ═══════
  { id: "c-coolwater", type: "carrier",   position: { x: C(4) + 60, y: R(5) + 30 }, data: { label: "Water" } },
  { id: "e-mixer",     type: "equipment", position: { x: C(6) + 20, y: R(5) + 40 }, data: { label: "Liquid Mixer" } },
  { id: "c-mixed-w",   type: "carrier",   position: { x: C(7) + 60, y: R(5) + 40 }, data: { label: "Water" } },

  // ═══════ DIRECT OCEAN CAPTURE (col 4, row 6) ═══════
  { id: "e-doc",       type: "equipment", position: { x: C(4), y: R(6) + 20 },      data: { label: "Direct Ocean Capture", subtitle: "0.3 t/h CO₂" } },
  { id: "c-co2-doc",   type: "carrier",   position: { x: C(5) + 60, y: R(6) + 20 }, data: { label: "CO₂" } },

  // ═══════ DAC (col 5, row 5) — separated from mixer row ═══════
  { id: "e-dac",       type: "equipment", position: { x: C(5), y: R(4) + 60 },      data: { label: "Direct Air Capture", subtitle: "0.5 t/h CO₂" } },
  { id: "c-co2-dac",   type: "carrier",   position: { x: C(6) + 60, y: R(4) + 60 }, data: { label: "CO₂" } },

  // Methanol reactor (col 9) — moved down for clearance
  { id: "e-meoh-plant", type: "equipment", position: { x: C(9), y: R(5) + 80 },     data: { label: "Methanol Synthesis Reactor" } },

  // Methanol out
  { id: "c-meoh", type: "carrier", position: { x: C(11), y: R(5) + 80 }, data: { label: "Methanol" } },

  // Wastewater from methanol
  // c-waste-meoh removed — methanol wastewater goes to main c-waste-w carrier
];

/**
 * Post-process edges: recalculate sourceHandle/targetHandle based on
 * actual node positions so connections use vertical ports when nodes
 * are stacked and horizontal ports when side-by-side.
 */
function optimizeEdgeHandles(nodes: Node[], edges: Edge[]): Edge[] {
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const dimsFor = (type?: string) => {
    if (type === "gate") return { w: 160, h: 80 };
    if (type === "carrier") return { w: 82, h: 82 };
    return { w: 140, h: 80 };
  };

  return edges.map((edge) => {
    const srcNode = nodeMap.get(edge.source);
    const tgtNode = nodeMap.get(edge.target);
    if (!srcNode || !tgtNode) return edge;

    const sd = dimsFor(srcNode.type);
    const td = dimsFor(tgtNode.type);
    const sourceSide = pickClosestAnchor(srcNode.position, sd, tgtNode.position, td);
    const targetSide = pickClosestAnchor(tgtNode.position, td, srcNode.position, sd);

    return {
      ...edge,
      sourceHandle: anchorHandleId(sourceSide, "source"),
      targetHandle: anchorHandleId(targetSide, "target"),
    };
  });
}


/* ════════════════════════════════════════════════════════════
   EDGES, No carrier→carrier links.
   ════════════════════════════════════════════════════════════ */

const _northseaEdgesRaw: Edge[] = [
  // ════════ ELECTRICITY — single carrier distributes to all equipment ════════
  feElec("e01", "g-power", "c-elec", 10, "MW", true),
  feElec("e03",  "c-elec", "e-mvcd",       0.5, "MW"),
  feElec("e03b", "c-elec", "e-med",        0.3, "MW", false, [0, 14]),
  feElec("e03c", "c-elec", "e-meh",        0.2, "MW", false, [0, 28]),
  feElec("e04",  "c-elec", "e-ely1",       4.2, "MW", false, [0, 42]),
  feElec("e04b", "c-elec", "e-ely2",       4.2, "MW", false, [0, 56]),
  feElec("e05",  "c-elec", "e-compressor", 0.6, "MW", false, [0, 70]),
  feElec("e06",  "c-elec", "e-dac",        0.3, "MW", false, [0, 84]),
  feElec("e06b", "c-elec", "e-doc",        0.2, "MW", false, [0, 98]),
  feElec("e06d", "c-elec", "e-valve1",      0.01, "MW", false, [0, 126]),
  feElec("e06e", "c-elec", "e-deoxo1",     0.05, "MW", false, [0, 140]),
  feElec("e06f", "c-elec", "e-deoxo2",     0.05, "MW", false, [0, 154]),
  feElec("e06g", "c-elec", "e-dryer1",     0.08, "MW", false, [0, 168]),
  feElec("e06h", "c-elec", "e-dryer2",     0.08, "MW", false, [0, 182]),
  feElec("e06i", "c-elec", "e-valve2",     0.01, "MW", false, [0, 196]),
  feElec("e06j", "c-elec", "e-h2-storage", 0.05, "MW", false, [0, 210]),
  feElec("e06k", "c-elec", "e-fuel-cell",  0.02, "MW", false, [0, 224]),
  feElec("e06l", "c-elec", "e-h2-motor",   0.02, "MW", false, [0, 238]),
  feElec("e06m", "c-elec", "e-mixer",      0.03, "MW", false, [0, 252]),
  feElec("e06n", "c-elec", "e-meoh-plant", 0.4,  "MW", false, [0, 266]),

  // ════════ SEAWATER → PUMP → WATER ════════
  fe("e10", "g-water",    "c-seawater",  CLR_SEA, 156, "m³/h", true),
  fe("e10b", "c-seawater", "e-pump",     CLR_SEA, 156, "m³/h"),
  fe("e10c", "e-pump",     "c-pump-water", CLR_ULTRA, 156, "m³/h"),

  // ════════ PUMP WATER → DESALINATION + DIRECT OCEAN CAPTURE ════════
  fe("e11", "c-pump-water", "e-mvcd",    CLR_ULTRA, 9.0, "m³/h", false, [0, -14]),
  fe("e12", "c-pump-water", "e-med",     CLR_ULTRA, 133, "m³/h"),
  fe("e13", "c-pump-water", "e-meh",     CLR_ULTRA, 14.8, "m³/h", false, [0, 14]),
  fe("e14", "c-pump-water", "e-doc",     CLR_ULTRA, 5.0, "m³/h", false, [0, 28]),

  // ════════ DESALINATION → WATER ════════
  fe("e20", "e-mvcd", "c-ultra-1", CLR_ULTRA, 1.1, "m³/h"),
  fe("e21", "e-med",  "c-ultra-1", CLR_ULTRA, 1.89, "m³/h", false, [0, 14]),
  fe("e22", "e-med",  "c-ultra-2", CLR_ULTRA, 0.97, "m³/h"),
  fe("e23", "e-meh",  "c-ultra-2", CLR_ULTRA, 0.43, "m³/h", false, [0, 14]),

  // ════════ WASTEWATER — collected from desalination, Fuel Cell, Hydrogen Motor, Compressor ════════
  fe("e24", "e-mvcd", "c-waste-w", CLR_WASTE_W, 7.9, "m³/h", false, [0, -14]),
  fe("e25", "e-med",  "c-waste-w", CLR_WASTE_W, 130.1, "m³/h"),
  fe("e26", "e-meh",  "c-waste-w", CLR_WASTE_W, 13.9, "m³/h", false, [0, 14]),
  fe("e24b", "e-fuel-cell",  "c-waste-w", CLR_WASTE_W, 2.5, "m³/h", false, [0, 28]),
  fe("e24c", "e-h2-motor",   "c-waste-w", CLR_WASTE_W, 1.8, "m³/h", false, [0, 42]),
  fe("e24d", "e-compressor", "c-waste-w", CLR_WASTE_W, 0.5, "m³/h", false, [0, 56]),
  // Wastewater → Water Discharge gate (direct)
  fe("e78b", "c-waste-w", "g-waste-water", CLR_WASTE_W, 165, "m³/h", true),

  // ════════ DESALINATION → COOLING WATER → LIQUID MIXER ════════
  fe("e27", "e-mvcd", "c-coolwater", CLR_COOL, 7.9, "m³/h", false, [0, -14]),
  fe("e28", "e-med",  "c-coolwater", CLR_COOL, 131.1, "m³/h"),
  fe("e29", "e-meh",  "c-coolwater", CLR_COOL, 14.3, "m³/h", false, [0, 14]),
  fe("e30", "c-coolwater", "e-mixer", CLR_COOL, 153.3, "m³/h"),

  // ════════ WATER → VALVE → ELECTROLYZERS ════════
  fe("e31", "c-ultra-1",  "e-valve1",   CLR_ULTRA, 2.99, "m³/h"),
  fe("e32", "e-valve1",   "c-ultra-v1", CLR_ULTRA, 2.99, "m³/h"),
  fe("e33", "c-ultra-v1", "e-ely1",     CLR_ULTRA, 1.26, "m³/h"),
  fe("e34", "c-ultra-2",  "e-ely2",     CLR_ULTRA, 1.26, "m³/h"),

  // ════════ ELECTROLYZERS → HYDROGEN → DEOXO ════════
  fe("e40", "e-ely1", "c-h2-raw1",   CLR_H2, 90, "kg/h"),
  fe("e41", "c-h2-raw1", "e-deoxo1", CLR_H2, 90, "kg/h"),
  fe("e42", "e-ely2", "c-h2-raw2",   CLR_H2, 90, "kg/h"),
  fe("e43", "c-h2-raw2", "e-deoxo2", CLR_H2, 90, "kg/h"),

  // ════════ DEOXO → HYDROGEN → DRYERS ════════
  fe("e44", "e-deoxo1", "c-h2-deox1", CLR_H2, 89.5, "kg/h"),
  fe("e45", "c-h2-deox1", "e-dryer1", CLR_H2, 89.5, "kg/h"),
  fe("e46", "e-deoxo2", "c-h2-deox2", CLR_H2, 89.5, "kg/h"),
  fe("e47", "c-h2-deox2", "e-dryer2", CLR_H2, 89.5, "kg/h"),

  // ════════ DRYERS → HYDROGEN ════════
  fe("e48", "e-dryer1", "c-h2-1", CLR_H2, 89, "kg/h"),
  fe("e49", "e-dryer2", "c-h2-2", CLR_H2, 89, "kg/h"),

  // ════════ HYDROGEN → VALVE2 / COMPRESSOR → carriers → STORAGE ════════
  fe("e50", "c-h2-1", "e-valve2",          CLR_H2, 89, "kg/h"),
  fe("e51", "c-h2-2", "e-compressor",      CLR_H2, 89, "kg/h"),
  fe("e52", "e-valve2",     "c-h2-v2",     CLR_H2, 89, "kg/h"),
  fe("e53", "e-compressor", "c-h2-comp",   CLR_H2, 89, "kg/h"),
  fe("e54a", "c-h2-v2",   "e-h2-storage",  CLR_H2, 89, "kg/h", false, [0, -14]),
  fe("e54b", "c-h2-comp", "e-h2-storage",  CLR_H2, 89, "kg/h", false, [0, 14]),

  // ════════ STORAGE → STORED HYDROGEN ════════
  fe("e55", "e-h2-storage", "c-h2-stored",  CLR_H2, 178, "kg/h"),


  // ════════ STORED H2 → Fuel Cell & H2 Motor ════════
  fe("e91", "c-h2-stored", "e-fuel-cell", CLR_H2, 30, "kg/h", false, [0, -14]),
  fe("e92", "c-h2-stored", "e-h2-motor",  CLR_H2, 20, "kg/h", false, [0, -28]),

  // ════════ STORED H2 → Methanol Reactor ════════
  fe("e58", "c-h2-stored", "e-meoh-plant", CLR_H2, 12, "kg/h", false, [0, 14]),

  // ════════ FUEL CELL / H2 MOTOR → output column carriers → Offtake Market gate ════════
  feElec("e95", "e-fuel-cell", "c-out-elec-fc", 1.5, "MW"),
  feElec("e96", "e-h2-motor",  "c-out-elec-m",  0.8, "MW"),
  feElec("e97", "c-out-elec-fc", "g-offtake-elec", 1.5, "MW", true, [0, -14]),
  feElec("e98", "c-out-elec-m",  "g-offtake-elec", 0.8, "MW", true, [0, 14]),

  // ════════ OXYGEN → output column carrier → Vent gate ════════
  fe("e70", "e-ely1", "c-o2", CLR_O2, 7450, "kg/h", false, [0, -14]),
  fe("e71", "e-ely2", "c-o2", CLR_O2, 7450, "kg/h", false, [0, 14]),
  fe("e72", "c-o2",   "c-out-o2",  CLR_O2, 14900, "kg/h"),
  fe("e73", "c-out-o2", "g-vent",  CLR_O2, 14900, "kg/h", true),

  // ════════ HEAT → redistributed to desalination units (MVCD, MED, MEH) ════════
  fe("e74", "e-ely1", "c-heat", CLR_HEAT, 1.2, "MW", false, [0, -14]),
  fe("e75", "e-ely2", "c-heat", CLR_HEAT, 1.2, "MW", false, [0, 14]),
  fe("e76a", "c-heat", "e-mvcd", CLR_HEAT, 0.4, "MW", false, [0, -14]),
  fe("e76b", "c-heat", "e-med",  CLR_HEAT, 1.2, "MW"),
  fe("e76c", "c-heat", "e-meh",  CLR_HEAT, 0.8, "MW", false, [0, 14]),

  // ════════ METHANOL WASTEWATER → main wastewater carrier ════════
  fe("e90", "e-meoh-plant", "c-waste-w", CLR_WASTE_W, 8.43, "m³/h", false, [0, 70]),

  // ════════ AIR → DAC → CO₂ ════════
  fe("e81", "g-air", "c-air", CLR_AIR, 5000, "m³/h", true),
  fe("e82", "c-air", "e-dac", CLR_AIR, 5000, "m³/h"),
  fe("e83", "e-dac", "c-co2-dac", CLR_CO2, 0.5, "t/h"),

  // ════════ DIRECT OCEAN CAPTURE → CO₂ ════════
  fe("e83b", "e-doc", "c-co2-doc", CLR_CO2, 0.3, "t/h"),

  // ════════ CO₂ (both sources) → METHANOL REACTOR ════════
  fe("e86a", "c-co2-dac", "e-meoh-plant", CLR_CO2, 0.5, "t/h", false, [0, -14]),
  fe("e86b", "c-co2-doc", "e-meoh-plant", CLR_CO2, 0.3, "t/h", false, [0, 14]),

  // ════════ LIQUID MIXER → WATER → METHANOL PLANT ════════
  fe("e84", "e-mixer",   "c-mixed-w",    CLR_COOL, 153.3, "m³/h"),
  fe("e85", "c-mixed-w", "e-meoh-plant", CLR_COOL, 2.77, "m³/h"),

  // ════════ METHANOL → output column carrier → MeOH Offtake gate ════════
  fe("e87", "e-meoh-plant", "c-meoh",         CLR_MEOH, 1.2, "t/h"),
  fe("e88", "c-meoh",       "c-out-meoh",     CLR_MEOH, 1.2, "t/h"),
  fe("e89", "c-out-meoh",   "g-offtake-meoh", CLR_MEOH, 1.2, "t/h", true),
];

/** Exported edges — handles optimized based on actual node positions */
export const northseaEdges: Edge[] = optimizeEdgeHandles(northseaNodes, _northseaEdgesRaw);
