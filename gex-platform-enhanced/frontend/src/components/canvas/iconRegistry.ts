/**
 * Centralized icon registry for all plant components.
 * Uses ISO 10628 / IEC 62424 inspired P&ID symbols for equipment,
 * and simplified process icons for carriers and gates.
 * @version 2 — P&ID style
 */
import {
  Zap, Droplets, Atom, Wind, Thermometer, Flame, FlaskConical, Waves,
  CloudRain, Leaf,
  Snowflake, Fuel, Sprout, Recycle, Wheat, TreePine, TestTube, Beaker,
  Layers, CloudFog, FlaskRound, CircleDashed,
  type LucideIcon,
} from "lucide-react";

import {
  PidElectrolyzer,
  PidWaterTreatment,
  PidFilter,
  PidCompressor,
  PidPump,
  PidBlower,
  PidTank,
  PidReactor,
  PidReformer,
  PidFuelCell,
  PidHeatExchanger,
  PidCooler,
  PidBoiler,
  PidTurbine,
  PidMixer,
  PidSeparator,
  PidColumn,
  PidValve,
  PidDac,
  PidGasifier,
  PidDryer,
  PidFlare,
  PidLoading,
  PidConveyor,
  PidPipeline,
  PidMeter,
  PidSafety,
  PidGateInput,
  PidGateOutput,
  PidCarrier,
} from "./pidIcons";

// Type alias — our P&ID SVGs match the LucideIcon call signature
type IconComponent = LucideIcon | typeof PidElectrolyzer;

// ══════════════════════════════════════════════
// EQUIPMENT ICONS — keyed by equipment label
// ══════════════════════════════════════════════
export const equipmentIcons: Record<string, IconComponent> & { __fallback?: (label: string) => IconComponent | undefined } = {
  // Electrolyzers
  "Electrolyzer": PidElectrolyzer,
  "Electrolyzer 1": PidElectrolyzer,
  "Electrolyzer 2": PidElectrolyzer,
  // Water treatment
  "Water Treatment Unit": PidWaterTreatment,
  "Mechanical Vapor Compression Distillation": PidWaterTreatment,
  "Multi Effect Distillation": PidWaterTreatment,
  "Multi Effect Humidification": PidWaterTreatment,
  "Reverse Osmosis Unit": PidWaterTreatment,
  "Demineralization Unit": PidWaterTreatment,
  "Ion Exchange Unit": PidWaterTreatment,
  "Ultrafiltration Unit": PidFilter,
  "Water Softener": PidWaterTreatment,
  "Cooling Water Treatment Unit": PidWaterTreatment,
  "Effluent Neutralization Unit": PidWaterTreatment,
  "Wastewater Treatment Unit": PidWaterTreatment,
  "Brine Concentrator": PidWaterTreatment,
  "Evaporator": PidBoiler,
  "Crystallizer": PidReactor,
  "Cooling Tower Makeup Water System": PidWaterTreatment,
  // Purification
  "Hydrogen Purifier": PidFilter,
  "Hydrogen Purification Unit": PidFilter,
  "CO2 Purification Unit": PidFilter,
  "Syngas Cleanup Unit": PidFilter,
  "Sulfur Removal Unit": PidFilter,
  "H2S Scavenger Bed": PidFilter,
  "Amine Treating Unit": PidColumn,
  "Adsorption Purification Unit": PidFilter,
  "Mercury Removal Unit": PidFilter,
  "Deoxidation Unit": PidFilter,
  "Dryer Unit": PidDryer,
  "Deoxidation & Dryer Unit": PidFilter,
  "Activated Carbon Filter": PidFilter,
  "Filter": PidFilter,
  "Electrostatic Precipitator": PidFilter,
  "Baghouse": PidFilter,
  "Scrubber": PidColumn,
  // Compressors & rotating
  "Compressor": PidCompressor,
  "Hydrogen Compressor": PidCompressor,
  "H₂ Compressor": PidCompressor,
  "CO2 Compressor": PidCompressor,
  "Syngas Compressor": PidCompressor,
  "Natural Gas Compressor": PidCompressor,
  "Air Compressor": PidCompressor,
  "Instrument Air Compressor": PidCompressor,
  "Refrigeration Compressor": PidCompressor,
  "Pump": PidPump,
  "Blower": PidBlower,
  "Flue Gas Blower": PidBlower,
  "Electric Generator": PidTurbine,
  "Engine Generator Set": PidTurbine,
  "Expander": PidTurbine,
  // Storage
  "Buffer": PidTank,
  "Buffer Tank": PidTank,
  "Hydrogen Storage Tank": PidTank,
  "H₂ Storage Tank": PidTank,
  "Ammonia Storage Tank": PidTank,
  "CO2 Storage Tank": PidTank,
  "Natural Gas Storage Tank": PidTank,
  "CNG Storage Tank": PidTank,
  "LPG Storage Tank": PidTank,
  "Hydrocarbon Storage Tank": PidTank,
  "Methanol Storage Tank": PidTank,
  "Ethanol Storage Tank": PidTank,
  // Reactors & synthesis
  "Reforming Reactor": PidReformer,
  "Water Gas Shift Reactor": PidReactor,
  "Reverse Water Gas Shift Reactor": PidReactor,
  "Fischer Tropsch Reactor": PidReactor,
  "Methanol Synthesis Reactor": PidReactor,
  "DME Synthesis Reactor": PidReactor,
  "Ammonia Synthesis Reactor": PidReactor,
  "Methanation Reactor": PidReactor,
  "Hydrotreater": PidReactor,
  "Hydrocracker": PidReactor,
  "Hydroisomerization Reactor": PidReactor,
  "Alkylation Reactor": PidReactor,
  "Polymerization Reactor": PidReactor,
  // Power & re-electrification
  "Fuel Cell": PidFuelCell,
  "H2 Motor": PidTurbine,
  "Hydrogen Motor": PidTurbine,
  "Re-Electrification Unit": PidFuelCell,
  "Power Rectifier": PidFuelCell,
  "Inverter": PidFuelCell,
  "Transformer": PidFuelCell,
  "Electrical Switchgear": PidFuelCell,
  "Motor Control Center": PidFuelCell,
  "Uninterruptible Power Supply": PidFuelCell,
  "Battery Energy Storage System": PidFuelCell,
  "VFD Drive": PidFuelCell,
  // Heat exchange & thermal
  "Heat Exchanger": PidHeatExchanger,
  "Air Cooler": PidCooler,
  "Chiller": PidCooler,
  "Cooling Tower": PidCooler,
  "Steam Boiler": PidBoiler,
  "Steam Turbine": PidTurbine,
  "Gas Turbine": PidTurbine,
  "Heat Recovery Steam Generator": PidHeatExchanger,
  "Steam Drum": PidTank,
  "Deaerator": PidTank,
  "Condensate Polishing Unit": PidFilter,
  "Thermal Oil Heater": PidBoiler,
  "Fired Heater": PidBoiler,
  "Flue Gas Cooler": PidCooler,
  "Waste Heat Recovery Unit": PidHeatExchanger,
  "Organic Rankine Cycle Unit": PidTurbine,
  "Refrigeration System": PidCooler,
  // Mixing & separation
  "Gas Mixer": PidMixer,
  "Liquid Mixer": PidMixer,
  "Separator": PidSeparator,
  "Flash Separator": PidSeparator,
  "Flare Separator": PidSeparator,
  "Oil Water Separator": PidSeparator,
  // Carbon capture
  "DAC Contactor": PidDac,
  "Direct Air Capture": PidDac,
  "DAC Regeneration Unit": PidDac,
  "Direct Ocean Capture": PidDac,
  "CO2 Capture Unit": PidDac,
  // Biomass
  "Gasifier": PidGasifier,
  "Pyrolysis Reactor": PidGasifier,
  "Hydrothermal Liquefaction Unit": PidReactor,
  "Torrefaction Unit": PidBoiler,
  "Biomass Combustion Unit": PidBoiler,
  "Anaerobic Digester": PidReactor,
  "Biogas Upgrading Unit": PidFilter,
  // Columns
  "Distillation Column": PidColumn,
  "Absorber Column": PidColumn,
  "Stripper Column": PidColumn,
  // Valves
  "Valve": PidValve,
  "JT Valve": PidValve,
  "Control Valve": PidValve,
  "Check Valve": PidValve,
  "Pressure Regulating Valve": PidValve,
  "Pressure Relief Valve": PidValve,
  "Rupture Disc": PidSafety,
  // Safety
  "Thermal Oxidizer": PidBoiler,
  "Catalytic Oxidizer": PidBoiler,
  "Flare System": PidFlare,
  "Vent Stack": PidFlare,
  "Pressure Relief System": PidSafety,
  "Blowdown System": PidSafety,
  "Inerting System": PidSafety,
  "Nitrogen Blanketing System": PidSafety,
  "Gas Detection System": PidMeter,
  "Fire Suppression System": PidSafety,
  "Firewater Pump Unit": PidPump,
  // Piping
  "Pipeline": PidPipeline,
  "Compressor Station": PidCompressor,
  "Header": PidPipeline,
  "Orifice": PidMeter,
  "Sampling System": PidMeter,
  "Metering System": PidMeter,
  // Loading
  "Hydrogen Tube Trailer Loading Unit": PidLoading,
  "Tank Truck Loading Unit": PidLoading,
  "Rail Loading Unit": PidLoading,
  "Ship Loading Unit": PidLoading,
  // Liquefaction
  "CO2 Liquefaction Unit": PidCooler,
  "Hydrogen Liquefaction Unit": PidCooler,
  "Natural Gas Liquefaction Unit": PidCooler,
  // Feedstock
  "Biomass Receiving Station": PidLoading,
  "Biomass Storage Silo": PidTank,
  "Biomass Dry Storage Bunker": PidTank,
  "Biomass Slurry Tank": PidTank,
  "Feedstock Blending Unit": PidMixer,
  "Feeder Hopper": PidTank,
  "Screw Conveyor": PidConveyor,
  "Belt Conveyor": PidConveyor,
  "Bucket Elevator": PidConveyor,
  "Size Reduction Mill": PidTurbine,
  "Shredder": PidTurbine,
  "Chip Screen": PidFilter,
  "Magnetic Separator": PidSeparator,
  "Solids Dryer": PidDryer,
  "Pelletizer": PidCompressor,
  "Briquetter": PidCompressor,
  // Gas generation
  "Air Separation Unit": PidColumn,
  "Nitrogen Generation Unit": PidColumn,
  "Oxygen Generation Unit": PidColumn,
  // Sludge & water misc
  "Sludge Dewatering Unit": PidFilter,
  "Solvent Regeneration Unit": PidReactor,
};

export const defaultEquipmentIcon: IconComponent = PidReactor;

// ══════════════════════════════════════════════
// CARRIER ICONS — keyed by carrier label
// ══════════════════════════════════════════════
export const carrierIcons: Record<string, IconComponent> = {
  // Power
  "Electricity": Zap,
  "Power": Zap,
  // Water family
  "Seawater": Waves,
  "Water": Droplets,
  "Wastewater": Waves,
  "Effluent": Waves,
  "Cooling Water": Snowflake,
  "Condensate": Droplets,
  "Brine": FlaskRound,
  "Demineralized Water": Droplets,
  // Gases
  "Hydrogen": Atom,
  "H₂": Atom,
  "Liquid Hydrogen": Snowflake,
  "Oxygen": Wind,
  "Liquid Oxygen": Snowflake,
  "Nitrogen": CircleDashed,
  "Liquid Nitrogen": Snowflake,
  "Argon": CircleDashed,
  "Air": Wind,
  "Compressed Air": Wind,
  "Instrument Air": Wind,
  "Flue Gas": CloudFog,
  "Vent Gas": CloudFog,
  // Carbon
  "CO₂": CloudRain,
  "Carbon Dioxide": CloudRain,
  "Carbon Monoxide": CloudRain,
  "Captured CO₂": CloudRain,
  // Heat / Steam
  "Heat": Thermometer,
  "Process Steam": CloudFog,
  "Steam": CloudFog,
  "LP Steam": CloudFog,
  "MP Steam": CloudFog,
  "HP Steam": CloudFog,
  "Refrigerant": Snowflake,
  "Glycol": Snowflake,
  // Hydrocarbons / Fuels
  "Methane": Flame,
  "Natural Gas": Flame,
  "Biogas": Flame,
  "Biomethane": Flame,
  "Syngas": Flame,
  "LNG": Fuel,
  "LPG": Fuel,
  "CNG": Fuel,
  "Diesel": Fuel,
  "Gasoline": Fuel,
  "Kerosene": Fuel,
  "Naphtha": Fuel,
  // Chemicals
  "Methanol": FlaskConical,
  "Ethanol": FlaskConical,
  "DME": FlaskConical,
  "Ammonia": TestTube,
  "Urea": TestTube,
  "Sulfur": Beaker,
  "Sulfuric Acid": Beaker,
  "Carbon Black": Layers,
  "Coke": Layers,
  "Char": Layers,
  // Bio
  "Biomass": Wheat,
  "Feedstock": Wheat,
  "Wood Chips": TreePine,
  "Digestate": Sprout,
  "Slurry": Recycle,
  "Sludge": Recycle,
  "Glycerol": FlaskConical,
};

/**
 * Resolve a carrier icon with alias-aware + keyword fallback so user-defined
 * carrier labels still get a meaningful symbol instead of the generic circle.
 */
export function getCarrierIcon(label: string): IconComponent {
  if (carrierIcons[label]) return carrierIcons[label];
  const lower = label.toLowerCase().trim();
  for (const key of Object.keys(carrierIcons)) {
    if (key.toLowerCase() === lower) return carrierIcons[key];
  }
  // Keyword fallbacks (order matters — most specific first)
  if (/(steam|vapor)/.test(lower)) return CloudFog;
  if (/(refriger|chill|cryo|liquid\s*(h2|o2|n2|hydrogen|oxygen|nitrogen))/.test(lower)) return Snowflake;
  if (/(diesel|gasoline|petrol|kerosene|naphtha|fuel|lng|lpg|cng)/.test(lower)) return Fuel;
  if (/(biogas|biometh|methane|natural\s*gas|syngas|flame|combust)/.test(lower)) return Flame;
  if (/(co2|carbon|flue|vent\s*gas)/.test(lower)) return CloudRain;
  if (/(power|electric|kw|mw|volt)/.test(lower)) return Zap;
  if (/(hydrogen|h2|h₂)/.test(lower)) return Atom;
  if (/(oxygen|o2|o₂)/.test(lower)) return Wind;
  if (/(nitrogen|argon|inert)/.test(lower)) return CircleDashed;
  if (/(brine|sulfur|acid|caustic|amine)/.test(lower)) return Beaker;
  if (/(methanol|ethanol|alcohol|solvent|chem|dme|glycerol)/.test(lower)) return FlaskConical;
  if (/(ammonia|urea|nh3)/.test(lower)) return TestTube;
  if (/(biomass|wood|pellet|chip|wheat|straw|husk)/.test(lower)) return Wheat;
  if (/(digest|sludge|slurry|waste)/.test(lower)) return Recycle;
  if (/(water|effluent|condens|cool)/.test(lower)) return Droplets;
  if (/(air|wind|breath)/.test(lower)) return Wind;
  if (/(heat|thermal|temp)/.test(lower)) return Thermometer;
  return defaultCarrierIcon;
}

export const defaultCarrierIcon: IconComponent = PidCarrier;

// ══════════════════════════════════════════════
// GATE ICONS — keyed by gate label
// ══════════════════════════════════════════════
export const gateIcons: Record<string, IconComponent> = {
  "Power Supply": Zap,
  "Water Supply": Droplets,
  "Air Intake": Leaf,
  "CO₂ Supply": FlaskConical,
  "Heat Supply": Flame,
  "Fuel Supply": Flame,
  "Gas Supply": Flame,
  "Biomass Supply": Leaf,
  "Chemical Supply": FlaskConical,
  "Vent": PidFlare,
  "H₂ Offtake": Atom,
  "MeOH Offtake": PidGateOutput,
  "Offtake Market": PidGateOutput,
  "Water Discharge": Waves,
  "Heat Offtake": Flame,
  "Waste Export": Waves,
  "CO₂ Offtake": CloudRain,
};

export const defaultInputGateIcon: IconComponent = PidGateInput;
export const defaultOutputGateIcon: IconComponent = PidGateOutput;

/** Get icon for any component by type and label */
export function getComponentIcon(type: "equipment" | "carrier" | "gate", label: string): IconComponent {
  if (type === "equipment") return equipmentIcons[label] || defaultEquipmentIcon;
  if (type === "carrier") return getCarrierIcon(label);
  return gateIcons[label] || defaultInputGateIcon;
}
