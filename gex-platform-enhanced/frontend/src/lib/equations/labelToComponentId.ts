/**
 * Maps equipment labels (as shown in the canvas) to the equation-library
 * component_id (E1, E2, …) so that each equipment only sees its OWN equations.
 *
 * The mapping is derived from the descriptions of the first equation of each
 * component in `public/equation-library/equations.json`.
 *
 * If a label is not in this map, the EquationsTab falls back to "no equations
 * available" for that equipment.
 */
export const LABEL_TO_COMPONENT_ID: Record<string, string> = {
  // E1–E7 — Electrical conversion / storage
  "Power Rectifier": "E1",
  "Inverter": "E2",
  "Transformer": "E3",
  "Electrical Switchgear": "E4",
  "Motor Control Center": "E5",
  "Uninterruptible Power Supply": "E6",
  "Battery Energy Storage System": "E7",

  // E8–E20 — Piping & distribution
  "Pipeline": "E8",
  "Compressor Station": "E9",
  "Header": "E10",
  "Valve": "E11",
  "JT Valve": "E12",
  "Control Valve": "E13",
  "Check Valve": "E14",
  "Pressure Regulating Valve": "E15",
  "Pressure Relief Valve": "E16",
  "Rupture Disc": "E17",
  "Orifice": "E18",
  "Sampling System": "E19",
  "Metering System": "E20",

  // E21–E30 — Compressors & rotating equipment
  "Hydrogen Compressor": "E21",
  "CO2 Compressor": "E22",
  "Syngas Compressor": "E23",
  "Natural Gas Compressor": "E24",
  "Air Compressor": "E25",
  "Instrument Air Compressor": "E26",
  "Refrigeration Compressor": "E27",
  "Pump": "E28",
  "Blower": "E29",
  "Electric Generator": "E30",
  "Engine Generator Set": "E30",

  // E31–E48 — Heat exchange & thermal
  "Fired Heater": "E31",
  "Heat Exchanger": "E32",
  "Air Cooler": "E33",
  "Chiller": "E34",
  "Cooling Tower": "E35",
  "Steam Boiler": "E36",
  "Steam Turbine": "E37",
  "Gas Turbine": "E38",
  "Heat Recovery Steam Generator": "E39",
  "Steam Drum": "E40",
  "Deaerator": "E41",
  "Condensate Polishing Unit": "E42",
  "Thermal Oil Heater": "E43",
  "Flue Gas Cooler": "E45",
  "Waste Heat Recovery Unit": "E46",
  "Organic Rankine Cycle Unit": "E47",
  "Refrigeration System": "E48",

  // E49–E62 — Separation & purification
  "Separator": "E49",
  "Filter": "E50",
  "Electrostatic Precipitator": "E51",
  "Baghouse": "E52",
  "Scrubber": "E53",
  "Hydrogen Purification Unit": "E54",
  "CO2 Purification Unit": "E55",
  "Syngas Cleanup Unit": "E56",
  "Sulfur Removal Unit": "E57",
  "H2S Scavenger Bed": "E58",
  "Amine Treating Unit": "E59",
  "Adsorption Purification Unit": "E60",
  "Dryer Unit": "E61",
  "Deoxidation Unit": "E62",
  "Solvent Regeneration Unit": "E63",

  // E64–E77 — Water treatment
  "Water Treatment Unit": "E64",
  "Reverse Osmosis Unit": "E65",
  "Demineralization Unit": "E66",
  "Ion Exchange Unit": "E67",
  "Ultrafiltration Unit": "E68",
  "Activated Carbon Filter": "E69",
  "Water Softener": "E70",
  "Cooling Water Treatment Unit": "E71",
  "Effluent Neutralization Unit": "E72",
  "Wastewater Treatment Unit": "E73",
  "Sludge Dewatering Unit": "E74",
  "Brine Concentrator": "E75",
  "Evaporator": "E76",
  "Crystallizer": "E77",

  // E78 — Electrolyzer
  "Electrolyzer": "E78",

  // E79–E81 — Air/gas separation
  "Air Separation Unit": "E79",
  "Nitrogen Generation Unit": "E80",
  "Oxygen Generation Unit": "E81",

  // E82–E85 — Carbon capture
  "DAC Contactor": "E82",
  "Direct Air Capture": "E82",
  "DAC Regeneration Unit": "E83",
  "Direct Ocean Capture": "E84",
  "CO2 Capture Unit": "E85",

  // E86–E92 — Biomass & thermochemical
  "Gasifier": "E86",
  "Pyrolysis Reactor": "E87",
  "Hydrothermal Liquefaction Unit": "E88",
  "Torrefaction Unit": "E89",
  "Biomass Combustion Unit": "E90",
  "Anaerobic Digester": "E91",
  "Biogas Upgrading Unit": "E92",

  // E93–E105 — Reactors & synthesis
  "Reforming Reactor": "E93",
  "Water Gas Shift Reactor": "E94",
  "Reverse Water Gas Shift Reactor": "E95",
  "Methanation Reactor": "E96",
  "Fischer Tropsch Reactor": "E97",
  "Methanol Synthesis Reactor": "E98",
  "DME Synthesis Reactor": "E99",
  "Ammonia Synthesis Reactor": "E100",
  "Hydrotreater": "E101",
  "Hydrocracker": "E102",
  "Hydroisomerization Reactor": "E103",
  "Alkylation Reactor": "E104",
  "Polymerization Reactor": "E105",

  // E106–E108 — Columns & absorption
  "Distillation Column": "E106",
  "Absorber Column": "E107",
  "Stripper Column": "E108",

  // E109–E118 — Storage tanks
  "Ammonia Storage Tank": "E109",
  "Hydrogen Storage Tank": "E110",
  "CO2 Storage Tank": "E111",
  "Natural Gas Storage Tank": "E112",
  "CNG Storage Tank": "E113",
  "LPG Storage Tank": "E114",
  "Hydrocarbon Storage Tank": "E115",
  "Methanol Storage Tank": "E116",
  "Ethanol Storage Tank": "E117",
  "Buffer Tank": "E118",

  // E119–E122 — Loading & logistics
  "Hydrogen Tube Trailer Loading Unit": "E119",
  "Tank Truck Loading Unit": "E120",
  "Rail Loading Unit": "E121",
  "Ship Loading Unit": "E122",

  // E123–E125 — Liquefaction
  "CO2 Liquefaction Unit": "E123",
  "Hydrogen Liquefaction Unit": "E124",
  "Natural Gas Liquefaction Unit": "E125",

  // E126–E135 — Safety & emissions
  "Thermal Oxidizer": "E126",
  "Catalytic Oxidizer": "E127",
  "Flare System": "E128",
  "Vent Stack": "E129",
  "Pressure Relief System": "E130",
  "Blowdown System": "E131",
  "Inerting System": "E132",
  "Nitrogen Blanketing System": "E133",
  "Gas Detection System": "E134",
  "Fire Suppression System": "E135",

  // E136–E153 — Feedstock handling
  "Biomass Receiving Station": "E136",
  "Biomass Storage Silo": "E137",
  "Biomass Dry Storage Bunker": "E138",
  "Biomass Slurry Tank": "E139",
  "Feedstock Blending Unit": "E140",
  "Gas Mixer": "E141",
  "Liquid Mixer": "E142",
  "Feeder Hopper": "E143",
  "Screw Conveyor": "E144",
  "Belt Conveyor": "E145",
  "Bucket Elevator": "E146",
  "Size Reduction Mill": "E147",
  "Shredder": "E148",
  "Chip Screen": "E149",
  "Magnetic Separator": "E150",
  "Solids Dryer": "E151",
  "Pelletizer": "E152",
  "Briquetter": "E153",

  // E154–E165 — Misc / late additions
  "Flash Separator": "E154",
  "Expander": "E155",
  "Flare Separator": "E156",
  "Fuel Cell": "E157",
  "VFD Drive": "E158",
  "Firewater Pump Unit": "E159",
  "Oil Water Separator": "E160",
  "Cooling Tower Makeup Water System": "E161",
  "Flue Gas Blower": "E162",
  "Mercury Removal Unit": "E163",
  "Mechanical Vapor Compression Distillation": "E164",
  "Multi Effect Distillation": "E165",
  "Multi Effect Humidification": "E165",

  // Aliases / not in equipment list but commonly seen on canvas
  "Hydrogen Motor": "E158",
  "Re-Electrification Unit": "E157",
  "Demin Water System": "E66",
  "RO System": "E65",
  "PSA Unit": "E60",
  "TSA Unit": "E60",
  "Deoxo Unit": "E62",
  "Gas Dryer": "E61",
  "Molecular Sieve": "E61",
  "Amine Unit": "E59",
  "CO2 Absorber": "E107",
  "ASU": "E79",
  "CO2 Capture Regeneration": "E83",
  "Liquefaction Unit": "E124",
  "LH2 Liquefaction": "E124",
  "LNG Liquefaction": "E125",
  "Fractionation Column": "E106",
  "Rotary Dryer": "E151",
};

export function getComponentIdForLabel(label: string): string | null {
  return LABEL_TO_COMPONENT_ID[label] ?? null;
}