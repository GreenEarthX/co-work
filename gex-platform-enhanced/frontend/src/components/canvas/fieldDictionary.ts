/**
 * Field Dictionary — Complete form definitions for every plant component.
 * Parsed from equipment_dictionary.xlsx, carrier_dictionary.xlsx, gate_dictionary.xlsx.
 *
 * Each component maps to an array of field definitions used by ComponentDetailDialog
 * to dynamically render the correct form.
 */

export interface FieldDef {
  name: string;
  type: "select" | "number" | "text" | "date" | "multiselect";
  unit?: string;
  values?: string[];
  min?: number;
  max?: number;
  required?: boolean;
  description?: string;
  outputModules?: string;
}

/* Helper for concise field definitions */
const sel = (name: string, values: string[], opts?: Partial<FieldDef>): FieldDef =>
  ({ name, type: "select", values, ...opts });
const num = (name: string, unit: string, min?: number, max?: number, opts?: Partial<FieldDef>): FieldDef =>
  ({ name, type: "number", unit, min, max, ...opts });
const txt = (name: string, opts?: Partial<FieldDef>): FieldDef =>
  ({ name, type: "text", ...opts });
const dt = (name: string, opts?: Partial<FieldDef>): FieldDef =>
  ({ name, type: "date", ...opts });

/* ═══════════════════════════════════════════════════════
   COMMON FIELDS (appended to most equipment & some carriers)
   ═══════════════════════════════════════════════════════ */
const commonCost: FieldDef[] = [
  num("Plant Availability", "%", 0, 100),
  num("Scheduled Operating Hours", "h/year", 0, 8760),
  num("Total Installed Capital Cost", "currency", 0),
  num("Capital Cost Reference Year", "year", 2000, 2100),
  sel("Capital Cost Basis", ["Vendor Quote", "Feasibility Estimate", "Pre-FEED Estimate", "FEED Estimate", "EPC Lump Sum", "Literature Benchmark", "Assumed"]),
  num("Annual Fixed Operating Cost", "currency/year", 0),
];

/* ═══════════════════════════════════════════════════════
   EQUIPMENT FIELDS
   ═══════════════════════════════════════════════════════ */
export const equipmentFields: Record<string, FieldDef[]> = {
  "Electrolyzer": [
    sel("Electrolyzer Technology", ["PEM", "Alkaline", "SOEC", "AEM"], { required: true, description: "Technology class of the electrolyzer stack" }),
    num("Hydrogen Production Capacity", "kg H₂/h", 0, undefined, { description: "Nameplate H₂ production at 100% load" }),
    num("Specific Electricity Consumption", "kWh/kg H₂", 30, 100, { description: "System-level electricity incl. BOP, excl. external compression" }),
    num("Stack Design Operating Pressure", "bar(g)", 0, 500),
    num("Stack Design Operating Temperature", "°C", 0, 1000),
    num("Stack Lifetime", "hours", 0, undefined, { description: "Cumulative operating hours before stack replacement" }),
    num("Stack Degradation Rate", "% per 1000h", 0, 5),
    num("Water Consumption", "L H₂O/kg H₂", 0, 50),
    ...commonCost,
  ],

  "Reforming Reactor": [
    sel("Reforming Technology", ["SMR", "ATR", "Dry Reforming", "Partial Oxidation", "Combined Reforming"], { required: true }),
    num("Rated H₂ Production Capacity", "kg H₂/h", 0, undefined, {}),
    num("Specific Feedstock Consumption", "kWh LHV/kg H₂", 40, 200),
    num("Reformer Thermal Efficiency", "decimal LHV", 0.5, 1.0),
    num("Steam to Carbon Ratio", "mol/mol", 0, 6),
    num("CO₂ Emissions Intensity", "kg CO₂eq/kg H₂", 0, 30),
    sel("CCS Integration Mode", ["None", "Pre-combustion Ready", "CCS Integrated", "Full Capture"]),
    num("CO₂ Capture Rate", "decimal", 0, 1.0),
    num("Catalyst Lifetime", "hours", 0),
    ...commonCost,
  ],

  "Water Gas Shift Reactor": [
    sel("WGS Configuration", ["HT-WGS", "LT-WGS", "Sour Shift", "Isothermal WGS"], { required: true }),
    num("Rated Syngas Throughput", "Nm³/h", 0),
    num("CO Conversion", "decimal", 0, 1.0),
    num("Steam to CO Ratio", "mol/mol", 1.0, 5.0),
    num("CO₂ Yield", "kg CO₂/kg H₂", 0),
    sel("Catalyst Type", ["Fe-Cr High Temperature", "Cu-Zn Low Temperature", "Co-Mo Sulfided Sour Shift", "Precious Metal Isothermal"]),
    num("Catalyst Lifetime", "hours", 0),
    ...commonCost,
  ],

  "Fischer-Tropsch Reactor": [
    sel("FT Reactor Type", ["Slurry Bubble Column", "Fixed Bed Tubular", "Microchannel", "Fluidised Bed"], { required: true }),
    sel("FT Catalyst Type", ["Cobalt", "Iron", "Ruthenium"], { required: true }),
    num("Design Syngas Feed Rate", "Nm³/h", 0),
    num("Per Pass CO Conversion", "decimal", 0, 1.0),
    num("Chain Growth Probability Alpha", "decimal", 0.7, 0.95),
    num("C₅+ Selectivity", "wt%", 0, 100),
    num("Reactor Operating Temperature", "°C", 150, 350),
    num("Reactor Operating Pressure", "bar(g)", 10, 50),
    num("Catalyst Lifetime", "hours", 0),
    ...commonCost,
  ],

  "Methanol Synthesis Reactor": [
    sel("Reactor Type", ["Adiabatic Quench", "Isothermal BWR", "Radial Flow", "Tubular"], { required: true }),
    sel("Catalyst Type", ["Cu-Zn-Al Standard", "Cu-Zn-Al High Activity", "Other"], { required: true }),
    num("Design Syngas Feed Rate", "Nm³/h", 0),
    num("Per Pass CO₂ Conversion", "decimal", 0, 1.0),
    num("Methanol Selectivity", "mol%", 90, 100),
    num("Reactor Operating Temperature", "°C", 200, 300),
    num("Reactor Operating Pressure", "bar(g)", 40, 120),
    num("Catalyst Lifetime", "hours", 0),
    ...commonCost,
  ],

  "Ammonia Synthesis Reactor": [
    sel("Reactor Configuration", ["Multi-Bed Adiabatic with Inter-Bed Quench", "Multi-Bed Adiabatic with Inter-Bed Cooling", "Isothermal", "Once Through"], { required: true }),
    sel("Catalyst Type", ["Magnetite Fe₃O₄ Promoted", "Wüstite Fe₁₋ₓO", "Ruthenium on Carbon"], { required: true }),
    num("Design Synthesis Gas Feed Rate", "Nm³/h", 0),
    num("Per Pass NH₃ Conversion", "decimal", 0, 0.4),
    num("Number of Catalyst Beds", "", 1, 5),
    num("Reactor Operating Temperature", "°C", 350, 550),
    num("Reactor Operating Pressure", "bar(g)", 100, 350),
    num("Catalyst Lifetime", "hours", 0),
    ...commonCost,
  ],

  "Methanation Reactor": [
    sel("Methanation Reactor Type", ["Adiabatic Fixed Bed Series", "Isothermal Cooled", "Fluidised Bed", "Structured Catalyst"], { required: true }),
    sel("Catalyst Type", ["Nickel on Alumina", "Ruthenium on Alumina", "Other"], { required: true }),
    num("Design CO₂ Feed Rate", "Nm³/h", 0),
    num("CO₂ Conversion", "decimal", 0, 1.0),
    num("CH₄ Selectivity", "mol%", 90, 100),
    num("Reactor Operating Temperature", "°C", 200, 700),
    num("Reactor Operating Pressure", "bar(g)", 1, 30),
    num("Catalyst Lifetime", "hours", 0),
    ...commonCost,
  ],

  "Hydrogen Compressor": [
    sel("Compressor Type", ["Reciprocating Piston", "Ionic Liquid", "Diaphragm Metallic", "Electrochemical"], { required: true }),
    num("Rated Mass Flow", "kg/h", 0),
    num("Suction Pressure", "bar(g)", 0),
    num("Discharge Pressure", "bar(g)", 0, 1000),
    num("Number of Stages", "", 1, 8),
    num("Overall Isentropic Efficiency", "decimal", 0.5, 0.9),
    num("Rated Shaft Power", "kW", 0),
    sel("Driver Type", ["Electric Motor", "Variable Speed Drive Motor", "Gas Turbine", "Steam Turbine"]),
    sel("Cooling Type", ["Water Cooled Intercooled", "Air Cooled Intercooled", "Uncooled Single Stage"]),
    ...commonCost,
  ],

  "CO2 Compressor": [
    sel("Compressor Type", ["Integrally Geared Centrifugal", "Reciprocating Piston", "Screw", "Axial"], { required: true }),
    num("Rated Mass Flow", "t CO₂/h", 0),
    num("Suction Pressure", "bar(g)", 0),
    num("Discharge Pressure", "bar(g)", 0, 300),
    num("Number of Stages", "", 1, 10),
    num("Overall Isentropic Efficiency", "decimal", 0.5, 0.9),
    num("Rated Shaft Power", "kW", 0),
    sel("Intercooling Type", ["Water Cooled", "Air Cooled", "None"]),
    ...commonCost,
  ],

  "Syngas Compressor": [
    sel("Compressor Type", ["Centrifugal Multi-Stage", "Reciprocating Piston", "Axial-Centrifugal Combination"], { required: true }),
    num("Rated Volumetric Flow", "Nm³/h", 0),
    num("Suction Pressure", "bar(g)", 0),
    num("Discharge Pressure", "bar(g)", 0, 200),
    num("Number of Stages", "", 1, 10),
    num("Overall Isentropic Efficiency", "decimal", 0.5, 0.9),
    num("Rated Shaft Power", "kW", 0),
    ...commonCost,
  ],

  "Heat Exchanger": [
    sel("Heat Exchanger Type", ["Shell and Tube", "Plate", "Plate and Frame", "Spiral", "Air Cooled", "Printed Circuit PCHE", "Double Pipe"], { required: true }),
    num("Rated Duty", "kW", 0),
    num("Design LMTD", "°C", 1, 200),
    num("Heat Transfer Area", "m²", 0),
    num("Overall U Value", "W/m²K", 10, 5000),
    num("Hot Side Design Pressure", "bar(g)", 0, 400),
    num("Cold Side Design Pressure", "bar(g)", 0, 400),
    sel("Shell Material", ["Carbon Steel", "Stainless Steel 316L", "Duplex 2205", "Titanium", "Hastelloy C276"]),
    sel("Tube Material", ["Carbon Steel", "Stainless Steel 316L", "Duplex 2205", "Titanium", "Copper-Nickel 90/10"]),
    ...commonCost,
  ],

  "Cooling Tower": [
    sel("Cooling Tower Type", ["Natural Draft", "Mechanical Draft Induced", "Mechanical Draft Forced", "Hybrid", "Dry Cooling"], { required: true }),
    num("Design Heat Rejection Duty", "MW", 0),
    num("Design Wet Bulb Temperature", "°C", -10, 40),
    num("Design Cooling Range", "°C", 3, 25),
    num("Design Approach Temperature", "°C", 2, 15),
    num("Design Makeup Water Rate", "m³/h", 0),
    num("Cycles of Concentration", "", 1, 10),
    ...commonCost,
  ],

  "Steam Boiler": [
    sel("Boiler Type", ["Fire-Tube", "Water-Tube D-Type", "Water-Tube A-Type", "Once-Through", "Package", "Waste Heat"], { required: true }),
    sel("Firing Mode", ["Natural Gas Fired", "Oil Fired", "Biomass Fired", "Dual Fuel Gas-Oil", "Multi-Fuel", "Unfired"]),
    num("Rated Steam Generation Capacity", "t/h", 0),
    num("Design Steam Pressure", "bar(g)", 0, 300),
    num("Thermal Efficiency LHV", "decimal", 0.6, 1.0),
    sel("Superheater Included", ["Yes", "No"]),
    num("Design Superheat Temperature", "°C", 100, 650),
    num("NOx Emission Level", "mg/Nm³", 0, 1000),
    num("Number of Burners", "", 0, 50),
    sel("Economizer Included", ["Yes", "No"]),
    ...commonCost,
  ],

  "Steam Turbine": [
    sel("Turbine Type", ["Back-Pressure", "Condensing", "Extraction-Condensing", "Extraction-Back-Pressure", "Impulse Single-Stage"], { required: true }),
    num("Rated Shaft Power Output", "kW", 0),
    num("Isentropic Efficiency", "decimal", 0.4, 0.95),
    num("Inlet Steam Design Pressure", "bar(g)", 0, 300),
    num("Exhaust Steam Design Pressure", "bar(a)", 0.01, 50),
    num("Rotational Speed", "RPM", 500, 5000),
    num("Number of Extraction Points", "", 0, 5),
    sel("Gearbox Included", ["Yes", "No"]),
    sel("Governor Control Type", ["Mechanical-Hydraulic", "Electro-Hydraulic", "Digital DEH", "Fixed Speed"]),
    ...commonCost,
  ],

  "Air Separation Unit": [
    sel("ASU Type", ["Cryogenic Low Pressure", "Cryogenic High Pressure", "VPSA", "PSA", "Membrane"], { required: true }),
    num("Design Rated O₂ Output", "Nm³/h", 0),
    num("Design O₂ Purity", "vol%", 90, 99.9),
    num("Specific Power Consumption", "kWh/Nm³ O₂", 0.2, 2.0),
    sel("N₂ Co-production", ["Yes", "No"]),
    sel("Argon Co-production", ["Yes", "No"]),
    ...commonCost,
  ],

  "PSA Unit": [
    sel("PSA Target Gas", ["Hydrogen", "CO₂", "Nitrogen", "Oxygen", "Methane"], { required: true }),
    sel("Adsorbent Type", ["Activated Carbon", "Zeolite 5A", "Zeolite 13X", "CMS Carbon Molecular Sieve", "Alumina"]),
    num("Design Feed Flow Rate", "Nm³/h", 0),
    num("Product Recovery", "decimal", 0.5, 0.999),
    num("Product Purity", "mol%", 90, 99.9999),
    num("Number of Beds", "", 2, 16),
    num("Cycle Time", "seconds", 30, 600),
    num("Design Feed Pressure", "bar(g)", 0, 50),
    ...commonCost,
  ],

  "Buffer Tank": [
    sel("Storage Concept", ["Atmospheric", "Pressurised", "Cryogenic", "Semi-Refrigerated"], { required: true }),
    num("Geometric Capacity", "m³", 0),
    num("Net Working Capacity", "m³", 0),
    num("Residence Time at Design Flow", "minutes", 0),
    num("Vessel Design Pressure", "bar(g)", 0, 400),
    num("Minimum Design Temperature", "°C", -275, 50),
    num("Maximum Design Temperature", "°C", -50, 400),
    sel("Shell Material", ["Carbon Steel A516", "Stainless Steel 316L", "Stainless Steel 304L", "Duplex 2205", "Hastelloy C276"]),
    sel("Tank Geometry", ["Vertical Cylinder Fixed Roof", "Horizontal Cylinder", "Sphere", "Double-Wall Vacuum Jacket"]),
    sel("Insulation Type", ["Perlite Vacuum Annulus", "Polyurethane Foam", "Mineral Wool", "Cellular Glass", "Multi-Layer Vacuum", "None"]),
    num("Boil-Off Rate", "%/day", 0, 5),
    sel("Pressure Relief Type", ["Spring-Loaded PRV", "Pilot-Operated PRV", "Rupture Disk", "PRV and Rupture Disk Series"]),
    num("Relief Valve Set Pressure", "bar(g)", 0, 400),
    sel("Inerting System", ["Nitrogen Blanket Continuous", "Nitrogen Blanket On-Demand", "None"]),
    ...commonCost,
  ],

  "Power Rectifier": [
    sel("Rectifier Type", ["Thyristor SCR", "IGBT PWM", "Diode Bridge", "Active Front End"], { required: true }),
    num("Rated DC Power Output", "kW", 0),
    num("Rated DC Voltage Output", "V DC", 0, 6000),
    num("Rated DC Current Output", "A DC", 0, 100000),
    sel("AC Input Voltage Class", ["400 V AC LV", "690 V AC LV", "3.3 kV MV", "6.6 kV MV", "11 kV MV", "33 kV MV"]),
    sel("Number of Pulse Groups", ["6-Pulse", "12-Pulse", "24-Pulse"]),
    num("Conversion Efficiency", "decimal", 0.92, 0.99),
    num("Total Harmonic Distortion", "%", 0, 35),
    num("Power Factor at Rated Load", "decimal", 0.7, 1.0),
    ...commonCost,
  ],

  "Pump": [
    sel("Pump Type", ["Centrifugal Single-Stage", "Centrifugal Multi-Stage", "Axial Flow", "Reciprocating Plunger", "Rotary Screw", "Rotary Gear", "Diaphragm", "Submersible"], { required: true }),
    sel("Driver Type", ["Electric Motor", "Variable Speed Drive Motor", "Diesel Engine", "Hydraulic", "Steam Turbine"]),
    num("Rated Flow", "m³/h", 0),
    num("Rated Head", "m", 0, 5000),
    num("Maximum Working Pressure", "bar(g)", 0),
    num("Rated Shaft Power", "kW", 0),
    num("Overall Efficiency at Rated Point", "decimal", 0.3, 0.92),
    num("NPSHR at Rated Flow", "m", 0, 30),
    num("Number of Stages", "", 1, 30),
    sel("Casing Material", ["Cast Iron", "Carbon Steel", "Stainless Steel 316L", "Duplex 2205", "Alloy 20", "Hastelloy C276"]),
    sel("Impeller Material", ["Cast Iron", "Carbon Steel", "Stainless Steel 316L", "Duplex 2205", "Bronze", "Hastelloy C276"]),
    sel("Mechanical Seal Type", ["Single Seal", "Double Seal Back-to-Back", "Double Seal Face-to-Face", "Cartridge Seal", "Magnetic Drive"]),
    num("Number of Units Installed", "", 1, 10),
    ...commonCost,
  ],

  "Blower": [
    sel("Blower Type", ["Centrifugal", "Axial", "Roots Positive Displacement", "Side Channel", "Regenerative"], { required: true }),
    num("Rated Volumetric Flow", "m³/h", 0),
    num("Design Pressure Rise", "mbar", 0, 2000),
    num("Rated Shaft Power", "kW", 0),
    num("Overall Efficiency at Rated Point", "decimal", 0.4, 0.85),
    num("Maximum Discharge Pressure", "bar(g)", 0),
    sel("Casing Material", ["Cast Iron", "Carbon Steel", "Aluminium", "Stainless Steel 316L"]),
    num("Number of Units Installed", "", 1, 10),
    sel("Drive Configuration", ["Direct Drive", "Belt Drive", "VFD Direct Drive", "Gearbox Drive"]),
    sel("Cooling Type", ["Air Natural", "Air Forced", "Water Cooled"]),
    ...commonCost,
  ],

  "Refrigeration Compressor": [
    sel("Compressor Type", ["Reciprocating", "Screw", "Centrifugal", "Scroll"], { required: true }),
    sel("Refrigerant Type", ["Ammonia R717", "Propane R290", "R134a", "R404A", "Mixed Refrigerant MR", "Nitrogen N₂"]),
    num("Rated Cooling Capacity", "kW", 0),
    num("COP at Design Point", "decimal", 1.0, 8.0),
    num("Evaporating Temperature", "°C", -200, 20),
    num("Condensing Temperature", "°C", 20, 60),
    num("Rated Shaft Power", "kW", 0),
    ...commonCost,
  ],

  "Electric Generator": [
    sel("Generator Type", ["Synchronous", "Asynchronous Induction"], { required: true }),
    num("Rated Electrical Output", "kW", 0),
    num("Rated Voltage", "kV", 0, 36),
    num("Rated Power Factor", "decimal", 0.8, 1.0),
    num("Generator Efficiency", "decimal", 0.9, 0.99),
    num("Rated Speed", "RPM", 500, 5000),
    sel("Cooling Type", ["Air Cooled", "Hydrogen Cooled", "Water Cooled"]),
    ...commonCost,
  ],

  "Transformer": [
    sel("Transformer Type", ["Step-Up", "Step-Down", "Autotransformer", "Rectifier Transformer"], { required: true }),
    num("Rated Power", "MVA", 0),
    num("Primary Voltage", "kV", 0, 800),
    num("Secondary Voltage", "kV", 0, 800),
    num("Impedance", "%", 4, 15),
    sel("Cooling Type", ["ONAN", "ONAF", "OFAF", "ODAF"]),
    num("No-Load Losses", "kW", 0),
    num("Full-Load Losses", "kW", 0),
    ...commonCost,
  ],

  "Desalination Unit": [
    sel("Desalination Technology", ["Reverse Osmosis", "Multi-Effect Distillation", "Multi-Stage Flash", "Electrodialysis Reversal"], { required: true }),
    num("Design Treatment Capacity", "m³/h", 0),
    num("Design Recovery Rate", "decimal", 0.3, 0.95),
    num("Design Product TDS", "mg/L", 0, 500),
    num("Design Feed TDS", "mg/L", 500, 45000),
    num("Specific Energy Consumption", "kWh/m³", 1, 15),
    ...commonCost,
  ],

  "Demineralisation Unit": [
    sel("Demineralisation Technology", ["Mixed Bed Ion Exchange", "Two-Bed Cation-Anion", "EDI Electrodeionisation", "RO + Mixed Bed Polish"], { required: true }),
    num("Design Treatment Capacity", "m³/h", 0),
    num("Design Product Conductivity", "µS/cm", 0, 10),
    num("Design Feed Conductivity", "µS/cm", 10, 2000),
    sel("Resin Type SAC", ["Strong Acid Cation Gel", "Strong Acid Cation Macroporous"]),
    sel("Resin Type SBA", ["Strong Base Anion Type I", "Strong Base Anion Type II"]),
    ...commonCost,
  ],

  "Reverse Osmosis Unit": [
    sel("RO Configuration", ["Single Pass", "Double Pass", "Single Pass with Partial Second Pass"], { required: true }),
    sel("Membrane Type", ["Brackish Water Polyamide TFC", "Seawater Polyamide TFC", "Low Fouling", "High Rejection"]),
    num("Design Treatment Capacity", "m³/h", 0),
    num("Design Recovery Rate", "decimal", 0.5, 0.95),
    num("Design Feed Pressure", "bar(g)", 5, 80),
    num("Design Permeate TDS", "mg/L", 0, 200),
    num("Specific Energy Consumption", "kWh/m³", 1, 10),
    ...commonCost,
  ],

  "Water Softener": [
    sel("Water Softener Type", ["Sodium Cycle Ion Exchange", "Lime Soda Ash", "Pellet Softening", "Continuous Ion Exchange"], { required: true }),
    num("Design Treatment Capacity", "m³/h", 0),
    num("Design Feed Hardness", "mg/L as CaCO₃", 10, 2000),
    num("Design Product Hardness", "mg/L as CaCO₃", 0, 100),
    num("Design Service Run Length", "bed volumes", 50, 800),
    num("Resin Bed Volume", "m³", 0),
    num("Design Salt Dose", "kg NaCl/m³ resin", 50, 200),
    num("Number of Vessels", "", 1, 6),
    ...commonCost,
  ],

  "Cooling Water Treatment Unit": [
    sel("Treatment Type", ["Open Recirculating Chemical", "Side Stream Softening", "Closed Loop Chemical", "Combined Physical Chemical"], { required: true }),
    num("Design Max Cooling Water Temp", "°C", 20, 95),
    num("Design Cycles of Concentration", "", 2, 10),
    num("Design Circulating Water Flow", "m³/h", 0),
    num("Design Max Inlet TDS", "mg/L", 0),
    ...commonCost,
  ],

  "Activated Carbon Filter": [
    sel("Filter Type", ["Granular Activated Carbon Gravity", "Granular Activated Carbon Pressure", "Powdered Activated Carbon Dosing"], { required: true }),
    sel("Activated Carbon Type", ["Coconut Shell", "Coal Based", "Wood Based"]),
    num("Design Treatment Capacity", "m³/h", 0),
    num("Design EBCT", "minutes", 5, 60),
    num("Carbon Bed Volume", "m³", 0),
    num("Carbon Replacement Interval", "months", 6, 60),
    ...commonCost,
  ],

  "Hydrogen Tube Trailer Loading Unit": [
    sel("Loading Unit Type", ["Cascade Fill Compression", "Direct Compression Fill"], { required: true }),
    num("Design Fill Pressure", "bar(g)", 0, 500),
    num("Design Fill Rate", "kg H₂/h", 0),
    num("Number of Loading Positions", "", 1, 10),
    sel("ATEX Zone Classification", ["Zone 0", "Zone 1", "Zone 2", "Non-Hazardous"]),
    sel("Metering System Type", ["Fiscal Custody Transfer Mass Flow", "Indicative Volume Flow", "No Metering"]),
    ...commonCost,
  ],

  "Tank Truck Loading Unit": [
    sel("Loading Unit Type", ["Top Loading Fixed Arm", "Bottom Loading Swivel Arm", "Pressurised Vapour Recovery", "Cryogenic Liquid Arm"], { required: true }),
    num("Design Maximum Loading Rate", "m³/h", 0),
    num("Design Maximum Operating Pressure", "bar(g)", 0, 30),
    sel("Loading Arm Configuration", ["Bottom Loading Standard", "Top Loading Dome Hatch", "Bottom Loading with Vapour Return", "Top Loading with Vapour Return"]),
    sel("Vapour Recovery System", ["Yes", "No"]),
    sel("Overfill Protection System", ["Yes", "No"]),
    num("Number of Loading Bays", "", 1, 20),
    ...commonCost,
  ],

  "Rail Loading Unit": [
    sel("Loading Unit Type", ["Top Loading Fixed", "Top Loading Swing Arm", "Bottom Loading", "Pressurised Rail Car Loading"], { required: true }),
    num("Design Maximum Loading Rate", "m³/h", 0),
    num("Design Maximum Operating Pressure", "bar(g)", 0, 30),
    num("Loading Arm Reach", "m", 1, 12),
    num("Number of Railcar Spots", "", 1, 20),
    sel("Vapour Recovery System", ["Yes", "No"]),
    ...commonCost,
  ],

  "Solids Dryer": [
    sel("Dryer Type", ["Rotary Drum Direct", "Paddle Dryer Indirect", "Conveyor Belt", "Flash Tube", "Fluidised Bed", "Superheated Steam"], { required: true }),
    sel("Drying Medium Type", ["Steam Indirect", "Hot Air Direct", "Superheated Steam Direct", "Flue Gas Direct", "Microwave RF Electric"]),
    num("Design Maximum Throughput", "t/h dry matter", 0.1, 1000),
    num("Design Max Inlet Moisture", "wt% wb", 10, 80),
    num("Design Target Outlet Moisture", "wt% wb", 0, 30),
    num("Design Thermal Duty", "MW", 0),
    num("Specific Thermal Energy Consumption", "kWh/t water evaporated", 600, 1500),
    ...commonCost,
  ],

  "Magnetic Separator": [
    sel("Magnet Type", ["Permanent Magnet NdFeB", "Permanent Magnet Ferrite", "Electromagnetic Self Cleaning", "Electromagnetic Manual Clean", "Eddy Current Rotor", "Superconducting HGMS"], { required: true }),
    num("Design Magnetic Field Strength", "T", 0.04, 5),
    num("Design Tramp Iron Removal Efficiency", "decimal", 0.7, 0.999),
    num("Design Maximum Throughput", "t/h", 1, 1000),
    sel("Automatic Self Cleaning", ["Yes", "No"]),
    ...commonCost,
  ],

  "Stripper Column": [
    sel("Stripper Type", ["Amine Regeneration Packed", "Amine Regeneration Trayed", "Physical Solvent Regeneration", "Hot Potassium Carbonate Regeneration"], { required: true }),
    num("Design Solvent Regeneration Capacity", "m³/h", 0.1, 50000),
    num("Design Reboiler Duty", "kW", 0, 500000),
    num("Design Column Diameter", "m", 0.1, 12),
    num("Design Operating Pressure", "bar(g)", 0, 10),
    ...commonCost,
  ],

  "Absorber Column": [
    sel("Absorber Type", ["Amine Packed Column", "Amine Trayed Column", "Physical Solvent Packed", "Hot Potassium Carbonate", "Chilled Ammonia"], { required: true }),
    num("Design Gas Throughput", "Nm³/h", 0),
    num("Design CO₂ Removal Efficiency", "decimal", 0.8, 0.999),
    num("Design Column Diameter", "m", 0.1, 15),
    num("Design Column Height", "m", 5, 80),
    sel("Packing Type", ["Random Pall Rings", "Structured Mellapak", "Sieve Tray", "Valve Tray"]),
    ...commonCost,
  ],

  "Fuel Cell": [
    sel("Fuel Cell Type", ["PEM", "SOFC", "MCFC", "AFC", "PAFC"], { required: true }),
    num("Rated Electrical Output", "kW", 0),
    num("Electrical Efficiency LHV", "decimal", 0.3, 0.65),
    num("Operating Temperature", "°C", 50, 1000),
    num("Stack Lifetime", "hours", 0),
    num("Stack Degradation Rate", "% per 1000h", 0, 5),
    ...commonCost,
  ],

  "Gasifier": [
    sel("Gasifier Type", ["Entrained Flow", "Fluidised Bed Bubbling", "Fluidised Bed Circulating", "Fixed Bed Updraft", "Fixed Bed Downdraft", "Plasma"], { required: true }),
    sel("Oxidant Type", ["Oxygen Blown", "Air Blown", "Steam Blown", "Hybrid"]),
    num("Design Feedstock Throughput", "t/h", 0),
    num("Cold Gas Efficiency", "decimal LHV", 0.5, 0.95),
    num("Design Operating Temperature", "°C", 700, 1600),
    num("Design Operating Pressure", "bar(g)", 0, 80),
    num("Carbon Conversion", "decimal", 0.8, 1.0),
    ...commonCost,
  ],

  "ORC Unit": [
    sel("ORC Working Fluid", ["R245fa", "R134a", "Isobutane", "Isopentane", "Toluene", "Siloxane MM", "CO₂ Supercritical"], { required: true }),
    num("Rated Electrical Output", "kW", 0),
    num("Net Electrical Efficiency", "decimal", 0.05, 0.25),
    num("Heat Source Temperature", "°C", 70, 400),
    num("Cooling Water Temperature", "°C", 5, 40),
    ...commonCost,
  ],
};


/* ═══════════════════════════════════════════════════════
   CARRIER FIELDS
   ═══════════════════════════════════════════════════════ */
export const carrierFields: Record<string, FieldDef[]> = {
  "Electricity": [
    sel("Current Type", ["AC", "DC"]),
    num("Voltage", "kV", 0.04, 800),
    num("Frequency", "Hz", 0, 60),
    num("Power Factor", "decimal", 0, 1.0),
  ],

  "Heat": [
    sel("Heat Transfer Mode", ["Sensible", "Latent"]),
    num("Temperature", "°C", -273.15, 1600),
  ],

  "Process Steam": [
    sel("Steam Quality Mode", ["Superheated", "Saturated Dry", "Wet Steam"]),
    num("Temperature", "°C", 0, 600),
    num("Pressure", "bar(g)", 0, 300),
    num("Steam Quality", "dryness fraction", 0, 1.0),
  ],

  "Hydrogen": [
    sel("Physical State", ["Gas", "Liquid Cryogenic"]),
    num("Temperature", "°C", -273.15, 200),
    num("Pressure", "bar(g)", 0, 700),
    num("Purity", "mol%", 90, 100),
    num("H₂O", "ppmv", 0, 500),
    num("O₂", "ppmv", 0, 10000),
    num("CO", "ppmv", 0, 1000),
    num("CO₂", "ppmv", 0, 5000),
    num("Total Sulfur", "ppmv", 0, 100),
    num("Total Hydrocarbons", "ppmv", 0, 5000),
    num("NH₃", "ppmv", 0, 10000),
    num("N₂", "ppmv", 0, 5000),
    num("LHV", "MJ/kg", 100, 120),
  ],

  "Carbon Monoxide": [
    num("Temperature", "°C", -273.15, 200),
    num("Pressure", "bar(g)", 0, 350),
    num("Purity", "mol%", 90, 100),
    num("CO₂", "ppmv", 0, 50000),
    num("H₂", "ppmv", 0, 50000),
    num("N₂", "ppmv", 0, 10000),
    num("LHV", "MJ/kg", 9, 11),
  ],

  "Nitrogen": [
    sel("Physical State", ["Gas", "Liquid Cryogenic"]),
    num("Temperature", "°C", -273.15, 200),
    num("Pressure", "bar(g)", 0, 350),
    num("Purity", "mol%", 99, 100),
    num("O₂", "ppmv", 0, 10000),
    num("H₂O", "ppmv", 0, 1000),
  ],

  "Oxygen": [
    sel("Physical State", ["Gas", "Liquid Cryogenic"]),
    num("Temperature", "°C", -273.15, 200),
    num("Pressure", "bar(g)", 0, 350),
    num("Purity", "mol%", 90, 100),
    num("N₂", "ppmv", 0, 10000),
    num("H₂O", "ppmv", 0, 1000),
    num("Ar", "ppmv", 0, 30000),
  ],

  "Carbon Dioxide": [
    sel("Physical State", ["Gas", "Liquid", "Supercritical", "Solid Dry Ice"]),
    num("Temperature", "°C", -78, 200),
    num("Pressure", "bar(g)", 0, 300),
    num("Purity", "mol%", 90, 100),
    num("H₂O", "ppmv", 0, 5000),
    num("H₂S", "ppmv", 0, 1000),
    num("CO", "ppmv", 0, 5000),
    num("O₂", "ppmv", 0, 10000),
    num("NOx", "ppmv", 0, 500),
    num("SO₂", "ppmv", 0, 500),
  ],

  "Ammonia": [
    sel("Physical State", ["Gas", "Liquid Pressurised", "Liquid Refrigerated"]),
    num("Temperature", "°C", -50, 200),
    num("Pressure", "bar(g)", 0, 300),
    num("Purity", "wt%", 99, 100),
    num("H₂O", "ppmv", 0, 5000),
    num("Oil Content", "ppmv", 0, 50),
  ],

  "Methanol": [
    num("Temperature", "°C", -30, 100),
    num("Pressure", "bar(g)", 0, 30),
    num("Purity", "wt%", 90, 100),
    num("Water Content", "wt%", 0, 10),
    num("Density", "kg/m³", 780, 810),
    num("LHV", "MJ/kg", 19, 21),
  ],

  "Methane": [
    sel("Physical State", ["Gas", "Liquid Cryogenic LNG"]),
    num("Temperature", "°C", -165, 200),
    num("Pressure", "bar(g)", 0, 350),
    num("Purity", "mol%", 90, 100),
    num("CO₂", "ppmv", 0, 50000),
    num("H₂S", "ppmv", 0, 100),
    num("H₂O", "ppmv", 0, 1000),
    num("Wobbe Index", "MJ/Nm³", 40, 55),
    num("LHV", "MJ/Nm³", 30, 40),
  ],

  "Syngas": [
    num("Temperature", "°C", 10, 1400),
    num("Pressure", "bar(g)", 0, 100),
    num("H₂ Mole Fraction", "mol/mol", 0, 0.75),
    num("CO Mole Fraction", "mol/mol", 0, 0.65),
    num("CO₂ Mole Fraction", "mol/mol", 0, 0.40),
    num("CH₄ Mole Fraction", "mol/mol", 0, 0.20),
    num("N₂ Mole Fraction", "mol/mol", 0, 0.60),
    num("H₂O Mole Fraction", "mol/mol", 0, 0.40),
    num("Ar Mole Fraction", "mol/mol", 0, 0.02),
    num("H₂S", "ppmv", 0, 10000),
    num("COS", "ppmv", 0, 2000),
    num("NH₃", "ppmv", 0, 5000),
    num("LHV", "MJ/Nm³", 2, 15),
  ],

  "Natural Gas": [
    num("Temperature", "°C", 0, 60),
    num("Pressure", "bar(g)", 0, 100),
    num("CH₄ Mole Fraction", "mol/mol", 0.70, 1.0),
    num("C₂H₆ Mole Fraction", "mol/mol", 0, 0.15),
    num("C₃H₈ Mole Fraction", "mol/mol", 0, 0.05),
    num("CO₂ Mole Fraction", "mol/mol", 0, 0.10),
    num("N₂ Mole Fraction", "mol/mol", 0, 0.10),
    num("H₂ Mole Fraction", "mol/mol", 0, 0.25),
    num("H₂S", "ppmv", 0, 100),
    num("Total Sulfur", "ppmv", 0, 100),
    num("LHV", "MJ/Nm³", 30, 45),
    num("Wobbe Index", "MJ/Nm³", 40, 60),
  ],

  "Gasoline": [
    num("Temperature", "°C", -20, 50),
    num("Pressure", "bar(g)", 0, 10),
    num("Density", "kg/m³", 700, 800),
    num("RON", "", 85, 102),
    num("MON", "", 80, 95),
    num("RVP", "kPa", 30, 100),
    num("Sulfur", "mg/kg", 0, 50),
    num("Benzene", "vol%", 0, 5),
    num("Oxygen Content", "wt%", 0, 3.7),
    num("LHV", "MJ/kg", 40, 46),
  ],

  "Diesel": [
    num("Temperature", "°C", -30, 50),
    num("Pressure", "bar(g)", 0, 10),
    num("Density", "kg/m³", 800, 860),
    num("Cetane Number", "", 40, 75),
    num("Sulfur", "mg/kg", 0, 50),
    num("CFPP", "°C", -40, 5),
    num("Flash Point", "°C", 55, 120),
    num("Viscosity at 40°C", "mm²/s", 2, 4.5),
    num("Bio-blend Fraction", "vol%", 0, 100),
    num("LHV", "MJ/kg", 42, 46),
  ],

  "Jet Fuel": [
    num("Temperature", "°C", -50, 50),
    num("Pressure", "bar(g)", 0, 10),
    num("Density", "kg/m³", 775, 840),
    num("Flash Point", "°C", 38, 100),
    num("Freezing Point", "°C", -65, -40),
    num("Sulfur", "mg/kg", 0, 3000),
    num("Aromatics", "vol%", 0, 25),
    num("Naphthalene", "vol%", 0, 3),
    num("Net Heat of Combustion", "MJ/kg", 42, 44),
    num("SAF Blend Ratio", "vol%", 0, 100),
  ],

  "Marine Fuel": [
    num("Temperature", "°C", -30, 80),
    num("Density", "kg/m³", 800, 1010),
    num("Sulfur", "wt%", 0, 3.5),
    num("Viscosity at 50°C", "mm²/s", 1, 700),
    num("Flash Point", "°C", 60, 120),
    num("CCAI", "", 790, 870),
    num("LHV", "MJ/kg", 38, 46),
  ],

  "Water": [
    num("Temperature", "°C", 0, 100),
    num("Pressure", "bar(g)", 0, 30),
    num("Conductivity", "µS/cm", 0, 3000),
    num("pH", "", 5.5, 9.5),
    num("Total Hardness", "mg/L as CaCO₃", 0, 1000),
    num("TDS", "mg/L", 0, 2000),
    num("Dissolved O₂", "mg/L", 0, 15),
    num("Silica", "mg/L as SiO₂", 0, 100),
    num("Iron", "mg/L", 0, 10),
    num("TOC", "mg/L", 0, 50),
  ],

  "Demineralised Water": [
    num("Temperature", "°C", 0, 50),
    num("Pressure", "bar(g)", 0, 30),
    num("Conductivity", "µS/cm", 0, 1),
    num("Silica", "µg/L as SiO₂", 0, 20),
    num("Dissolved O₂", "µg/L", 0, 50),
    num("TOC", "µg/L", 0, 200),
    num("Na⁺", "µg/L", 0, 20),
    num("Cl⁻", "µg/L", 0, 50),
  ],

  "Boiler Feedwater": [
    num("Temperature", "°C", 80, 200),
    num("Pressure", "bar(g)", 0, 300),
    num("Conductivity", "µS/cm", 0, 0.5),
    num("Dissolved O₂", "µg/L", 0, 10),
    num("pH", "", 8.5, 9.5),
    num("Silica", "µg/L as SiO₂", 0, 20),
    num("Iron", "µg/L", 0, 20),
    num("Hardness", "µg/L as CaCO₃", 0, 5),
  ],

  "Condensate": [
    num("Temperature", "°C", 50, 200),
    num("Pressure", "bar(g)", 0, 30),
    num("Conductivity", "µS/cm", 0, 50),
    num("pH", "", 7, 9.5),
    num("Dissolved O₂", "mg/L", 0, 0.05),
    num("Iron", "mg/L", 0, 0.01),
  ],

  "Cooling Water": [
    num("Temperature", "°C", 5, 50),
    num("Pressure", "bar(g)", 0, 10),
    num("TDS", "mg/L", 0, 5000),
    num("pH", "", 6.5, 9.0),
    num("Hardness", "mg/L as CaCO₃", 0, 1500),
    num("Chloride", "mg/L", 0, 1000),
    num("Silica", "mg/L as SiO₂", 0, 200),
  ],

  "Wastewater": [
    num("Temperature", "°C", 5, 60),
    num("Pressure", "bar(g)", 0, 5),
    num("pH", "", 4, 12),
    num("COD", "mg/L", 0, 50000),
    num("BOD₅", "mg/L", 0, 20000),
    num("TSS", "mg/L", 0, 10000),
    num("TDS", "mg/L", 0, 50000),
    sel("Regulatory Classification", ["Non-hazardous", "Hazardous", "Not Classified"]),
  ],

  "Brine": [
    num("Temperature", "°C", 5, 80),
    num("Pressure", "bar(g)", 0, 10),
    num("TDS", "mg/L", 10000, 300000),
    num("pH", "", 5, 9),
    sel("Disposal Route", ["Deep Well Injection", "Evaporation Pond", "Municipal Sewer", "Ocean Outfall", "ZLD Crystalliser"]),
  ],

  "Flue Gas": [
    num("Temperature", "°C", 50, 400),
    num("CO₂", "vol%", 2, 20),
    num("O₂", "vol%", 1, 15),
    num("NOx", "mg/Nm³", 0, 500),
    num("SO₂", "mg/Nm³", 0, 2000),
    num("CO", "mg/Nm³", 0, 500),
    num("Particulate", "mg/Nm³", 0, 500),
  ],

  "Used Cooking Oil": [
    num("Temperature", "°C", 0, 80),
    num("Density", "kg/m³", 900, 940),
    num("LHV", "MJ/kg", 34, 40),
    num("Free Fatty Acid", "mg KOH/g", 0, 200),
    num("Moisture", "wt%", 0, 5),
    num("Iodine Value", "g I₂/100g", 60, 140),
  ],

  "Animal Fats": [
    num("Temperature", "°C", 0, 80),
    num("Density", "kg/m³", 860, 930),
    num("LHV", "MJ/kg", 35, 42),
    num("Free Fatty Acid", "mg KOH/g", 0, 200),
    num("Moisture", "wt%", 0, 3),
    num("Iodine Value", "g I₂/100g", 30, 80),
  ],

  "Black Liquor": [
    num("Temperature", "°C", 60, 140),
    num("Density", "kg/m³", 1050, 1400),
    num("Total Dry Solids", "wt%", 10, 85),
    num("LHV Dry Solids", "MJ/kg", 12, 16),
    num("Inorganic Fraction", "wt% of DS", 30, 55),
    num("Sodium Content", "wt% of DS", 15, 25),
    num("Sulfur Content", "wt% of DS", 2, 8),
  ],

  "Tall Oil": [
    num("Temperature", "°C", 10, 80),
    num("Density", "kg/m³", 940, 1000),
    num("LHV", "MJ/kg", 33, 38),
    num("Acid Number", "mg KOH/g", 100, 180),
    num("Rosin Acid Content", "wt%", 20, 50),
    num("Unsaponifiable Matter", "wt%", 5, 35),
    num("Moisture", "wt%", 0, 5),
  ],

  "Crude Glycerine": [
    num("Temperature", "°C", 0, 80),
    num("Density", "kg/m³", 1200, 1280),
    num("Glycerol Content", "wt%", 50, 100),
    num("Moisture", "wt%", 0, 20),
    num("Methanol Content", "wt%", 0, 5),
    num("Ash Content", "wt%", 0, 10),
    num("pH", "", 4, 9),
  ],

  "Wood Chips": [
    num("Moisture", "wt% wb", 10, 65),
    num("LHV wet basis", "MJ/kg", 5, 18),
    num("Ash Content dry basis", "wt%", 0.3, 10),
    num("Bulk Density", "kg/m³", 150, 450),
    num("Particle Size P80", "mm", 10, 80),
  ],

  "Wood Pellets": [
    num("Moisture", "wt% ar", 5, 15),
    num("LHV ar basis", "MJ/kg", 14, 19),
    num("Ash Content dry basis", "wt%", 0.3, 5),
    num("Bulk Density", "kg/m³", 550, 750),
    num("Durability Index", "%", 95, 99.5),
    num("Diameter", "mm", 6, 8),
  ],

  "Slag": [
    num("Temperature", "°C", 20, 1600),
    num("Bulk Density", "kg/m³", 1200, 2000),
    num("Free CaO", "wt%", 0, 15),
    num("Basicity Index", "", 0.5, 4),
    sel("Leachability Class", ["Inert", "Non-hazardous", "Hazardous"]),
  ],

  "Polymer": [
    sel("Polymer Type", ["PE", "PP", "PET", "PS", "PVC", "Other"]),
    num("Density", "kg/m³", 850, 1500),
    num("Bulk Density", "kg/m³", 400, 900),
    num("Melt Flow Index", "g/10min", 0, 100),
    num("Moisture", "wt%", 0, 0.5),
    num("Recycled Content", "wt%", 0, 100),
    num("LHV", "MJ/kg", 15, 48),
  ],

  "Ethanol": [
    num("Temperature", "°C", -30, 80),
    num("Pressure", "bar(g)", 0, 10),
    num("Purity", "vol%", 90, 100),
    num("Water Content", "wt%", 0, 10),
    num("Density", "kg/m³", 780, 810),
    num("LHV", "MJ/kg", 25, 28),
  ],

  "DME": [
    sel("Physical State", ["Gas", "Liquid Pressurised"]),
    num("Temperature", "°C", -30, 50),
    num("Pressure", "bar(g)", 0, 10),
    num("Purity", "wt%", 95, 100),
    num("Methanol Content", "wt%", 0, 5),
    num("Water Content", "ppmv", 0, 500),
    num("LHV", "MJ/kg", 27, 29),
  ],

  "Hydrogen Sulfide": [
    num("Temperature", "°C", -60, 200),
    num("Pressure", "bar(g)", 0, 100),
    num("Purity", "mol%", 80, 100),
  ],

  "Sulfur": [
    sel("Physical State", ["Liquid Molten", "Solid Prills", "Solid Pastilles", "Solid Flake"]),
    num("Purity", "wt%", 99, 100),
    num("Ash Content", "ppmw", 0, 500),
    num("Moisture", "wt%", 0, 2),
  ],

  "LPG": [
    sel("Physical State", ["Liquid Pressurised"]),
    num("Temperature", "°C", -50, 50),
    num("Pressure", "bar(g)", 0, 25),
    num("Propane/Butane Ratio", "vol/vol", 0, 1),
    num("Total Sulfur", "mg/kg", 0, 150),
    num("LHV", "MJ/kg", 45, 48),
  ],

  "Naphtha": [
    num("Temperature", "°C", -20, 50),
    num("Density", "kg/m³", 640, 770),
    num("Sulfur", "mg/kg", 0, 500),
    num("PIONA Paraffins", "vol%", 0, 100),
    num("LHV", "MJ/kg", 43, 47),
  ],

  "Wax": [
    num("Temperature", "°C", 20, 120),
    num("Congealing Point", "°C", 40, 110),
    num("Density at 70°C", "kg/m³", 750, 850),
    num("Oil Content", "wt%", 0, 30),
    num("LHV", "MJ/kg", 40, 46),
  ],

  "Air": [
    num("Temperature", "°C", -50, 60),
    num("Pressure", "bar(g)", 0, 50),
    num("Relative Humidity", "%", 0, 100),
  ],
};


/* ═══════════════════════════════════════════════════════
   GATE FIELDS
   ═══════════════════════════════════════════════════════ */
export const gateFields: Record<string, FieldDef[]> = {
  "Power Supply": [
    sel("Electricity Routing Type", ["Grid Supply", "Direct Line", "On Site Generation", "Hybrid"], { required: true }),
    sel("Power Market Zone System", ["EU Bidding Zone", "US ISO RTO", "Other System", "None"]),
    txt("Power Market Zone Code"),
    sel("Interconnection Relation", ["Same Zone", "Interconnected", "Cross Border Non Interconnected", "Not Assessed"]),
    num("Design Capacity", "MW", 0),
    num("Plant Availability", "%", 0, 100),
    num("Scheduled Operating Hours", "h/year", 0, 8760),
    sel("PPA Exists", ["Yes", "No"]),
    sel("PPA Type", ["Physical", "Virtual", "Sleeved", "Corporate", "Utility", "Other"]),
    sel("Additionality Strategy", ["New Plant", "Capacity Increase", "Repowered", "None", "Unknown"]),
    dt("Generator COD Date"),
    sel("Temporal Matching Requirement", ["Annual", "Monthly", "Hourly", "15 Minute", "Unknown"]),
    sel("Primary Metering Basis", ["Certified Smart Meter", "Revenue Grade Meter", "Grid Settlement", "SCADA", "Supplier Allocation", "Modeled", "Not Monitored"]),
    sel("Electricity Price Basis", ["Fixed Contract", "Day Ahead Spot", "Indexed", "Modeled", "Unknown"]),
    num("Average Electricity Price", "EUR/MWh", 0),
    sel("Electricity Storage Used", ["Yes", "No"]),
    num("Renewable Electricity Share", "%", 0, 100),
    sel("Renewable Share Evidence Strength", ["None", "Self Declaration", "Third Party Document", "Audited Certification", "Registry Record", "Metered Verified"]),
    num("Grid Emission Intensity", "kgCO₂e/MWh", 0),
    sel("EAC Used", ["Yes", "No"]),
    sel("EAC Type", ["Guarantee Of Origin", "REC", "I-REC", "TIGR", "Other", "Unknown"]),
    sel("Generator Technology", ["Wind", "Solar", "Hydro", "Biomass", "Geothermal", "Mixed", "Other"]),
    txt("Generator Country"),
  ],

  "Water Supply": [
    sel("Water Source Type", ["Surface", "Groundwater", "Municipal", "Reclaimed Wastewater", "Seawater", "Hybrid"], { required: true }),
    sel("Water Body Type", ["River", "Lake", "Reservoir", "Aquifer", "Coastal Sea", "Not Applicable"]),
    txt("Geographic Origin"),
    sel("Water Stress Region", ["Low", "Medium", "High", "Extremely High", "Unknown"]),
    num("Design Flow Capacity", "m³/h", 0),
    num("Annual Water Volume", "m³/year", 0),
    num("Plant Availability", "%", 0, 100),
    num("Scheduled Operating Hours", "h/year", 0, 8760),
    sel("Water Quality Grade", ["Potable", "Industrial", "Brackish", "Seawater", "Wastewater Grade", "Unknown"]),
    sel("Pretreatment Required", ["Yes", "No"]),
    sel("Primary Use Type", ["Process", "Cooling", "Both"]),
    num("Consumptive Use Share", "%", 0, 100),
    sel("Return Flow Exists", ["Yes", "No"]),
    sel("Discharge Permit Required", ["Yes", "No"]),
  ],

  "CO2 Supply": [
    sel("CO₂ Source Category", ["Fossil Industrial", "Biogenic", "Atmospheric DAC", "Geological", "Hybrid"], { required: true }),
    sel("CO₂ Origin Process", ["Ammonia", "Cement", "Steel", "Refinery", "Bioethanol", "Biogas Upgrading", "Biomass CHP", "Direct Air Capture", "Natural Reservoir", "Other"]),
    sel("Carbon Stream Type", ["Flue Gas", "Process Gas", "Fermentation Off Gas", "Ambient Air", "Pure Industrial", "Other"]),
    sel("CO₂ Capture Method", ["Post Combustion", "Pre Combustion", "Oxy Fuel", "Fermentation Separation", "Physical Separation", "Direct Air", "None Pure Stream", "Other"]),
    sel("Intentionally Produced Stream", ["Yes", "No"]),
    num("Design Supply Capacity", "tCO₂/h", 0),
    num("Annual CO₂ Quantity", "tCO₂/year", 0),
    num("Plant Availability", "%", 0, 100),
    num("CO₂ Purity", "%", 0, 100),
    sel("CO₂ Eligibility Claim", ["RFNBO Recycled Carbon", "Biogenic", "DAC Atmospheric", "Non Eligible", "Other"]),
    txt("Geographic Origin"),
    txt("Traceability Reference"),
  ],

  "Biomass Supply": [
    sel("Biomass Category", ["Woody Biomass", "Agricultural Residue", "Energy Crop", "Waste Biomass", "Aquatic Biomass", "Other"], { required: true }),
    sel("Biomass Origin", ["Forest Residue", "Sawmill Residue", "Plantation", "Straw", "Corn Stover", "Bagasse", "MSW Organic", "Sewage Sludge", "Algae", "Other"]),
    sel("Supply Chain Type", ["Direct Procurement", "Spot Market", "Long Term Contract", "Cooperative", "Self Produced", "Other"]),
    num("Design Supply Capacity", "t/year", 0),
    num("Annual Supply Quantity", "t/year", 0),
    num("Plant Availability", "%", 0, 100),
    sel("Moisture Basis", ["Wet Basis", "Dry Basis"]),
    num("Typical Moisture Content", "wt%", 0, 80),
    sel("Sustainability Certification", ["FSC", "PEFC", "SBP", "ISCC", "RED II Compliant", "None", "Other"]),
    sel("ILUC Risk Category", ["Low", "Medium", "High", "Unknown"]),
    sel("RED II Annex IX Listed", ["Yes Part A", "Yes Part B", "No", "Unknown"]),
    txt("Origin Country"),
  ],

  "Chemical Supply": [
    sel("Chemical Carrier", ["Ammonia", "Methanol", "Carbon Monoxide", "Solvent", "Syngas", "Chlorine", "Sodium Hydroxide", "Sodium Chloride", "Sulfur", "Nitrogen", "Oxygen", "Other"], { required: true }),
    sel("Chemical Use Role", ["Chemical Reagent", "Feedstock", "Solvent", "Utility", "Other"]),
    sel("Chemical Grade", ["Technical", "Industrial", "Food", "Pharmaceutical", "Electrolyser Grade", "Other"]),
    num("Design Supply Capacity", "t/year", 0),
    num("Annual Supply Quantity", "t/year", 0),
    num("Plant Availability", "%", 0, 100),
    num("Solution Concentration", "wt fraction", 0, 1.0),
    num("Purity", "%", 0, 100),
    sel("Hazard Class", ["Non Hazardous", "Corrosive", "Flammable", "Toxic", "Oxidizer", "Compressed Gas", "Cryogenic", "Unknown"]),
    sel("Transport Mode", ["Truck", "Rail", "Ship", "Pipeline", "Other"]),
    txt("Supplier Company"),
    txt("Production Country"),
  ],

  "Gas Supply": [
    sel("Gas Carrier", ["Hydrogen", "Ammonia", "Methane", "Natural Gas", "Carbon Dioxide", "Carbon Monoxide", "Nitrogen", "Oxygen", "Syngas", "Air", "LPG", "Other"], { required: true }),
    sel("Gas Use Role", ["Process Gas", "Fuel", "Utility", "Feedstock", "Inert Gas", "Oxidant", "Other"]),
    sel("Physical State at Delivery", ["Gas", "Liquid"]),
    num("Design Supply Capacity", "t/year", 0),
    num("Annual Supply Quantity", "t/year", 0),
    num("Plant Availability", "%", 0, 100),
    num("Gas Purity", "%", 0, 100),
    num("LHV", "kWh/kg", 0, 150),
    num("Pressure at Delivery", "bar(g)", 0),
    num("Temperature at Delivery", "°C", -273, 200),
    sel("Transport Mode", ["Pipeline", "Truck", "Rail", "Ship", "On Site Generation", "Other"]),
    txt("Supplier Company"),
    txt("Production Country"),
  ],

  "CO2 Offtake": [
    sel("CO₂ Offtake Type", ["Vented To Atmosphere", "On Site Utilization", "Export For Utilization", "Export For Geological Storage", "Export For Temporary Storage", "Other"], { required: true }),
    num("Design Offtake Capacity", "tCO₂/h", 0),
    num("Annual CO₂ Offtake Quantity", "tCO₂/year", 0),
    num("Plant Availability", "%", 0, 100),
    num("CO₂ Purity at Offtake", "%", 0, 100),
    sel("Offtake Physical State", ["Gas", "Compressed Gas", "Liquid", "Solid Dry Ice"]),
    num("Offtake Pressure", "bar(g)", 0, 300),
    sel("Receiving Party Type", ["Storage Operator", "Utilization Plant", "Trader", "Industrial Customer", "Other"]),
    txt("Receiving Facility Country"),
    txt("Receiving Facility Name"),
    sel("Transport Mode", ["Pipeline", "Truck", "Rail", "Ship", "Other"]),
    num("Transport Distance", "km", 0, 20000),
    sel("Offtake End Use", ["Geological Storage", "Long Lived Mineralization", "Short Lived Utilization", "Industrial Process With Re Release", "Unknown"]),
    sel("Permanence Duration", ["Less Than 1 Year", "1 To 10 Years", "10 To 100 Years", "More Than 100 Years", "Unknown"]),
    sel("MRV Available", ["Yes", "No"]),
  ],

  "Offtake Market": [
    sel("Offtaker Type", ["Refinery Operator", "Fuel Blending Operator", "Airport Fuel Supplier", "Bunkering Operator", "Steel Producer", "Chemical Producer", "Cement Plant", "District Heating Operator", "Utility Company", "Energy Trader", "Fleet Operator", "Other"], { required: true }),
    txt("Offtaker Identity"),
    txt("Offtake Country"),
    sel("Product Sold", ["Hydrogen", "Ammonia", "Methanol", "SAF", "eDiesel", "eMethane", "eLPG", "Heat", "Electricity", "Other"]),
    num("Contracted Annual Quantity", "t/year", 0),
    sel("Contract Type", ["Spot", "Short Term", "Long Term Offtake Agreement", "Letter of Intent", "No Contract"]),
    num("Contracted Price", "EUR/unit", 0),
    sel("Price Index Basis", ["Fixed", "Indexed to Commodity", "Indexed to Carbon", "Formula Based", "Unknown"]),
    sel("Delivery Basis", ["Ex Works", "FOB", "CIF", "DDP", "DAP", "Other"]),
    sel("Certification Required by Offtaker", ["Yes", "No"]),
    sel("Certification Scheme Required", ["ISCC EU", "ISCC PLUS", "REDcert EU", "CertifHy", "RSB EU RED", "Other", "Unknown"]),
  ],
};


/* ═══════════════════════════════════════════════════════
   LOOKUP FUNCTIONS
   ═══════════════════════════════════════════════════════ */

/** Find the best field list for an equipment component label */
export function getEquipmentFieldDefs(label: string): FieldDef[] {
  // Exact match first
  if (equipmentFields[label]) return equipmentFields[label];
  // Fuzzy match by keyword
  const l = label.toLowerCase();
  for (const [key, fields] of Object.entries(equipmentFields)) {
    if (l.includes(key.toLowerCase()) || key.toLowerCase().includes(l)) return fields;
  }
  // Generic fallback
  return commonCost;
}

/** Find the best field list for a carrier label */
export function getCarrierFieldDefs(label: string): FieldDef[] {
  if (carrierFields[label]) return carrierFields[label];
  const l = label.toLowerCase();
  for (const [key, fields] of Object.entries(carrierFields)) {
    if (l.includes(key.toLowerCase()) || key.toLowerCase().includes(l)) return fields;
  }
  return [];
}

/** Find the best field list for a gate (by label or gate type label) */
export function getGateFieldDefs(label: string): FieldDef[] {
  if (gateFields[label]) return gateFields[label];
  const l = label.toLowerCase();
  for (const [key, fields] of Object.entries(gateFields)) {
    if (l.includes(key.toLowerCase()) || key.toLowerCase().includes(l)) return fields;
  }
  return [];
}
