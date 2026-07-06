/**
 * Comprehensive Plant Component Database
 * Sourced from equipment_list.xlsx, carrier_list.xlsx, and gate definitions.
 */

export interface EquipmentDef {
  id: string;
  label: string;
  category: string;
}

export interface CarrierDef {
  id: string;
  label: string;
  carrierFunction: string;
  physicalStates: string;
  category: string;
}

export interface GateDef {
  id: string;
  label: string;
  gateType: "input" | "output";
}

/* ── Equipment (163 items, grouped by subcategory) ── */

const equipmentCategories: Record<string, string[]> = {
  "Electrical Systems": [
    "Power Rectifier", "Inverter", "Transformer", "Electrical Switchgear",
    "Motor Control Center", "Uninterruptible Power Supply", "Battery Energy Storage System", "VFD Drive",
    "Hydrogen Motor", "Re-Electrification Unit",
  ],
  "Piping & Distribution": [
    "Pipeline", "Compressor Station", "Header", "Valve", "JT Valve",
    "Control Valve", "Check Valve", "Pressure Regulating Valve", "Pressure Relief Valve",
    "Rupture Disc", "Orifice", "Sampling System", "Metering System",
  ],
  "Compressors & Rotating": [
    "Hydrogen Compressor", "CO2 Compressor", "Syngas Compressor", "Natural Gas Compressor",
    "Air Compressor", "Instrument Air Compressor", "Refrigeration Compressor",
    "Pump", "Blower", "Electric Generator", "Engine Generator Set", "Expander", "Flue Gas Blower",
  ],
  "Heat Exchange & Thermal": [
    "Heat Exchanger", "Air Cooler", "Chiller", "Cooling Tower",
    "Steam Boiler", "Steam Turbine", "Gas Turbine", "Heat Recovery Steam Generator",
    "Steam Drum", "Deaerator", "Condensate Polishing Unit", "Thermal Oil Heater",
    "Fired Heater", "Flue Gas Cooler", "Waste Heat Recovery Unit",
    "Organic Rankine Cycle Unit", "Refrigeration System",
  ],
  "Separation & Purification": [
    "Separator", "Filter", "Electrostatic Precipitator", "Baghouse", "Scrubber",
    "Hydrogen Purification Unit", "CO2 Purification Unit", "Syngas Cleanup Unit",
    "Sulfur Removal Unit", "H2S Scavenger Bed", "Amine Treating Unit",
    "Adsorption Purification Unit", "Dryer Unit", "Deoxidation Unit",
    "Solvent Regeneration Unit", "Flash Separator", "Flare Separator",
    "Mercury Removal Unit", "Oil Water Separator",
  ],
  "Water Treatment": [
    "Water Treatment Unit", "Reverse Osmosis Unit", "Demineralization Unit",
    "Ion Exchange Unit", "Ultrafiltration Unit", "Activated Carbon Filter",
    "Water Softener", "Cooling Water Treatment Unit", "Effluent Neutralization Unit",
    "Wastewater Treatment Unit", "Sludge Dewatering Unit", "Brine Concentrator",
    "Evaporator", "Crystallizer", "Cooling Tower Makeup Water System",
    "Mechanical Vapor Compression Distillation", "Multi Effect Distillation", "Multi Effect Humidification",
  ],
  "Electrolysis & Gas Generation": [
    "Electrolyzer", "Air Separation Unit", "Nitrogen Generation Unit",
    "Oxygen Generation Unit", "Fuel Cell",
  ],
  "Carbon Capture": [
    "DAC Contactor", "Direct Air Capture", "DAC Regeneration Unit", "Direct Ocean Capture", "CO2 Capture Unit",
  ],
  "Biomass & Thermochemical": [
    "Gasifier", "Pyrolysis Reactor", "Hydrothermal Liquefaction Unit",
    "Torrefaction Unit", "Biomass Combustion Unit", "Anaerobic Digester",
    "Biogas Upgrading Unit",
  ],
  "Reactors & Synthesis": [
    "Reforming Reactor", "Water Gas Shift Reactor", "Reverse Water Gas Shift Reactor",
    "Methanation Reactor", "Fischer Tropsch Reactor", "Methanol Synthesis Reactor",
    "DME Synthesis Reactor", "Ammonia Synthesis Reactor", "Hydrotreater",
    "Hydrocracker", "Hydroisomerization Reactor", "Alkylation Reactor",
    "Polymerization Reactor",
  ],
  "Columns & Absorption": [
    "Distillation Column", "Absorber Column", "Stripper Column",
  ],
  "Storage": [
    "Ammonia Storage Tank", "Hydrogen Storage Tank", "CO2 Storage Tank",
    "Natural Gas Storage Tank", "CNG Storage Tank", "LPG Storage Tank",
    "Hydrocarbon Storage Tank", "Methanol Storage Tank", "Ethanol Storage Tank", "Buffer Tank",
  ],
  "Loading & Logistics": [
    "Hydrogen Tube Trailer Loading Unit", "Tank Truck Loading Unit",
    "Rail Loading Unit", "Ship Loading Unit",
  ],
  "Liquefaction": [
    "CO2 Liquefaction Unit", "Hydrogen Liquefaction Unit", "Natural Gas Liquefaction Unit",
  ],
  "Safety & Emissions": [
    "Thermal Oxidizer", "Catalytic Oxidizer", "Flare System", "Vent Stack",
    "Pressure Relief System", "Blowdown System", "Inerting System",
    "Nitrogen Blanketing System", "Gas Detection System", "Fire Suppression System",
    "Firewater Pump Unit",
  ],
  "Feedstock Handling": [
    "Biomass Receiving Station", "Biomass Storage Silo", "Biomass Dry Storage Bunker",
    "Biomass Slurry Tank", "Feedstock Blending Unit", "Gas Mixer", "Liquid Mixer",
    "Feeder Hopper", "Screw Conveyor", "Belt Conveyor", "Bucket Elevator",
    "Size Reduction Mill", "Shredder", "Chip Screen", "Magnetic Separator",
    "Solids Dryer", "Pelletizer", "Briquetter",
  ],
};

let eqCounter = 1;
export const equipmentDatabase: EquipmentDef[] = Object.entries(equipmentCategories).flatMap(
  ([category, items]) =>
    items.map((label) => ({
      id: `E${eqCounter++}`,
      label,
      category,
    }))
);

/* ── Carriers (100 items, grouped by function) ── */

const carrierRaw: [string, string, string, string][] = [
  ["C1","Hydrogen","fuel,process gas","gas,liquid"],
  ["C2","Ammonia","fuel,chemical reagent","liquid,gas"],
  ["C3","Methanol","fuel,chemical reagent","liquid"],
  ["C4","Methane","fuel,process gas","gas,liquid"],
  ["C5","Gasoline","fuel","liquid"],
  ["C6","Diesel","fuel","liquid"],
  ["C7","Kerosene","fuel","liquid"],
  ["C8","Naphtha","fuel,feedstock","liquid"],
  ["C9","Ethanol","fuel,chemical reagent","liquid"],
  ["C10","Propane","fuel","gas,liquid"],
  ["C11","Butane","fuel","gas,liquid"],
  ["C12","Electricity","energy","energy"],
  ["C13","Carbon Dioxide","process gas,product,waste","gas,liquid"],
  ["C14","Carbon Monoxide","process gas,feedstock","gas"],
  ["C15","Air","utility,process gas","gas"],
  ["C16","Flue gas","waste,process gas","gas"],
  ["C17","Solvent","chemical reagent","liquid"],
  ["C18","Syngas","feedstock,process gas","gas"],
  ["C19","Water","utility,process gas","liquid"],
  ["C20","Heat","energy","energy"],
  ["C21","Process Steam","utility,energy","gas"],
  ["C22","Compressed Air","utility","gas"],
  ["C23","Heavy Fuel Oil","fuel","liquid"],
  ["C24","Light Fuel Oil","fuel","liquid"],
  ["C25","LPG","fuel","gas,liquid"],
  ["C26","Hard Coal","fuel","solid"],
  ["C27","Lignite","fuel","solid"],
  ["C28","Chlorine","chemical reagent","gas,liquid"],
  ["C29","Hydrogen Chloride","chemical reagent","gas"],
  ["C30","Nitrogen","utility,process gas","gas,liquid"],
  ["C31","Oxygen","utility,process gas","gas,liquid"],
  ["C32","Phosphoric Acid","chemical reagent","liquid"],
  ["C33","Sodium Hydroxide","chemical reagent","solid,liquid"],
  ["C34","Sodium Chloride","chemical reagent","solid"],
  ["C35","Calcium Carbonate","material","solid"],
  ["C36","Sulfur","chemical reagent,material","solid"],
  ["C37","Benzene","chemical reagent,feedstock","liquid"],
  ["C38","Carbonyl Sulfide","chemical reagent","gas"],
  ["C39","Ethene","feedstock","gas,liquid"],
  ["C40","Propene","feedstock","gas,liquid"],
  ["C41","Vinyl Chloride Monomer","feedstock","gas,liquid"],
  ["C42","Titanium Dioxide","material","solid"],
  ["C43","Used Cooking Oil","feedstock","liquid"],
  ["C44","Animal Fats","feedstock","solid,liquid"],
  ["C45","Animal Manure","feedstock","slurry"],
  ["C46","Sewage Sludge","feedstock,waste","slurry"],
  ["C47","Wastewater","waste,utility","liquid"],
  ["C48","Algae","feedstock","slurry"],
  ["C49","Straw","feedstock","solid"],
  ["C50","Bagasse","feedstock","solid"],
  ["C51","Grape Marcs","feedstock","solid"],
  ["C52","Wine Lees","feedstock","slurry"],
  ["C53","Nut Shells","feedstock","solid"],
  ["C54","Husks","feedstock","solid"],
  ["C55","Cobs","feedstock","solid"],
  ["C56","Forest Residues","feedstock","solid"],
  ["C57","Wood Chips","feedstock","solid"],
  ["C58","Bark","feedstock","solid"],
  ["C59","Sawdust","feedstock","solid"],
  ["C60","Wood Shavings","feedstock","solid"],
  ["C61","Black Liquor","feedstock,industrial stream","liquid"],
  ["C62","Fibre Sludge","feedstock,industrial stream","slurry"],
  ["C63","Lignin","feedstock","solid"],
  ["C64","Tall Oil","feedstock,industrial stream","liquid"],
  ["C65","Tall Oil Pitch","feedstock,industrial stream","solid"],
  ["C66","Crude Glycerine","feedstock,industrial stream","liquid"],
  ["C67","Palm Oil Mill Effluent","feedstock,waste","liquid"],
  ["C68","Catch Crops","feedstock","solid"],
  ["C69","Cover Crops","feedstock","solid"],
  ["C70","Damaged Crops","feedstock","solid"],
  ["C71","Gypsum","material","solid"],
  ["C72","Hydrated Lime","material,chemical reagent","solid"],
  ["C73","Kaolin","material","solid"],
  ["C74","Sodium Activated Bentonite","material","solid"],
  ["C75","Sand","material","solid"],
  ["C76","Crushed Stone","material","solid"],
  ["C77","Gravel","material","solid"],
  ["C78","Portland Cement","material","solid"],
  ["C79","Ash","waste,industrial stream","solid"],
  ["C80","Natural Gas","fuel,process gas","gas,liquid"],
  ["C81","Ethane","fuel,feedstock","gas,liquid"],
  ["C82","DME","fuel,chemical reagent","liquid,gas"],
  ["C83","FT Wax","product","liquid,solid"],
  ["C84","Bio Oil","product,feedstock","liquid"],
  ["C85","Biochar","product,material","solid"],
  ["C86","Tar","waste,feedstock","liquid,solid"],
  ["C87","Slag","waste,material","solid"],
  ["C88","Polymer","product,material","solid"],
  ["C89","Cyclohexane","product,feedstock","liquid"],
  ["C90","Hydrogen Sulfide","waste,process gas","gas"],
  ["C91","Hydrogen Peroxide","chemical reagent","liquid"],
  ["C92","Sulfur Dioxide","waste,process gas","gas"],
  ["C93","Nitrogen Oxides","waste,process gas","gas"],
  ["C94","Cooling Water","utility","liquid"],
  ["C95","Brine","waste,utility","liquid"],
  ["C96","Nitric Acid","chemical reagent","liquid"],
  ["C97","Sulfuric Acid","chemical reagent","liquid"],
  ["C98","Condensate","utility,waste","liquid"],
  ["C99","Ammonium Hydroxide","chemical reagent","liquid"],
  ["C100","Oxygenated Hydrocarbons","product,feedstock","liquid"],
];

function categorizeCarrier(fn: string): string {
  if (fn.includes("energy")) return "Energy";
  if (fn.includes("fuel")) return "Fuels";
  if (fn.includes("utility")) return "Utilities";
  if (fn.includes("feedstock")) return "Feedstocks";
  if (fn.includes("chemical reagent")) return "Chemicals";
  if (fn.includes("waste")) return "Waste Streams";
  if (fn.includes("product")) return "Products";
  if (fn.includes("process gas")) return "Process Gases";
  if (fn.includes("material")) return "Materials";
  return "Other";
}

export const carrierDatabase: CarrierDef[] = carrierRaw.map(([id, label, fn, states]) => ({
  id,
  label,
  carrierFunction: fn,
  physicalStates: states,
  category: categorizeCarrier(fn),
}));

/* ── Gates (15 items) ── */
// Note: in the spreadsheet, "output gate" means it provides TO the system (= our "input")
// and "input gate" means it receives FROM the system (= our "output")
export const gateDatabase: GateDef[] = [
  { id: "G1", label: "Power Supply", gateType: "input" },
  { id: "G2", label: "Fuel Supply", gateType: "input" },
  { id: "G3", label: "Biomass Supply", gateType: "input" },
  { id: "G4", label: "Chemical Supply", gateType: "input" },
  { id: "G5", label: "Gas Supply", gateType: "input" },
  { id: "G6", label: "Water Supply", gateType: "input" },
  { id: "G7", label: "CO₂ Supply", gateType: "input" },
  { id: "G8", label: "CO₂ Offtake", gateType: "output" },
  { id: "G9", label: "Offtake Market", gateType: "output" },
  { id: "G10", label: "Waste Export", gateType: "output" },
  { id: "G11", label: "Vent", gateType: "output" },
  { id: "G12", label: "Heat Supply", gateType: "input" },
  { id: "G13", label: "Heat Offtake", gateType: "output" },
  { id: "G14", label: "Water Discharge", gateType: "output" },
  { id: "G15", label: "Air Intake", gateType: "input" },
];

/* ── Helpers ── */

/** Get unique equipment categories */
export const getEquipmentCategories = () =>
  [...new Set(equipmentDatabase.map((e) => e.category))];

/** Get unique carrier categories */
export const getCarrierCategories = () =>
  [...new Set(carrierDatabase.map((c) => c.category))];
