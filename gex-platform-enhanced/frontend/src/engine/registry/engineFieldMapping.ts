/**
 * Mapping between UI field names and equation engine parameter keys.
 * Also maps equipment component labels to archetype IDs.
 */

/** Equipment label → archetype ID used by the equation engine */
export const LABEL_TO_ARCHETYPE: Record<string, string> = {
  'Electrolyzer': 'ELECTROLYSIS_UNIT',
  'Electrolyzer BOP': 'ELECTROLYSIS_BOP',
  'Power Rectifier': 'ELEC_POWER_CONVERSION',
  'Inverter': 'ELEC_POWER_CONVERSION',
  'Transformer': 'ELEC_POWER_CONVERSION',
  'VFD Drive': 'ELEC_POWER_CONVERSION',
  'Electrical Switchgear': 'ELEC_DISTRIBUTION_PROTECTION',
  'Motor Control Center': 'ELEC_DISTRIBUTION_PROTECTION',
  'Battery Energy Storage System': 'ELEC_STORAGE',
  'Uninterruptible Power Supply': 'ELEC_STORAGE',
  'DCS / PLC System': 'INSTRUMENTATION_CONTROL',
  'SCADA System': 'INSTRUMENTATION_CONTROL',
  'Process Analyzer': 'INSTRUMENTATION_CONTROL',
  'Water Treatment Unit': 'WATER_TREATMENT_UNIT',
  'Demin Water System': 'WATER_TREATMENT_UNIT',
  'RO System': 'WATER_TREATMENT_UNIT',
  'Pump': 'PUMP_LIQUID',
  'Blower': 'BLOWER_FAN',
  'Flue Gas Blower': 'BLOWER_FAN',
  'Hydrogen Compressor': 'COMPRESSOR_GAS',
  'CO2 Compressor': 'COMPRESSOR_GAS',
  'Syngas Compressor': 'COMPRESSOR_GAS',
  'Natural Gas Compressor': 'COMPRESSOR_GAS',
  'Air Compressor': 'COMPRESSOR_GAS',
  'Instrument Air Compressor': 'COMPRESSOR_GAS',
  'Refrigeration Compressor': 'COMPRESSOR_GAS',
  'Air Cooler': 'GAS_COOLER_INTERCOOLER',
  'Flue Gas Cooler': 'GAS_COOLER_INTERCOOLER',
  'Heat Exchanger': 'HEAT_EXCHANGER_GENERIC',
  'Cooling Tower': 'COOLING_SYSTEM',
  'Chiller': 'COOLING_SYSTEM',
  'Refrigeration System': 'COOLING_SYSTEM',
  'Steam Boiler': 'STEAM_SYSTEM',
  'Steam Drum': 'STEAM_SYSTEM',
  'Steam Turbine': 'STEAM_SYSTEM',
  'Heat Recovery Steam Generator': 'STEAM_SYSTEM',
  'Deaerator': 'STEAM_SYSTEM',
  'Fired Heater': 'THERMAL_HEATER',
  'Thermal Oil Heater': 'THERMAL_HEATER',
  'Electric Generator': 'POWER_GENERATION_UNIT',
  'Engine Generator Set': 'POWER_GENERATION_UNIT',
  'Gas Turbine': 'POWER_GENERATION_UNIT',
  'KO Drum': 'GAS_LIQUID_SEPARATOR',
  'Flash Vessel': 'GAS_LIQUID_SEPARATOR',
  'Demister': 'COALESCER_DEMISTER',
  'Cyclone': 'PARTICULATE_REMOVAL_GAS',
  'Wet Scrubber': 'GAS_SCRUBBING_WET',
  'Venturi Scrubber': 'GAS_SCRUBBING_WET',
  'PSA Unit': 'ADSORPTION_PURIFIER',
  'TSA Unit': 'ADSORPTION_PURIFIER',
  'Deoxo Unit': 'ADSORPTION_PURIFIER',
  'Gas Dryer': 'DRYER_GAS',
  'Molecular Sieve': 'DRYER_GAS',
  'Amine Unit': 'AMINE_GAS_TREATING_SYSTEM',
  'CO2 Absorber': 'ABSORPTION_STRIPPING_COLUMN',
  'Solvent Regeneration Unit': 'SOLVENT_REGENERATION',
  'ASU': 'AIR_SEPARATION_SYSTEM',
  'Air Separation Unit': 'AIR_SEPARATION_SYSTEM',
  'DAC Contactor': 'CO2_CAPTURE_CONTACTOR',
  'Direct Air Capture': 'CO2_CAPTURE_CONTACTOR',
  'CO2 Capture Unit': 'CO2_CAPTURE_CONTACTOR',
  'CO2 Capture Regeneration': 'CO2_CAPTURE_REGENERATION',
  'Liquefaction Unit': 'LIQUEFACTION_UNIT',
  'LH2 Liquefaction': 'LIQUEFACTION_UNIT',
  'LNG Liquefaction': 'LIQUEFACTION_UNIT',
  'Distillation Column': 'DISTILLATION_FRACTIONATION_COLUMN',
  'Fractionation Column': 'DISTILLATION_FRACTIONATION_COLUMN',
  'Evaporator': 'EVAPORATION_CRYSTALLIZATION_UNIT',
  'Crystallizer': 'EVAPORATION_CRYSTALLIZATION_UNIT',
  'Rotary Dryer': 'SOLIDS_DRYING_UNIT',
  'Hydrotreater': 'UPGRADING_HYDROPROCESSING_UNIT',
  'Hydrocracker': 'UPGRADING_HYDROPROCESSING_UNIT',
  'Crusher': 'SIZE_REDUCTION_UNIT',
  'Mill': 'SIZE_REDUCTION_UNIT',
  'Screen': 'SOLIDS_SCREEN_SEPARATION',
  'Conveyor': 'SOLIDS_CONVEYING_FEEDING',
  'Screw Feeder': 'SOLIDS_CONVEYING_FEEDING',
  'Pelletizer': 'DENSIFICATION_UNIT',
  'Storage Tank': 'STORAGE_TANK',
  'Cryogenic Tank': 'STORAGE_TANK',
  'Loading Arm': 'LOADING_UNLOADING_INTERFACE',
  'Pipeline': 'PIPELINE_TRANSPORT',
  'Header': 'DISTRIBUTION_HEADER_MANIFOLD',
  'Wastewater Treatment': 'WASTEWATER_TREATMENT_UNIT',
  'Pressure Relief Valve': 'SAFETY_RELIEF_BLOWDOWN',
  'Rupture Disc': 'SAFETY_RELIEF_BLOWDOWN',
  'Flare': 'VENTING_FLARING',
  'Vent Stack': 'VENTING_FLARING',
  'Catalytic Oxidizer': 'OXIDATION_ABATEMENT',
  'Thermal Oxidizer': 'OXIDATION_ABATEMENT',
  'N2 Blanketing System': 'INERTING_BLANKETING',
  'Gas Detector': 'DETECTION_FIRE_PROTECTION',
  'Fire Suppression': 'DETECTION_FIRE_PROTECTION',
  'Anaerobic Digester': 'BIOGAS_PRODUCTION_UNIT',
  'Biogas Upgrader': 'BIOGAS_UPGRADING_UNIT',
  'Gasifier': 'GASIFICATION_UNIT',
  'Pyrolysis Reactor': 'PYROLYSIS_UNIT',
  'HTL Reactor': 'HTL_TORREFACTION_UNIT',
  'Torrefaction Reactor': 'HTL_TORREFACTION_UNIT',
  'Biomass Boiler': 'BIOMASS_COMBUSTION_UNIT',
  'Reforming Reactor': 'REFORMING_OXIDATION_REACTOR',
  'Shift Reactor': 'SHIFT_REACTOR',
  'Tar Reformer': 'TAR_REFORMING_UNIT',
  'Methanation Reactor': 'METHANATION_REACTOR',
  'Methanol Reactor': 'METHANOL_SYNTHESIS_REACTOR',
  'DME Reactor': 'DME_REACTOR',
  'Ammonia Synthesis Reactor': 'AMMONIA_SYNTHESIS_REACTOR',
  'Fischer Tropsch Reactor': 'FISCHER_TROPSCH_REACTOR',
  'Polymerization Reactor': 'POLYMERIZATION_REACTOR',
  'Haber Bosch Loop': 'HABER_BOSCH_LOOP_SKID',
};

/**
 * FieldDef name → engine paramKey.
 * Only fields that have a direct engine parameter mapping are listed.
 */
export const FIELD_TO_PARAM: Record<string, string> = {
  // Electrolysis
  'Hydrogen Production Capacity': 'CAPACITY_H2',
  'Specific Electricity Consumption': 'SEC_ELEC_H2',
  'Water Consumption': 'WATER_FACTOR',
  // Generic capacity/flow
  'Design Capacity': 'CAPACITY_MAIN',
  'Throughput Capacity': 'CAPACITY_MAIN',
  'Nominal Capacity': 'CAPACITY_MAIN',
  'Mass Flow Rate': 'FLOW_MAIN',
  'Flow Rate': 'FLOW_MAIN',
  'Rated Flow': 'FLOW_MAIN',
  // Power
  'Rated Power': 'POWER_ELEC',
  'Electrical Power': 'POWER_ELEC',
  'Power Consumption': 'POWER_ELEC',
  'Motor Power': 'POWER_ELEC',
  'Fixed Power': 'P_FIXED',
  'Base Power': 'P_BASE',
  // SEC generic
  'Specific Energy Consumption': 'SEC_ELEC',
  // Thermal
  'Thermal Duty': 'DUTY_TH',
  'Heat Duty': 'DUTY_TH',
  'Cooling Duty': 'COOLING_DUTY',
  'COP': 'COP_COOL',
  'Thermal Efficiency': 'EFF_TH',
  'Fuel LHV': 'LHV_FUEL',
  'Steam Duty': 'STEAM_DUTY',
  'Steam Flow': 'FLOW_STEAM',
  'Steam Enthalpy': 'DELTAH_STEAM',
  'Fuel Flow': 'FLOW_FUEL',
  // BESS
  'Storage Capacity': 'E_STORAGE',
  'Duration': 'DURATION_H',
  // Generator
  'Electrical Efficiency': 'EFF_ELEC',
  // Split/removal
  'Recovery': 'RECOVERY',
  'Removal Efficiency': 'REMOVAL_EFF',
  // Operating
  'Scheduled Operating Hours': 'HOURS_YEAR',
  'Plant Availability': 'HOURS_YEAR',  // approximate mapping
};

/**
 * Get the engine paramKey for a given field name, if one exists.
 */
export function getParamKeyForField(fieldName: string): string | null {
  return FIELD_TO_PARAM[fieldName] ?? null;
}

/**
 * Get the archetype ID for an equipment label.
 */
export function getArchetypeForLabel(label: string): string | null {
  // Try exact match first
  if (LABEL_TO_ARCHETYPE[label]) return LABEL_TO_ARCHETYPE[label];
  // Try partial match
  for (const [key, archetype] of Object.entries(LABEL_TO_ARCHETYPE)) {
    if (label.toLowerCase().includes(key.toLowerCase())) return archetype;
  }
  return null;
}
