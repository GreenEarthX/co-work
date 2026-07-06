/**
 * Real-world Procurement Database for Plant Equipment
 * Contains actual manufacturers, models, and market prices (2024-2025 data).
 * Three optimization strategies: Best Price, Highest Efficiency, Economies of Scale.
 */

export interface ManufacturerOption {
  manufacturer: string;
  model: string;
  country: string;
  /** Unit price in EUR — for large equipment, total installed cost */
  priceEur: number;
  /** Display price string */
  priceDisplay: string;
  /** Efficiency metric (type-specific, e.g., kWh/kg for electrolyzers) */
  efficiency: string;
  /** Min capacity for economies of scale pricing */
  scaleThreshold?: string;
  /** Lead time in months */
  leadTimeMonths: number;
  /** TRL (Technology Readiness Level) */
  trl: number;
}

export interface EquipmentProcurement {
  /** Equipment keywords to match node labels */
  keywords: string[];
  /** Unit for pricing context */
  pricingUnit: string;
  /**
   * Quantity multiplier for a reference 100 MW plant.
   * For per-kW items (electrolyzers): 100_000 (kW).
   * For per-unit items: realistic unit count for the plant.
   * Defaults to 1 if omitted.
   */
  plantScaleQty?: number;
  bestPrice: ManufacturerOption;
  bestEfficiency: ManufacturerOption;
  economiesOfScale: ManufacturerOption;
}

export const procurementDatabase: EquipmentProcurement[] = [
  /* ═══════════════════════════ ELECTROLYSIS ═══════════════════════════ */
  {
    keywords: ["electrolyzer", "electrolysis"],
    pricingUnit: "€/kW installed",
    plantScaleQty: 100_000, // 100 MW = 100,000 kW
    bestPrice: {
      manufacturer: "LONGi Green Energy",
      model: "ALK Hi1 1000 Nm³/h",
      country: "China",
      priceEur: 350,
      priceDisplay: "€350/kW",
      efficiency: "4.3 kWh/Nm³ H₂ (LHV)",
      scaleThreshold: ">20 MW",
      leadTimeMonths: 8,
      trl: 9,
    },
    bestEfficiency: {
      manufacturer: "Nel Hydrogen",
      model: "A3880 PEM",
      country: "Norway",
      priceEur: 1200,
      priceDisplay: "€1,200/kW",
      efficiency: "4.53 kWh/Nm³ H₂ (LHV), 74% system eff.",
      scaleThreshold: ">5 MW",
      leadTimeMonths: 14,
      trl: 9,
    },
    economiesOfScale: {
      manufacturer: "thyssenkrupp nucera",
      model: "Scalion 20 MW ALK Module",
      country: "Germany",
      priceEur: 500,
      priceDisplay: "€500/kW (at 100+ MW scale)",
      efficiency: "4.4 kWh/Nm³ H₂",
      scaleThreshold: "100+ MW, modular stacking",
      leadTimeMonths: 12,
      trl: 9,
    },
  },

  /* ═══════════════════════════ COMPRESSORS ═══════════════════════════ */
  {
    keywords: ["compressor", "h₂ compressor", "hydrogen compressor"],
    pricingUnit: "€ per unit",
    plantScaleQty: 3, // typically 2-4 compressor trains
    bestPrice: {
      manufacturer: "Howden",
      model: "Burton Corblin Diaphragm",
      country: "UK",
      priceEur: 480000,
      priceDisplay: "€480k",
      efficiency: "88% isentropic eff., up to 500 bar",
      leadTimeMonths: 10,
      trl: 9,
    },
    bestEfficiency: {
      manufacturer: "Burckhardt Compression",
      model: "Laby-GI H₂ (6-stage)",
      country: "Switzerland",
      priceEur: 920000,
      priceDisplay: "€920k",
      efficiency: "92% isentropic eff., up to 1000 bar",
      leadTimeMonths: 14,
      trl: 9,
    },
    economiesOfScale: {
      manufacturer: "NEUMAN & ESSER (NEA)",
      model: "KAB Series Multi-Train",
      country: "Germany",
      priceEur: 750000,
      priceDisplay: "€750k/unit (15% discount at 4+ units)",
      efficiency: "90% isentropic eff.",
      scaleThreshold: "4+ units, multi-train discount",
      leadTimeMonths: 12,
      trl: 9,
    },
  },

  /* ═══════════════════════════ WATER TREATMENT ═══════════════════════════ */
  {
    keywords: ["water treatment", "wtu", "demin", "demineralization", "reverse osmosis"],
    pricingUnit: "€ per unit",
    plantScaleQty: 2, // primary + backup train
    bestPrice: {
      manufacturer: "Veolia Water Technologies",
      model: "NURION RO Module",
      country: "France",
      priceEur: 185000,
      priceDisplay: "€185k",
      efficiency: "95% recovery rate, 50 m³/h",
      leadTimeMonths: 6,
      trl: 9,
    },
    bestEfficiency: {
      manufacturer: "SUEZ Water Technologies",
      model: "ZeeWeed 700B UF + EDI",
      country: "France",
      priceEur: 340000,
      priceDisplay: "€340k",
      efficiency: "99.5% ion rejection, 0.1 µS/cm output",
      leadTimeMonths: 8,
      trl: 9,
    },
    economiesOfScale: {
      manufacturer: "DuPont Water Solutions",
      model: "FILMTEC™ RO Train (modular)",
      country: "USA",
      priceEur: 250000,
      priceDisplay: "€250k/train (20% off at 3+ trains)",
      efficiency: "97% recovery rate",
      scaleThreshold: "3+ trains, centralized pre-treatment",
      leadTimeMonths: 7,
      trl: 9,
    },
  },

  /* ═══════════════════════════ PURIFICATION (PSA/MEMBRANE) ═══════════════════════════ */
  {
    keywords: ["purif", "purifier", "psa", "hydrogen purification"],
    pricingUnit: "€ per unit",
    plantScaleQty: 2, // 2 PSA trains for 100 MW
    bestPrice: {
      manufacturer: "UOP (Honeywell)",
      model: "Polybed PSA H₂",
      country: "USA",
      priceEur: 720000,
      priceDisplay: "€720k",
      efficiency: "99.99% H₂ purity, 85% recovery",
      leadTimeMonths: 10,
      trl: 9,
    },
    bestEfficiency: {
      manufacturer: "Air Liquide Engineering",
      model: "SmartPSA™ H₂",
      country: "France",
      priceEur: 1150000,
      priceDisplay: "€1.15M",
      efficiency: "99.999% H₂ purity, 92% recovery",
      leadTimeMonths: 12,
      trl: 9,
    },
    economiesOfScale: {
      manufacturer: "Linde Engineering",
      model: "Hydropure™ PSA Modular",
      country: "Germany",
      priceEur: 950000,
      priceDisplay: "€950k/module (scale at 3+ modules)",
      efficiency: "99.99% H₂ purity, 90% recovery",
      scaleThreshold: "3+ modules, shared adsorbent regeneration",
      leadTimeMonths: 11,
      trl: 9,
    },
  },

  /* ═══════════════════════════ HEAT EXCHANGERS ═══════════════════════════ */
  {
    keywords: ["heat exchanger", "heat exchange", "cooler", "air cooler"],
    pricingUnit: "€ per unit",
    plantScaleQty: 4, // multiple heat exchangers across process
    bestPrice: {
      manufacturer: "Kelvion",
      model: "NX Series Plate Heat Exchanger",
      country: "Germany",
      priceEur: 85000,
      priceDisplay: "€85k",
      efficiency: "92% thermal eff., up to 200°C",
      leadTimeMonths: 6,
      trl: 9,
    },
    bestEfficiency: {
      manufacturer: "Alfa Laval",
      model: "AlfaNova 76 Fusion-Bonded",
      country: "Sweden",
      priceEur: 195000,
      priceDisplay: "€195k",
      efficiency: "98% thermal eff., up to 550°C",
      leadTimeMonths: 8,
      trl: 9,
    },
    economiesOfScale: {
      manufacturer: "SWEP (Dover)",
      model: "B649 Brazed Plate (modular bank)",
      country: "Sweden",
      priceEur: 120000,
      priceDisplay: "€120k/unit (25% off at 6+ units)",
      efficiency: "95% thermal eff.",
      scaleThreshold: "6+ units, parallel bank configuration",
      leadTimeMonths: 5,
      trl: 9,
    },
  },

  /* ═══════════════════════════ PUMPS ═══════════════════════════ */
  {
    keywords: ["pump"],
    pricingUnit: "€ per unit",
    plantScaleQty: 6, // multiple process pumps
    bestPrice: {
      manufacturer: "Grundfos",
      model: "CR 95 Multi-Stage Centrifugal",
      country: "Denmark",
      priceEur: 38000,
      priceDisplay: "€38k",
      efficiency: "82% hydraulic eff.",
      leadTimeMonths: 4,
      trl: 9,
    },
    bestEfficiency: {
      manufacturer: "Sulzer",
      model: "MSD-RO High-Pressure",
      country: "Switzerland",
      priceEur: 125000,
      priceDisplay: "€125k",
      efficiency: "91% hydraulic eff., up to 80 bar",
      leadTimeMonths: 8,
      trl: 9,
    },
    economiesOfScale: {
      manufacturer: "KSB",
      model: "Etanorm SYT (standardized fleet)",
      country: "Germany",
      priceEur: 52000,
      priceDisplay: "€52k/unit (fleet pricing at 10+ units)",
      efficiency: "86% hydraulic eff.",
      scaleThreshold: "10+ identical units, fleet maintenance contract",
      leadTimeMonths: 5,
      trl: 9,
    },
  },

  /* ═══════════════════════════ REFORMING REACTORS ═══════════════════════════ */
  {
    keywords: ["reformer", "reforming reactor", "smr", "atr"],
    pricingUnit: "€ total installed",
    bestPrice: {
      manufacturer: "Casale",
      model: "AW-500 Steam Reformer",
      country: "Switzerland",
      priceEur: 3200000,
      priceDisplay: "€3.2M",
      efficiency: "78% conversion eff.",
      leadTimeMonths: 18,
      trl: 9,
    },
    bestEfficiency: {
      manufacturer: "Topsoe",
      model: "SynCOR Autothermal Reformer™",
      country: "Denmark",
      priceEur: 6500000,
      priceDisplay: "€6.5M",
      efficiency: "95% methane conversion, 30% lower CO₂ vs SMR",
      leadTimeMonths: 24,
      trl: 9,
    },
    economiesOfScale: {
      manufacturer: "Wood (ex-Jacobs)",
      model: "TopReformer™ Modular SMR",
      country: "UK",
      priceEur: 4800000,
      priceDisplay: "€4.8M/train (15% off at 2+ trains)",
      efficiency: "83% conversion eff.",
      scaleThreshold: "2+ parallel trains",
      leadTimeMonths: 20,
      trl: 9,
    },
  },

  /* ═══════════════════════════ SYNTHESIS REACTORS (METHANOL/AMMONIA) ═══════════════════════════ */
  {
    keywords: ["reactor", "synthesis", "methanol synthesis", "ammonia synthesis", "methanation", "fischer tropsch"],
    pricingUnit: "€ total installed",
    bestPrice: {
      manufacturer: "Casale",
      model: "Axial-Radial Converter",
      country: "Switzerland",
      priceEur: 2800000,
      priceDisplay: "€2.8M",
      efficiency: "Per-pass conversion 35%",
      leadTimeMonths: 16,
      trl: 9,
    },
    bestEfficiency: {
      manufacturer: "Topsoe",
      model: "SynCOR Methanol™ / S-300",
      country: "Denmark",
      priceEur: 5200000,
      priceDisplay: "€5.2M",
      efficiency: "Per-pass conversion 64%, compact loop",
      leadTimeMonths: 22,
      trl: 9,
    },
    economiesOfScale: {
      manufacturer: "thyssenkrupp Uhde",
      model: "Uhde Dual-Pressure Synthesis",
      country: "Germany",
      priceEur: 4100000,
      priceDisplay: "€4.1M/reactor (modular mega-scale)",
      efficiency: "Per-pass conversion 42%",
      scaleThreshold: "500+ t/day, shared utilities",
      leadTimeMonths: 20,
      trl: 9,
    },
  },

  /* ═══════════════════════════ STORAGE TANKS ═══════════════════════════ */
  {
    keywords: ["tank", "storage", "buffer"],
    pricingUnit: "€ per unit",
    plantScaleQty: 10, // multiple storage vessels for buffer capacity
    bestPrice: {
      manufacturer: "Hexagon Purus",
      model: "X-STORE 700 bar Type IV",
      country: "Norway",
      priceEur: 290000,
      priceDisplay: "€290k",
      efficiency: "700 bar, 5 kg/vessel, composite",
      leadTimeMonths: 6,
      trl: 9,
    },
    bestEfficiency: {
      manufacturer: "Chart Industries",
      model: "Cryo-Stor LH₂ Vacuum Tank",
      country: "USA",
      priceEur: 720000,
      priceDisplay: "€720k",
      efficiency: "Boil-off <0.3%/day, up to 100 m³",
      leadTimeMonths: 12,
      trl: 9,
    },
    economiesOfScale: {
      manufacturer: "NPROXX",
      model: "Type IV 500-bar Rack System",
      country: "Germany",
      priceEur: 380000,
      priceDisplay: "€380k/rack (20% off at 10+ racks)",
      efficiency: "500 bar, 30 kg/rack",
      scaleThreshold: "10+ racks, automated filling station",
      leadTimeMonths: 8,
      trl: 9,
    },
  },

  /* ═══════════════════════════ BOILERS / HRSG ═══════════════════════════ */
  {
    keywords: ["boiler", "steam boiler", "hrsg", "heat recovery steam generator"],
    pricingUnit: "€ total installed",
    bestPrice: {
      manufacturer: "Thermax",
      model: "Steam Pak Fire Tube",
      country: "India",
      priceEur: 980000,
      priceDisplay: "€980k",
      efficiency: "89% thermal eff.",
      leadTimeMonths: 8,
      trl: 9,
    },
    bestEfficiency: {
      manufacturer: "Babcock & Wilcox",
      model: "Universal HRSG",
      country: "USA",
      priceEur: 2800000,
      priceDisplay: "€2.8M",
      efficiency: "95% thermal eff., triple pressure",
      leadTimeMonths: 16,
      trl: 9,
    },
    economiesOfScale: {
      manufacturer: "NEM Energy",
      model: "DrumPlus™ Modular HRSG",
      country: "Netherlands",
      priceEur: 2100000,
      priceDisplay: "€2.1M/module (CHP integration)",
      efficiency: "92% thermal eff.",
      scaleThreshold: "2+ modules, shared steam header",
      leadTimeMonths: 14,
      trl: 9,
    },
  },

  /* ═══════════════════════════ TURBINES ═══════════════════════════ */
  {
    keywords: ["turbine", "gas turbine", "steam turbine"],
    pricingUnit: "€ total installed",
    bestPrice: {
      manufacturer: "GE Vernova",
      model: "LM2500 Aero-derivative",
      country: "USA",
      priceEur: 5200000,
      priceDisplay: "€5.2M",
      efficiency: "37% simple cycle eff.",
      leadTimeMonths: 14,
      trl: 9,
    },
    bestEfficiency: {
      manufacturer: "Siemens Energy",
      model: "SGT-800 (H₂-ready)",
      country: "Germany",
      priceEur: 9500000,
      priceDisplay: "€9.5M",
      efficiency: "41% simple cycle, 60% combined cycle",
      leadTimeMonths: 18,
      trl: 9,
    },
    economiesOfScale: {
      manufacturer: "MAN Energy Solutions",
      model: "MGT 6100/6200 Series",
      country: "Germany",
      priceEur: 7200000,
      priceDisplay: "€7.2M/unit (fleet deal at 3+ units)",
      efficiency: "39% simple cycle eff.",
      scaleThreshold: "3+ units, fleet service agreement",
      leadTimeMonths: 16,
      trl: 9,
    },
  },

  /* ═══════════════════════════ SEPARATORS ═══════════════════════════ */
  {
    keywords: ["separator", "flash separator", "oil water separator"],
    pricingUnit: "€ per unit",
    bestPrice: {
      manufacturer: "Koch-Glitsch",
      model: "Flexipac HC Structured Packing",
      country: "USA",
      priceEur: 130000,
      priceDisplay: "€130k",
      efficiency: "HETP 0.35 m",
      leadTimeMonths: 6,
      trl: 9,
    },
    bestEfficiency: {
      manufacturer: "Sulzer",
      model: "Mellapak 252Y + KnitMesh",
      country: "Switzerland",
      priceEur: 240000,
      priceDisplay: "€240k",
      efficiency: "HETP 0.22 m, 40% lower pressure drop",
      leadTimeMonths: 8,
      trl: 9,
    },
    economiesOfScale: {
      manufacturer: "Raschig",
      model: "Super-Ring SR3 Random Packing",
      country: "Germany",
      priceEur: 95000,
      priceDisplay: "€95k/column (bulk at 4+ columns)",
      efficiency: "HETP 0.40 m",
      scaleThreshold: "4+ columns, shared distrib. internals",
      leadTimeMonths: 5,
      trl: 9,
    },
  },

  /* ═══════════════════════════ DISTILLATION COLUMNS ═══════════════════════════ */
  {
    keywords: ["distillation", "column", "absorber", "stripper"],
    pricingUnit: "€ total installed",
    bestPrice: {
      manufacturer: "Koch-Glitsch",
      model: "FLEXITRAY® Valve Tray Column",
      country: "USA",
      priceEur: 450000,
      priceDisplay: "€450k",
      efficiency: "75% tray efficiency",
      leadTimeMonths: 10,
      trl: 9,
    },
    bestEfficiency: {
      manufacturer: "Sulzer Chemtech",
      model: "Structured Packing Column MellapakPlus",
      country: "Switzerland",
      priceEur: 820000,
      priceDisplay: "€820k",
      efficiency: "HETP 0.15 m, ultra-low pressure drop",
      leadTimeMonths: 12,
      trl: 9,
    },
    economiesOfScale: {
      manufacturer: "HAT International",
      model: "Modular Column System",
      country: "Germany",
      priceEur: 580000,
      priceDisplay: "€580k/column (modular at 2+ trains)",
      efficiency: "80% tray efficiency",
      scaleThreshold: "2+ identical trains",
      leadTimeMonths: 10,
      trl: 9,
    },
  },

  /* ═══════════════════════════ FILTERS ═══════════════════════════ */
  {
    keywords: ["filter", "baghouse", "precipitator", "scrubber"],
    pricingUnit: "€ per unit",
    bestPrice: {
      manufacturer: "Donaldson",
      model: "Torit PowerCore TG Series",
      country: "USA",
      priceEur: 65000,
      priceDisplay: "€65k",
      efficiency: "99.9% particulate removal",
      leadTimeMonths: 4,
      trl: 9,
    },
    bestEfficiency: {
      manufacturer: "Pall Corporation",
      model: "Accusep™ Crossflow Ceramic",
      country: "USA",
      priceEur: 180000,
      priceDisplay: "€180k",
      efficiency: "99.99%, sub-micron filtration, 0.1 µm",
      leadTimeMonths: 8,
      trl: 9,
    },
    economiesOfScale: {
      manufacturer: "Camfil",
      model: "Gold Series X-Flo Modular",
      country: "Sweden",
      priceEur: 95000,
      priceDisplay: "€95k/module (30% off at 5+ modules)",
      efficiency: "99.95% particulate removal",
      scaleThreshold: "5+ modules, centralized dust handling",
      leadTimeMonths: 5,
      trl: 9,
    },
  },

  /* ═══════════════════════════ COOLING TOWERS ═══════════════════════════ */
  {
    keywords: ["cooling tower", "chiller"],
    pricingUnit: "€ per unit",
    plantScaleQty: 2, // 2 cooling cells for 100 MW
    bestPrice: {
      manufacturer: "SPX Cooling Technologies",
      model: "Marley NC Series",
      country: "USA",
      priceEur: 220000,
      priceDisplay: "€220k",
      efficiency: "Approach 3.5°C",
      leadTimeMonths: 8,
      trl: 9,
    },
    bestEfficiency: {
      manufacturer: "ENEXIO (now Paharpur)",
      model: "2H Water Technologies Hybrid",
      country: "Germany",
      priceEur: 450000,
      priceDisplay: "€450k",
      efficiency: "Approach 2.2°C, 60% less water vs wet tower",
      leadTimeMonths: 12,
      trl: 9,
    },
    economiesOfScale: {
      manufacturer: "Hamon",
      model: "Multi-Cell Natural Draft",
      country: "Belgium",
      priceEur: 350000,
      priceDisplay: "€350k/cell (multi-cell at 4+ cells)",
      efficiency: "Approach 2.8°C",
      scaleThreshold: "4+ cells, shared basin & piping",
      leadTimeMonths: 10,
      trl: 9,
    },
  },

  /* ═══════════════════════════ GASIFIERS ═══════════════════════════ */
  {
    keywords: ["gasifier", "gasification"],
    pricingUnit: "€ total installed",
    bestPrice: {
      manufacturer: "Nexterra Systems",
      model: "Updraft Fixed-Bed",
      country: "Canada",
      priceEur: 2500000,
      priceDisplay: "€2.5M",
      efficiency: "Cold gas eff. 70%",
      leadTimeMonths: 14,
      trl: 8,
    },
    bestEfficiency: {
      manufacturer: "ThermoChem Recovery International",
      model: "Indirectly-Heated Steam Gasifier",
      country: "USA",
      priceEur: 5800000,
      priceDisplay: "€5.8M",
      efficiency: "Cold gas eff. 82%, low tar",
      leadTimeMonths: 20,
      trl: 8,
    },
    economiesOfScale: {
      manufacturer: "Valmet",
      model: "CFB Gasifier (multi-fuel)",
      country: "Finland",
      priceEur: 4200000,
      priceDisplay: "€4.2M/unit (reference at 100+ MWth)",
      efficiency: "Cold gas eff. 78%",
      scaleThreshold: "100+ MWth, multi-fuel flexibility",
      leadTimeMonths: 18,
      trl: 9,
    },
  },

  /* ═══════════════════════════ CO₂ CAPTURE ═══════════════════════════ */
  {
    keywords: ["co2 capture", "dac", "carbon capture", "amine"],
    pricingUnit: "€ per tCO₂/yr capacity",
    bestPrice: {
      manufacturer: "Aker Carbon Capture",
      model: "Just Catch™ Modular",
      country: "Norway",
      priceEur: 1800000,
      priceDisplay: "€1.8M (100 ktCO₂/yr)",
      efficiency: "90% capture rate, amine-based",
      leadTimeMonths: 14,
      trl: 9,
    },
    bestEfficiency: {
      manufacturer: "Shell Cansolv",
      model: "DC-201 Advanced Amine",
      country: "Netherlands",
      priceEur: 3200000,
      priceDisplay: "€3.2M",
      efficiency: "97% capture rate, low reboiler duty 2.5 GJ/tCO₂",
      leadTimeMonths: 18,
      trl: 9,
    },
    economiesOfScale: {
      manufacturer: "Mitsubishi Heavy Industries",
      model: "KM CDR Process™",
      country: "Japan",
      priceEur: 2400000,
      priceDisplay: "€2.4M/train (mega-scale at 1+ MtCO₂/yr)",
      efficiency: "95% capture rate",
      scaleThreshold: "1+ MtCO₂/yr, world's largest references",
      leadTimeMonths: 20,
      trl: 9,
    },
  },

  /* ═══════════════════════════ FUEL CELLS ═══════════════════════════ */
  {
    keywords: ["fuel cell"],
    pricingUnit: "€/kW installed",
    plantScaleQty: 5_000, // 5 MW auxiliary fuel cell
    bestPrice: {
      manufacturer: "SinoHytec",
      model: "HYMOD-150 PEM FC",
      country: "China",
      priceEur: 600,
      priceDisplay: "€600/kW",
      efficiency: "52% electrical eff.",
      leadTimeMonths: 6,
      trl: 9,
    },
    bestEfficiency: {
      manufacturer: "Bloom Energy",
      model: "Energy Server ES-5 SOFC",
      country: "USA",
      priceEur: 2800,
      priceDisplay: "€2,800/kW",
      efficiency: "65% electrical eff., SOFC",
      leadTimeMonths: 12,
      trl: 9,
    },
    economiesOfScale: {
      manufacturer: "Ballard Power",
      model: "FCgen-HPS Multi-MW Stack",
      country: "Canada",
      priceEur: 1100,
      priceDisplay: "€1,100/kW (volume at 50+ MW)",
      efficiency: "57% electrical eff.",
      scaleThreshold: "50+ MW, modular rack design",
      leadTimeMonths: 10,
      trl: 9,
    },
  },

  /* ═══════════════════════════ ASU / N₂ / O₂ GENERATION ═══════════════════════════ */
  {
    keywords: ["air separation", "asu", "nitrogen gen", "oxygen gen"],
    pricingUnit: "€ total installed",
    bestPrice: {
      manufacturer: "Hangzhou Hangyang",
      model: "KDON-10000/5000",
      country: "China",
      priceEur: 4200000,
      priceDisplay: "€4.2M",
      efficiency: "0.38 kWh/Nm³ O₂",
      leadTimeMonths: 14,
      trl: 9,
    },
    bestEfficiency: {
      manufacturer: "Linde Engineering",
      model: "LIMEDE™ 3-Column ASU",
      country: "Germany",
      priceEur: 8500000,
      priceDisplay: "€8.5M",
      efficiency: "0.32 kWh/Nm³ O₂, argon co-production",
      leadTimeMonths: 20,
      trl: 9,
    },
    economiesOfScale: {
      manufacturer: "Air Liquide Engineering",
      model: "LURGI Mega-ASU",
      country: "France",
      priceEur: 6800000,
      priceDisplay: "€6.8M/train (3000+ tpd O₂)",
      efficiency: "0.34 kWh/Nm³ O₂",
      scaleThreshold: "3000+ tpd O₂, world-scale references",
      leadTimeMonths: 22,
      trl: 9,
    },
  },

  /* ═══════════════════════════ FLARE SYSTEMS ═══════════════════════════ */
  {
    keywords: ["flare", "thermal oxidizer", "catalytic oxidizer"],
    pricingUnit: "€ per unit",
    bestPrice: {
      manufacturer: "Zeeco",
      model: "GLSF Ground-Level Enclosed Flare",
      country: "USA",
      priceEur: 280000,
      priceDisplay: "€280k",
      efficiency: "99.5% DRE",
      leadTimeMonths: 6,
      trl: 9,
    },
    bestEfficiency: {
      manufacturer: "John Zink Hamworthy",
      model: "LSVG™ Low-Smoke Vapour Guard",
      country: "USA",
      priceEur: 520000,
      priceDisplay: "€520k",
      efficiency: "99.99% DRE, smokeless operation",
      leadTimeMonths: 8,
      trl: 9,
    },
    economiesOfScale: {
      manufacturer: "NAO Inc.",
      model: "Multi-Point Ground Flare (MPGF)",
      country: "USA",
      priceEur: 420000,
      priceDisplay: "€420k/stage (modular staging)",
      efficiency: "99.9% DRE",
      scaleThreshold: "Multi-stage, add capacity as needed",
      leadTimeMonths: 7,
      trl: 9,
    },
  },

  /* ═══════════════════════════ TRANSFORMERS / ELECTRICAL ═══════════════════════════ */
  {
    keywords: ["transformer", "rectifier", "inverter", "switchgear", "electrical"],
    pricingUnit: "€ per unit",
    plantScaleQty: 4, // multiple transformers for 100 MW grid connection
    bestPrice: {
      manufacturer: "TBEA",
      model: "SZ11 Oil-Immersed Transformer",
      country: "China",
      priceEur: 95000,
      priceDisplay: "€95k",
      efficiency: "99.2%, up to 63 MVA",
      leadTimeMonths: 6,
      trl: 9,
    },
    bestEfficiency: {
      manufacturer: "Siemens Energy",
      model: "GEAFOL Cast-Resin Dry Transformer",
      country: "Germany",
      priceEur: 210000,
      priceDisplay: "€210k",
      efficiency: "99.5%, eco-design compliant",
      leadTimeMonths: 10,
      trl: 9,
    },
    economiesOfScale: {
      manufacturer: "ABB (Hitachi Energy)",
      model: "Power Transformer Fleet Package",
      country: "Switzerland",
      priceEur: 165000,
      priceDisplay: "€165k/unit (fleet at 5+ units)",
      efficiency: "99.4%",
      scaleThreshold: "5+ units, centralized monitoring",
      leadTimeMonths: 8,
      trl: 9,
    },
  },

  /* ═══════════════════════════ LIQUEFACTION ═══════════════════════════ */
  {
    keywords: ["liquefaction", "lng", "lh2"],
    pricingUnit: "€ total installed",
    bestPrice: {
      manufacturer: "Chart Industries",
      model: "IPSMR® Liquefaction Module",
      country: "USA",
      priceEur: 12000000,
      priceDisplay: "€12M",
      efficiency: "8.5 kWh/kg LH₂",
      leadTimeMonths: 18,
      trl: 8,
    },
    bestEfficiency: {
      manufacturer: "Linde Engineering",
      model: "Cryo-Hydrogen Liquefier",
      country: "Germany",
      priceEur: 22000000,
      priceDisplay: "€22M",
      efficiency: "6.2 kWh/kg LH₂, 100 tpd",
      leadTimeMonths: 24,
      trl: 9,
    },
    economiesOfScale: {
      manufacturer: "Air Liquide Engineering",
      model: "Turbo-Brayton LH₂ Plant",
      country: "France",
      priceEur: 18000000,
      priceDisplay: "€18M/train (50+ tpd scale)",
      efficiency: "7.0 kWh/kg LH₂",
      scaleThreshold: "50+ tpd, world-scale references",
      leadTimeMonths: 22,
      trl: 9,
    },
  },

  /* ═══════════════════════════ POWER RECTIFIER ═══════════════════════════ */
  {
    keywords: ["power rectifier", "rectifier"],
    pricingUnit: "€ per unit",
    plantScaleQty: 4,
    bestPrice: { manufacturer: "ABB (Hitachi Energy)", model: "DPA UPScale ST 120 kW", country: "Switzerland", priceEur: 85000, priceDisplay: "€85k", efficiency: "96.5% AC-DC conversion", leadTimeMonths: 6, trl: 9 },
    bestEfficiency: { manufacturer: "Siemens Energy", model: "SINAMICS DCP 500 kW", country: "Germany", priceEur: 160000, priceDisplay: "€160k", efficiency: "98.2% AC-DC conversion", leadTimeMonths: 10, trl: 9 },
    economiesOfScale: { manufacturer: "Danfoss", model: "VACON NXP Liquid Cooled", country: "Denmark", priceEur: 120000, priceDisplay: "€120k/unit (fleet at 6+)", efficiency: "97.5% AC-DC conversion", scaleThreshold: "6+ units, shared cooling loop", leadTimeMonths: 8, trl: 9 },
  },

  /* ═══════════════════════════ INVERTER ═══════════════════════════ */
  {
    keywords: ["inverter"],
    pricingUnit: "€ per unit",
    plantScaleQty: 6,
    bestPrice: { manufacturer: "Sungrow", model: "SG3150U-MV Central Inverter", country: "China", priceEur: 42000, priceDisplay: "€42k", efficiency: "98.8% DC-AC conversion", leadTimeMonths: 4, trl: 9 },
    bestEfficiency: { manufacturer: "SMA Solar", model: "Sunny Central UP 4600", country: "Germany", priceEur: 95000, priceDisplay: "€95k", efficiency: "99.0% peak DC-AC", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "Huawei", model: "SUN2000-215KTL-H3", country: "China", priceEur: 58000, priceDisplay: "€58k/unit (20% off at 10+)", efficiency: "98.9% DC-AC", scaleThreshold: "10+ units, SmartString architecture", leadTimeMonths: 5, trl: 9 },
  },

  /* ═══════════════════════════ ELECTRICAL SWITCHGEAR ═══════════════════════════ */
  {
    keywords: ["switchgear"],
    pricingUnit: "€ per unit",
    plantScaleQty: 3,
    bestPrice: { manufacturer: "Schneider Electric", model: "SM6 24kV MV Switchgear", country: "France", priceEur: 55000, priceDisplay: "€55k", efficiency: "SF6-free, air insulated", leadTimeMonths: 6, trl: 9 },
    bestEfficiency: { manufacturer: "ABB (Hitachi Energy)", model: "UniGear ZS3.2 AIS", country: "Switzerland", priceEur: 120000, priceDisplay: "€120k", efficiency: "40.5 kV rated, arc-resistant", leadTimeMonths: 10, trl: 9 },
    economiesOfScale: { manufacturer: "Eaton", model: "Power Xpert UX 38 kV", country: "USA", priceEur: 85000, priceDisplay: "€85k/panel (fleet at 5+)", efficiency: "Vacuum circuit breakers, 50,000 ops", scaleThreshold: "5+ panels, unified protection relay", leadTimeMonths: 8, trl: 9 },
  },

  /* ═══════════════════════════ MOTOR CONTROL CENTER ═══════════════════════════ */
  {
    keywords: ["motor control center", "mcc"],
    pricingUnit: "€ per section",
    plantScaleQty: 8,
    bestPrice: { manufacturer: "WEG", model: "MCC Smart Motor Controller", country: "Brazil", priceEur: 28000, priceDisplay: "€28k/section", efficiency: "IE4 motor compatibility", leadTimeMonths: 5, trl: 9 },
    bestEfficiency: { manufacturer: "Siemens", model: "SIMOCODE pro MCC", country: "Germany", priceEur: 65000, priceDisplay: "€65k/section", efficiency: "Integrated condition monitoring", leadTimeMonths: 10, trl: 9 },
    economiesOfScale: { manufacturer: "ABB", model: "MNS iS Intelligent MCC", country: "Switzerland", priceEur: 45000, priceDisplay: "€45k/section (15% off at 10+)", efficiency: "Plug-in modules, hot-swap", scaleThreshold: "10+ sections, centralized SCADA", leadTimeMonths: 8, trl: 9 },
  },

  /* ═══════════════════════════ UPS ═══════════════════════════ */
  {
    keywords: ["uninterruptible power supply", "ups"],
    pricingUnit: "€ per unit",
    plantScaleQty: 2,
    bestPrice: { manufacturer: "Eaton", model: "9395P 600 kVA", country: "USA", priceEur: 95000, priceDisplay: "€95k", efficiency: "96.5% double-conversion", leadTimeMonths: 4, trl: 9 },
    bestEfficiency: { manufacturer: "Schneider Electric", model: "Galaxy VX 1500 kVA", country: "France", priceEur: 220000, priceDisplay: "€220k", efficiency: "99% ECOnversion mode", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "ABB", model: "PowerWave 33 500 kVA", country: "Switzerland", priceEur: 150000, priceDisplay: "€150k/unit (fleet at 3+)", efficiency: "97.5% double-conversion", scaleThreshold: "3+ units, parallel redundancy", leadTimeMonths: 6, trl: 9 },
  },

  /* ═══════════════════════════ BATTERY ENERGY STORAGE ═══════════════════════════ */
  {
    keywords: ["battery energy storage", "bess"],
    pricingUnit: "€/kWh installed",
    plantScaleQty: 50_000,
    bestPrice: { manufacturer: "BYD", model: "MC Cube T28 LFP", country: "China", priceEur: 145, priceDisplay: "€145/kWh", efficiency: "95.3% round-trip eff.", leadTimeMonths: 6, trl: 9 },
    bestEfficiency: { manufacturer: "Tesla", model: "Megapack 2XL", country: "USA", priceEur: 280, priceDisplay: "€280/kWh", efficiency: "97.5% round-trip eff.", leadTimeMonths: 10, trl: 9 },
    economiesOfScale: { manufacturer: "CATL", model: "EnerC Plus 20ft Container", country: "China", priceEur: 160, priceDisplay: "€160/kWh (at 100+ MWh)", efficiency: "96% round-trip eff.", scaleThreshold: "100+ MWh, containerized deployment", leadTimeMonths: 8, trl: 9 },
  },

  /* ═══════════════════════════ PIPELINE ═══════════════════════════ */
  {
    keywords: ["pipeline"],
    pricingUnit: "€/m installed",
    plantScaleQty: 5000,
    bestPrice: { manufacturer: "Tenaris", model: "TenarisHydril Blue Carbon Steel", country: "Argentina", priceEur: 320, priceDisplay: "€320/m", efficiency: "API 5L X52, up to 100 bar", leadTimeMonths: 8, trl: 9 },
    bestEfficiency: { manufacturer: "Salzgitter Mannesmann", model: "H₂-Ready Seamless Line Pipe", country: "Germany", priceEur: 580, priceDisplay: "€580/m", efficiency: "API 5L X70, HIC resistant", leadTimeMonths: 14, trl: 9 },
    economiesOfScale: { manufacturer: "Vallourec", model: "VAM H₂ Premium Connection", country: "France", priceEur: 450, priceDisplay: "€450/m (at 10+ km)", efficiency: "API 5L X65, sour service rated", scaleThreshold: "10+ km, rolling mill batch pricing", leadTimeMonths: 12, trl: 9 },
  },

  /* ═══════════════════════════ COMPRESSOR STATION ═══════════════════════════ */
  {
    keywords: ["compressor station"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Ariel Corporation", model: "JGK/4 Reciprocating Station", country: "USA", priceEur: 2800000, priceDisplay: "€2.8M", efficiency: "88% isentropic, 4-stage", leadTimeMonths: 12, trl: 9 },
    bestEfficiency: { manufacturer: "Siemens Energy", model: "STC-SH Turbocompressor Station", country: "Germany", priceEur: 6500000, priceDisplay: "€6.5M", efficiency: "92% polytropic, magnetic bearings", leadTimeMonths: 18, trl: 9 },
    economiesOfScale: { manufacturer: "Atlas Copco Gas and Process", model: "Integrally Geared Station", country: "Belgium", priceEur: 4500000, priceDisplay: "€4.5M/station (fleet at 3+)", efficiency: "90% polytropic", scaleThreshold: "3+ stations, shared O&M contract", leadTimeMonths: 16, trl: 9 },
  },

  /* ═══════════════════════════ HEADER ═══════════════════════════ */
  {
    keywords: ["header"],
    pricingUnit: "€ per unit",
    plantScaleQty: 4,
    bestPrice: { manufacturer: "Borsig", model: "Process Steam Header DN500", country: "Germany", priceEur: 45000, priceDisplay: "€45k", efficiency: "ASME B31.1, up to 100 bar", leadTimeMonths: 5, trl: 9 },
    bestEfficiency: { manufacturer: "Brembana & Rolle", model: "High-Alloy Header Duplex SS", country: "Italy", priceEur: 95000, priceDisplay: "€95k", efficiency: "ASME VIII Div.1, H₂S rated", leadTimeMonths: 10, trl: 9 },
    economiesOfScale: { manufacturer: "Bilfinger", model: "Modular Piperack Header System", country: "Germany", priceEur: 65000, priceDisplay: "€65k/header (at 6+)", efficiency: "Pre-fabricated, shop-welded", scaleThreshold: "6+ headers, piperack integration", leadTimeMonths: 7, trl: 9 },
  },

  /* ═══════════════════════════ VALVES (GENERAL) ═══════════════════════════ */
  {
    keywords: ["valve", "gate valve", "ball valve", "globe valve"],
    pricingUnit: "€ per unit",
    plantScaleQty: 100,
    bestPrice: { manufacturer: "Neway Valve", model: "Forged Steel Gate Valve API 600", country: "China", priceEur: 1200, priceDisplay: "€1,200", efficiency: "Class 600, up to DN300", leadTimeMonths: 3, trl: 9 },
    bestEfficiency: { manufacturer: "Emerson (Fisher)", model: "HP Butterfly Valve 8580", country: "USA", priceEur: 4500, priceDisplay: "€4,500", efficiency: "Triple offset, zero leakage", leadTimeMonths: 6, trl: 9 },
    economiesOfScale: { manufacturer: "IMI Critical Engineering", model: "Orton HP Ball Valve", country: "UK", priceEur: 2800, priceDisplay: "€2,800/unit (30% off at 50+)", efficiency: "H₂ service rated, fire-safe", scaleThreshold: "50+ units, project lot pricing", leadTimeMonths: 5, trl: 9 },
  },

  /* ═══════════════════════════ JT VALVE ═══════════════════════════ */
  {
    keywords: ["jt valve", "joule-thomson"],
    pricingUnit: "€ per unit",
    plantScaleQty: 4,
    bestPrice: { manufacturer: "Mokveld", model: "JT Axial Control Valve", country: "Netherlands", priceEur: 18000, priceDisplay: "€18k", efficiency: "Cv to 5000, cryogenic service", leadTimeMonths: 6, trl: 9 },
    bestEfficiency: { manufacturer: "Baker Hughes (Masoneilan)", model: "Camflex JT Valve", country: "USA", priceEur: 35000, priceDisplay: "€35k", efficiency: "Low noise trim, anti-cavitation", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "Emerson (Fisher)", model: "EWT JT Valve", country: "USA", priceEur: 25000, priceDisplay: "€25k/unit (at 6+)", efficiency: "Whisper Trim™, low noise", scaleThreshold: "6+ units, shared actuator supply", leadTimeMonths: 7, trl: 9 },
  },

  /* ═══════════════════════════ CONTROL VALVE ═══════════════════════════ */
  {
    keywords: ["control valve"],
    pricingUnit: "€ per unit",
    plantScaleQty: 40,
    bestPrice: { manufacturer: "Samson", model: "Type 3241 Globe Control Valve", country: "Germany", priceEur: 3200, priceDisplay: "€3,200", efficiency: "DN25–DN300, ANSI 300", leadTimeMonths: 4, trl: 9 },
    bestEfficiency: { manufacturer: "Emerson (Fisher)", model: "easy-e™ ET Control Valve", country: "USA", priceEur: 6800, priceDisplay: "€6,800", efficiency: "SIL 3 capable, HART 7", leadTimeMonths: 6, trl: 9 },
    economiesOfScale: { manufacturer: "Flowserve (Valtek)", model: "MaxFlo 4 Rotary Control", country: "USA", priceEur: 4500, priceDisplay: "€4,500/unit (25% off at 30+)", efficiency: "High rangeability 300:1", scaleThreshold: "30+ units, project frame agreement", leadTimeMonths: 5, trl: 9 },
  },

  /* ═══════════════════════════ CHECK VALVE ═══════════════════════════ */
  {
    keywords: ["check valve"],
    pricingUnit: "€ per unit",
    plantScaleQty: 30,
    bestPrice: { manufacturer: "Crane ChemPharma", model: "Duo-Chek II Wafer Check", country: "USA", priceEur: 850, priceDisplay: "€850", efficiency: "Low cracking pressure, DN50–600", leadTimeMonths: 3, trl: 9 },
    bestEfficiency: { manufacturer: "Mokveld", model: "Zero Slam Axial Check Valve", country: "Netherlands", priceEur: 5500, priceDisplay: "€5,500", efficiency: "Non-slam, 0.3s closing time", leadTimeMonths: 6, trl: 9 },
    economiesOfScale: { manufacturer: "Velan", model: "Dual-Plate Check Valve", country: "Canada", priceEur: 2200, priceDisplay: "€2,200/unit (at 20+)", efficiency: "Compact, 1/4 weight of swing check", scaleThreshold: "20+ units, bulk lot pricing", leadTimeMonths: 4, trl: 9 },
  },

  /* ═══════════════════════════ PRESSURE REGULATING VALVE ═══════════════════════════ */
  {
    keywords: ["pressure regulating valve", "pressure regulator"],
    pricingUnit: "€ per unit",
    plantScaleQty: 12,
    bestPrice: { manufacturer: "Emerson (Tescom)", model: "44-2200 Series Regulator", country: "USA", priceEur: 2800, priceDisplay: "€2,800", efficiency: "Inlet to 414 bar, H₂ compatible", leadTimeMonths: 3, trl: 9 },
    bestEfficiency: { manufacturer: "Swagelok", model: "KPR Series High-Purity", country: "USA", priceEur: 5200, priceDisplay: "€5,200", efficiency: "Droop <2%, VCR fittings", leadTimeMonths: 5, trl: 9 },
    economiesOfScale: { manufacturer: "Rotarex", model: "D200 Dome-Loaded Regulator", country: "Luxembourg", priceEur: 3600, priceDisplay: "€3,600/unit (at 15+)", efficiency: "Rapid response, pilot-operated", scaleThreshold: "15+ units, calibration batch", leadTimeMonths: 4, trl: 9 },
  },

  /* ═══════════════════════════ PRESSURE RELIEF VALVE ═══════════════════════════ */
  {
    keywords: ["pressure relief valve", "prv", "psv"],
    pricingUnit: "€ per unit",
    plantScaleQty: 20,
    bestPrice: { manufacturer: "Leser", model: "Type 441 Spring-Loaded PRV", country: "Germany", priceEur: 1800, priceDisplay: "€1,800", efficiency: "API 526, ASME VIII certified", leadTimeMonths: 3, trl: 9 },
    bestEfficiency: { manufacturer: "Baker Hughes (Consolidated)", model: "2900 Series Pilot-Operated", country: "USA", priceEur: 6500, priceDisplay: "€6,500", efficiency: "98% set pressure accuracy", leadTimeMonths: 6, trl: 9 },
    economiesOfScale: { manufacturer: "Emerson (Crosby)", model: "J-Series PRV", country: "USA", priceEur: 3200, priceDisplay: "€3,200/unit (at 15+)", efficiency: "API 526, pop action", scaleThreshold: "15+ units, test bench sharing", leadTimeMonths: 4, trl: 9 },
  },

  /* ═══════════════════════════ RUPTURE DISC ═══════════════════════════ */
  {
    keywords: ["rupture disc"],
    pricingUnit: "€ per unit",
    plantScaleQty: 15,
    bestPrice: { manufacturer: "Fike", model: "AXIUS™ Scored Rupture Disc", country: "USA", priceEur: 350, priceDisplay: "€350", efficiency: "±2% burst accuracy, 0.5–100 bar", leadTimeMonths: 2, trl: 9 },
    bestEfficiency: { manufacturer: "BS&B Safety Systems", model: "RD-90 Reverse-Acting", country: "USA", priceEur: 650, priceDisplay: "€650", efficiency: "±1% burst tolerance, cryogenic rated", leadTimeMonths: 3, trl: 9 },
    economiesOfScale: { manufacturer: "REMBE", model: "KUB® Forward-Acting Disc", country: "Germany", priceEur: 480, priceDisplay: "€480/unit (at 20+)", efficiency: "±2% burst, ATEX certified", scaleThreshold: "20+ discs, annual replacement contract", leadTimeMonths: 2, trl: 9 },
  },

  /* ═══════════════════════════ ORIFICE ═══════════════════════════ */
  {
    keywords: ["orifice"],
    pricingUnit: "€ per unit",
    plantScaleQty: 20,
    bestPrice: { manufacturer: "Emerson (Daniel)", model: "Senior Orifice Fitting", country: "USA", priceEur: 1500, priceDisplay: "€1,500", efficiency: "ISO 5167, flange taps", leadTimeMonths: 3, trl: 9 },
    bestEfficiency: { manufacturer: "ABB", model: "OriMaster FPD500", country: "Switzerland", priceEur: 3200, priceDisplay: "€3,200", efficiency: "Integrated DP transmitter, ±0.5%", leadTimeMonths: 5, trl: 9 },
    economiesOfScale: { manufacturer: "Yokogawa", model: "EJA Series Orifice Assembly", country: "Japan", priceEur: 2200, priceDisplay: "€2,200/unit (at 15+)", efficiency: "Digital HART, remote diagnostics", scaleThreshold: "15+ units, unified calibration", leadTimeMonths: 4, trl: 9 },
  },

  /* ═══════════════════════════ SAMPLING SYSTEM ═══════════════════════════ */
  {
    keywords: ["sampling system"],
    pricingUnit: "€ per unit",
    plantScaleQty: 6,
    bestPrice: { manufacturer: "Swagelok", model: "MPC Modular Platform Component", country: "USA", priceEur: 8500, priceDisplay: "€8,500", efficiency: "Grab + on-line, closed loop", leadTimeMonths: 4, trl: 9 },
    bestEfficiency: { manufacturer: "Parker Hannifin", model: "SensoControl Analytical Panel", country: "USA", priceEur: 22000, priceDisplay: "€22k", efficiency: "Multi-stream, GC integration", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "Mechatest", model: "Liquid & Gas Sampling Cabinet", country: "Netherlands", priceEur: 14000, priceDisplay: "€14k/unit (at 8+)", efficiency: "ATEX Zone 1, SIL 2", scaleThreshold: "8+ cabinets, plant-wide contract", leadTimeMonths: 6, trl: 9 },
  },

  /* ═══════════════════════════ METERING SYSTEM ═══════════════════════════ */
  {
    keywords: ["metering system", "flow meter"],
    pricingUnit: "€ per unit",
    plantScaleQty: 10,
    bestPrice: { manufacturer: "Endress+Hauser", model: "Proline Promass F 300 Coriolis", country: "Switzerland", priceEur: 8500, priceDisplay: "€8,500", efficiency: "±0.1% mass flow accuracy", leadTimeMonths: 4, trl: 9 },
    bestEfficiency: { manufacturer: "Emerson (Micro Motion)", model: "ELITE CMFHC Coriolis", country: "USA", priceEur: 18000, priceDisplay: "€18k", efficiency: "±0.05%, custody transfer grade", leadTimeMonths: 6, trl: 9 },
    economiesOfScale: { manufacturer: "Yokogawa", model: "ROTAMASS 3-Series", country: "Japan", priceEur: 12000, priceDisplay: "€12k/unit (at 10+)", efficiency: "±0.1%, twin-tube design", scaleThreshold: "10+ units, plant-wide calibration", leadTimeMonths: 5, trl: 9 },
  },

  /* ═══════════════════════════ CO2 COMPRESSOR ═══════════════════════════ */
  {
    keywords: ["co2 compressor"],
    pricingUnit: "€ per unit",
    plantScaleQty: 2,
    bestPrice: { manufacturer: "MAN Energy Solutions", model: "RG Integrally-Geared CO₂", country: "Germany", priceEur: 1800000, priceDisplay: "€1.8M", efficiency: "86% polytropic, up to 150 bar", leadTimeMonths: 14, trl: 9 },
    bestEfficiency: { manufacturer: "Baker Hughes (Nuovo Pignone)", model: "MCL CO₂ Centrifugal", country: "Italy", priceEur: 3200000, priceDisplay: "€3.2M", efficiency: "90% polytropic, supercritical service", leadTimeMonths: 18, trl: 9 },
    economiesOfScale: { manufacturer: "Atlas Copco Gas and Process", model: "GT Integrally Geared CO₂ Train", country: "Belgium", priceEur: 2400000, priceDisplay: "€2.4M/train (at 2+)", efficiency: "88% polytropic", scaleThreshold: "2+ trains, CCS hub integration", leadTimeMonths: 16, trl: 9 },
  },

  /* ═══════════════════════════ SYNGAS COMPRESSOR ═══════════════════════════ */
  {
    keywords: ["syngas compressor"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Elliott Group", model: "Flex-Op Syngas Centrifugal", country: "USA", priceEur: 2200000, priceDisplay: "€2.2M", efficiency: "85% polytropic, 80 bar discharge", leadTimeMonths: 16, trl: 9 },
    bestEfficiency: { manufacturer: "Siemens Energy", model: "STC-GC Syngas Compressor", country: "Germany", priceEur: 4500000, priceDisplay: "€4.5M", efficiency: "91% polytropic, dry gas seals", leadTimeMonths: 20, trl: 9 },
    economiesOfScale: { manufacturer: "Mitsubishi Heavy Industries Compressor", model: "MCO-I Syngas Train", country: "Japan", priceEur: 3400000, priceDisplay: "€3.4M/train (at 2+)", efficiency: "89% polytropic", scaleThreshold: "2+ trains, integrated gearbox", leadTimeMonths: 18, trl: 9 },
  },

  /* ═══════════════════════════ NATURAL GAS COMPRESSOR ═══════════════════════════ */
  {
    keywords: ["natural gas compressor"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Ariel Corporation", model: "JGJ/2 Reciprocating NG", country: "USA", priceEur: 650000, priceDisplay: "€650k", efficiency: "87% isentropic, 3-stage", leadTimeMonths: 10, trl: 9 },
    bestEfficiency: { manufacturer: "Solar Turbines (Caterpillar)", model: "C65 Gas Compressor Set", country: "USA", priceEur: 2800000, priceDisplay: "€2.8M", efficiency: "91% polytropic, centrifugal", leadTimeMonths: 16, trl: 9 },
    economiesOfScale: { manufacturer: "Dresser-Rand (Siemens)", model: "DATUM Centrifugal NG", country: "USA", priceEur: 1800000, priceDisplay: "€1.8M/unit (fleet at 3+)", efficiency: "89% polytropic", scaleThreshold: "3+ units, fleet service program", leadTimeMonths: 14, trl: 9 },
  },

  /* ═══════════════════════════ AIR COMPRESSOR ═══════════════════════════ */
  {
    keywords: ["air compressor"],
    pricingUnit: "€ per unit",
    plantScaleQty: 3,
    bestPrice: { manufacturer: "Atlas Copco", model: "GA 315 VSD+ Oil-Injected Screw", country: "Belgium", priceEur: 85000, priceDisplay: "€85k", efficiency: "6.1 kW/(m³/min), VSD", leadTimeMonths: 4, trl: 9 },
    bestEfficiency: { manufacturer: "Ingersoll Rand", model: "Centac C1000 Centrifugal", country: "USA", priceEur: 280000, priceDisplay: "€280k", efficiency: "Oil-free, ISO 8573 Class 0", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "Kaeser", model: "CSG 250 Rotary Screw", country: "Germany", priceEur: 120000, priceDisplay: "€120k/unit (at 5+)", efficiency: "Sigma Profile, IE4 motor", scaleThreshold: "5+ units, SAM controller network", leadTimeMonths: 6, trl: 9 },
  },

  /* ═══════════════════════════ INSTRUMENT AIR COMPRESSOR ═══════════════════════════ */
  {
    keywords: ["instrument air compressor", "instrument air"],
    pricingUnit: "€ per unit",
    plantScaleQty: 2,
    bestPrice: { manufacturer: "Atlas Copco", model: "ZT 90 VSD Oil-Free", country: "Belgium", priceEur: 65000, priceDisplay: "€65k", efficiency: "Class 0 oil-free, 7 bar", leadTimeMonths: 4, trl: 9 },
    bestEfficiency: { manufacturer: "CompAir", model: "D Series Oil-Free 2-Stage", country: "UK", priceEur: 110000, priceDisplay: "€110k", efficiency: "ISO 8573-1 Class 0, dew point -40°C", leadTimeMonths: 6, trl: 9 },
    economiesOfScale: { manufacturer: "Kaeser", model: "DSG 250 Oil-Free Screw", country: "Germany", priceEur: 82000, priceDisplay: "€82k/unit (at 3+)", efficiency: "Class 0, integrated dryer", scaleThreshold: "3+ units, N+1 redundancy", leadTimeMonths: 5, trl: 9 },
  },

  /* ═══════════════════════════ REFRIGERATION COMPRESSOR ═══════════════════════════ */
  {
    keywords: ["refrigeration compressor"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Bitzer", model: "HSN 9593-160 Screw", country: "Germany", priceEur: 42000, priceDisplay: "€42k", efficiency: "COP 4.8, R717 ammonia", leadTimeMonths: 4, trl: 9 },
    bestEfficiency: { manufacturer: "GEA", model: "Grasso V1600 Reciprocating", country: "Germany", priceEur: 95000, priceDisplay: "€95k", efficiency: "COP 5.5, cascade to -50°C", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "Johnson Controls (York)", model: "YVAA Chiller Compressor", country: "USA", priceEur: 68000, priceDisplay: "€68k/unit (at 4+)", efficiency: "COP 5.2, magnetic bearings", scaleThreshold: "4+ units, centralized plant room", leadTimeMonths: 6, trl: 9 },
  },

  /* ═══════════════════════════ BLOWER ═══════════════════════════ */
  {
    keywords: ["blower"],
    pricingUnit: "€ per unit",
    plantScaleQty: 3,
    bestPrice: { manufacturer: "Aerzen", model: "Delta Blower GM 35 S", country: "Germany", priceEur: 28000, priceDisplay: "€28k", efficiency: "78% vol. eff., roots-type", leadTimeMonths: 4, trl: 9 },
    bestEfficiency: { manufacturer: "Atlas Copco", model: "ZB 5000 VSD Turbo Blower", country: "Belgium", priceEur: 85000, priceDisplay: "€85k", efficiency: "85% adiabatic eff., mag. bearings", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "Howden", model: "RR Series Roots Blower", country: "UK", priceEur: 45000, priceDisplay: "€45k/unit (at 4+)", efficiency: "80% vol. eff.", scaleThreshold: "4+ units, shared silencer system", leadTimeMonths: 5, trl: 9 },
  },

  /* ═══════════════════════════ ELECTRIC GENERATOR ═══════════════════════════ */
  {
    keywords: ["electric generator"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "WEG", model: "G Line Synchronous 10 MVA", country: "Brazil", priceEur: 650000, priceDisplay: "€650k", efficiency: "97.5%, 4-pole 1500 rpm", leadTimeMonths: 10, trl: 9 },
    bestEfficiency: { manufacturer: "ABB (Hitachi Energy)", model: "AMG 1600 Synchronous", country: "Switzerland", priceEur: 1500000, priceDisplay: "€1.5M", efficiency: "98.5%, air-cooled, 25 MVA", leadTimeMonths: 14, trl: 9 },
    economiesOfScale: { manufacturer: "Siemens Energy", model: "SGen-100A 2P Generator", country: "Germany", priceEur: 1100000, priceDisplay: "€1.1M/unit (fleet at 3+)", efficiency: "98.2%", scaleThreshold: "3+ units, standardized excitation", leadTimeMonths: 12, trl: 9 },
  },

  /* ═══════════════════════════ ENGINE GENERATOR SET ═══════════════════════════ */
  {
    keywords: ["engine generator set", "genset", "diesel generator"],
    pricingUnit: "€ per unit",
    plantScaleQty: 2,
    bestPrice: { manufacturer: "Caterpillar", model: "C32 ACERT 1250 kVA", country: "USA", priceEur: 180000, priceDisplay: "€180k", efficiency: "42% thermal eff.", leadTimeMonths: 6, trl: 9 },
    bestEfficiency: { manufacturer: "Wärtsilä", model: "W34SG Gas Genset 9.7 MW", country: "Finland", priceEur: 2800000, priceDisplay: "€2.8M", efficiency: "49.2% electrical eff., H₂ blend", leadTimeMonths: 14, trl: 9 },
    economiesOfScale: { manufacturer: "MAN Energy Solutions", model: "51/60G Gas Engine 18 MW", country: "Germany", priceEur: 4200000, priceDisplay: "€4.2M/unit (at 2+)", efficiency: "50.1% electrical eff.", scaleThreshold: "2+ units, CHP integration", leadTimeMonths: 16, trl: 9 },
  },

  /* ═══════════════════════════ AIR COOLER ═══════════════════════════ */
  {
    keywords: ["air cooler", "fin fan"],
    pricingUnit: "€ per unit",
    plantScaleQty: 6,
    bestPrice: { manufacturer: "Kelvion", model: "Air-Fin Cooler KF Series", country: "Germany", priceEur: 65000, priceDisplay: "€65k", efficiency: "Approach 10°C, forced draft", leadTimeMonths: 6, trl: 9 },
    bestEfficiency: { manufacturer: "Alfa Laval", model: "Alroll™ ACC Unit", country: "Sweden", priceEur: 140000, priceDisplay: "€140k", efficiency: "Approach 5°C, low-noise induced draft", leadTimeMonths: 10, trl: 9 },
    economiesOfScale: { manufacturer: "Chart Industries (HTRI)", model: "Modular Fin-Fan Bank", country: "USA", priceEur: 95000, priceDisplay: "€95k/bank (at 8+)", efficiency: "Approach 7°C, VFD fans", scaleThreshold: "8+ banks, shared pipe rack", leadTimeMonths: 8, trl: 9 },
  },

  /* ═══════════════════════════ CHILLER ═══════════════════════════ */
  {
    keywords: ["chiller"],
    pricingUnit: "€ per unit",
    plantScaleQty: 2,
    bestPrice: { manufacturer: "Daikin", model: "Navigator WME Water-Cooled Screw", country: "Japan", priceEur: 120000, priceDisplay: "€120k", efficiency: "COP 6.0, R-1234ze", leadTimeMonths: 6, trl: 9 },
    bestEfficiency: { manufacturer: "Carrier", model: "AquaEdge 19DV Centrifugal", country: "USA", priceEur: 280000, priceDisplay: "€280k", efficiency: "COP 7.5, mag. bearing oil-free", leadTimeMonths: 10, trl: 9 },
    economiesOfScale: { manufacturer: "Johnson Controls (York)", model: "YVWA Variable Speed Screw", country: "USA", priceEur: 180000, priceDisplay: "€180k/unit (at 3+)", efficiency: "COP 6.8", scaleThreshold: "3+ units, chiller plant optimization", leadTimeMonths: 8, trl: 9 },
  },

  /* ═══════════════════════════ STEAM DRUM ═══════════════════════════ */
  {
    keywords: ["steam drum"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Doosan Enerbility", model: "HP Steam Drum, 120 bar", country: "South Korea", priceEur: 320000, priceDisplay: "€320k", efficiency: "SA-516 Gr.70, ASME VIII", leadTimeMonths: 10, trl: 9 },
    bestEfficiency: { manufacturer: "Babcock & Wilcox", model: "Universal Drum, alloy clad", country: "USA", priceEur: 580000, priceDisplay: "€580k", efficiency: "Integral cyclone separators, 99.5% steam quality", leadTimeMonths: 14, trl: 9 },
    economiesOfScale: { manufacturer: "Bilfinger", model: "Modular Drum Package", country: "Germany", priceEur: 420000, priceDisplay: "€420k/unit (at 2+)", efficiency: "Pre-tested, shop-assembled", scaleThreshold: "2+ drums, shared HP header", leadTimeMonths: 12, trl: 9 },
  },

  /* ═══════════════════════════ DEAERATOR ═══════════════════════════ */
  {
    keywords: ["deaerator"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Stork Thermeq", model: "Spray-Tray Deaerator 50 t/h", country: "Netherlands", priceEur: 95000, priceDisplay: "€95k", efficiency: "O₂ < 7 ppb, 105°C", leadTimeMonths: 6, trl: 9 },
    bestEfficiency: { manufacturer: "BFS Industries", model: "Vacuum Deaerator VDA-100", country: "Germany", priceEur: 180000, priceDisplay: "€180k", efficiency: "O₂ < 3 ppb, membrane contactors", leadTimeMonths: 10, trl: 9 },
    economiesOfScale: { manufacturer: "Thermal Engineering International", model: "TTC Tray-Type Deaerator", country: "USA", priceEur: 130000, priceDisplay: "€130k/unit (at 2+)", efficiency: "O₂ < 5 ppb", scaleThreshold: "2+ units, shared LP steam", leadTimeMonths: 8, trl: 9 },
  },

  /* ═══════════════════════════ CONDENSATE POLISHING UNIT ═══════════════════════════ */
  {
    keywords: ["condensate polishing"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Veolia Water Technologies", model: "MULTIFLO™ CPU", country: "France", priceEur: 180000, priceDisplay: "€180k", efficiency: "< 0.1 µS/cm conductivity", leadTimeMonths: 8, trl: 9 },
    bestEfficiency: { manufacturer: "Purolite", model: "Mixed-Bed CPU with NRW resin", country: "UK", priceEur: 350000, priceDisplay: "€350k", efficiency: "< 0.055 µS/cm, silica < 5 ppb", leadTimeMonths: 12, trl: 9 },
    economiesOfScale: { manufacturer: "Graver Technologies", model: "Powdex™ Pre-Coat CPU", country: "USA", priceEur: 260000, priceDisplay: "€260k/unit (at 2+)", efficiency: "< 0.1 µS/cm, rapid regeneration", scaleThreshold: "2+ units, shared resin regeneration", leadTimeMonths: 10, trl: 9 },
  },

  /* ═══════════════════════════ THERMAL OIL HEATER ═══════════════════════════ */
  {
    keywords: ["thermal oil heater"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Thermax", model: "Thermic Fluid Heater FBC", country: "India", priceEur: 180000, priceDisplay: "€180k", efficiency: "87% thermal eff., up to 350°C", leadTimeMonths: 8, trl: 9 },
    bestEfficiency: { manufacturer: "Babcock Wanson", model: "TPC-B Thermal Oil Package", country: "France", priceEur: 380000, priceDisplay: "€380k", efficiency: "93% thermal eff., low NOx burner", leadTimeMonths: 12, trl: 9 },
    economiesOfScale: { manufacturer: "Pirobloc", model: "GFT-H Series Hot Oil Boiler", country: "Spain", priceEur: 250000, priceDisplay: "€250k/unit (at 2+)", efficiency: "90% thermal eff.", scaleThreshold: "2+ units, shared expansion tank", leadTimeMonths: 10, trl: 9 },
  },

  /* ═══════════════════════════ FIRED HEATER ═══════════════════════════ */
  {
    keywords: ["fired heater"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Heurtey Petrochem", model: "Box-Type Process Heater", country: "France", priceEur: 1200000, priceDisplay: "€1.2M", efficiency: "88% thermal eff.", leadTimeMonths: 14, trl: 9 },
    bestEfficiency: { manufacturer: "Amec Foster Wheeler", model: "Terrace Wall™ Heater", country: "UK", priceEur: 2800000, priceDisplay: "€2.8M", efficiency: "94% with convection bank, ultra-low NOx", leadTimeMonths: 20, trl: 9 },
    economiesOfScale: { manufacturer: "Petro-Chem Development", model: "Cylindrical Vertical Heater", country: "USA", priceEur: 1800000, priceDisplay: "€1.8M/unit (at 2+)", efficiency: "91% thermal eff.", scaleThreshold: "2+ units, shared stack", leadTimeMonths: 16, trl: 9 },
  },

  /* ═══════════════════════════ FLUE GAS COOLER ═══════════════════════════ */
  {
    keywords: ["flue gas cooler"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Wallstein", model: "FGC Economizer Package", country: "Germany", priceEur: 120000, priceDisplay: "€120k", efficiency: "Flue gas to 120°C, 5% fuel saving", leadTimeMonths: 6, trl: 9 },
    bestEfficiency: { manufacturer: "Aalborg Energie Technik", model: "Condensing Flue Gas Cooler", country: "Denmark", priceEur: 280000, priceDisplay: "€280k", efficiency: "Flue gas to 50°C, 12% fuel saving", leadTimeMonths: 10, trl: 9 },
    economiesOfScale: { manufacturer: "Cannon Bono Energia", model: "Modular FGC Recovery", country: "Italy", priceEur: 180000, priceDisplay: "€180k/unit (at 3+)", efficiency: "Flue gas to 90°C, 8% fuel saving", scaleThreshold: "3+ units, shared condensate system", leadTimeMonths: 8, trl: 9 },
  },

  /* ═══════════════════════════ WASTE HEAT RECOVERY UNIT ═══════════════════════════ */
  {
    keywords: ["waste heat recovery"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Thermax", model: "WHRB 10 tph Waste Heat Boiler", country: "India", priceEur: 650000, priceDisplay: "€650k", efficiency: "82% heat recovery, 10 bar steam", leadTimeMonths: 10, trl: 9 },
    bestEfficiency: { manufacturer: "NEM Energy", model: "DrumPlus WHRU, 40 bar", country: "Netherlands", priceEur: 1800000, priceDisplay: "€1.8M", efficiency: "92% heat recovery, dual pressure", leadTimeMonths: 16, trl: 9 },
    economiesOfScale: { manufacturer: "Sofinter", model: "Modular WHRU Package", country: "Italy", priceEur: 1200000, priceDisplay: "€1.2M/unit (at 2+)", efficiency: "87% heat recovery", scaleThreshold: "2+ units, shared steam header", leadTimeMonths: 14, trl: 9 },
  },

  /* ═══════════════════════════ ORC UNIT ═══════════════════════════ */
  {
    keywords: ["organic rankine cycle", "orc"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Turboden (Mitsubishi)", model: "T10 CHP ORC 1 MW", country: "Italy", priceEur: 1200000, priceDisplay: "€1.2M", efficiency: "18% net electrical, 85°C+ source", leadTimeMonths: 10, trl: 9 },
    bestEfficiency: { manufacturer: "ORMAT Technologies", model: "ORMAT Energy Converter 5 MW", country: "USA", priceEur: 4500000, priceDisplay: "€4.5M", efficiency: "23% net electrical, binary cycle", leadTimeMonths: 16, trl: 9 },
    economiesOfScale: { manufacturer: "Exergy International", model: "Radial Outflow ORC 2 MW", country: "Italy", priceEur: 2200000, priceDisplay: "€2.2M/unit (at 2+)", efficiency: "20% net electrical", scaleThreshold: "2+ units, modular deployment", leadTimeMonths: 12, trl: 9 },
  },

  /* ═══════════════════════════ REFRIGERATION SYSTEM ═══════════════════════════ */
  {
    keywords: ["refrigeration system"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "GEA", model: "GEA Grasso Screw Chiller 500 kW", country: "Germany", priceEur: 280000, priceDisplay: "€280k", efficiency: "COP 4.5, NH₃ R717", leadTimeMonths: 6, trl: 9 },
    bestEfficiency: { manufacturer: "Star Refrigeration", model: "Azanechiller 2.0 NH₃ 1.5 MW", country: "UK", priceEur: 650000, priceDisplay: "€650k", efficiency: "COP 6.0, low charge ammonia", leadTimeMonths: 12, trl: 9 },
    economiesOfScale: { manufacturer: "Johnson Controls (Sabroe)", model: "SABROEcool Cascade System", country: "Denmark", priceEur: 450000, priceDisplay: "€450k/unit (at 2+)", efficiency: "COP 5.2, CO₂/NH₃ cascade", scaleThreshold: "2+ units, shared machine room", leadTimeMonths: 10, trl: 9 },
  },

  /* ═══════════════════════════ ELECTROSTATIC PRECIPITATOR ═══════════════════════════ */
  {
    keywords: ["electrostatic precipitator", "esp"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "FLSmidth", model: "ESP-4 Plate Precipitator", country: "Denmark", priceEur: 850000, priceDisplay: "€850k", efficiency: "99.5% PM removal, 3 fields", leadTimeMonths: 12, trl: 9 },
    bestEfficiency: { manufacturer: "Babcock & Wilcox", model: "Wet ESP (WESP)", country: "USA", priceEur: 1800000, priceDisplay: "€1.8M", efficiency: "99.9% PM removal, sub-micron", leadTimeMonths: 16, trl: 9 },
    economiesOfScale: { manufacturer: "Thermax", model: "Modular Dry ESP", country: "India", priceEur: 1100000, priceDisplay: "€1.1M/unit (at 2+)", efficiency: "99.7% PM removal", scaleThreshold: "2+ units, shared TR sets", leadTimeMonths: 14, trl: 9 },
  },

  /* ═══════════════════════════ SCRUBBER ═══════════════════════════ */
  {
    keywords: ["scrubber", "flue gas desulfurization", "fgd"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Ducon Technologies", model: "Packed Tower Scrubber", country: "USA", priceEur: 350000, priceDisplay: "€350k", efficiency: "95% SOx removal", leadTimeMonths: 8, trl: 9 },
    bestEfficiency: { manufacturer: "Andritz", model: "Spray-Tower FGD, limestone/gypsum", country: "Austria", priceEur: 1200000, priceDisplay: "€1.2M", efficiency: "99% SOx removal, gypsum byproduct", leadTimeMonths: 14, trl: 9 },
    economiesOfScale: { manufacturer: "GE Vernova (ECOS)", model: "Seawater FGD System", country: "USA", priceEur: 800000, priceDisplay: "€800k/train (at 2+)", efficiency: "97% SOx removal", scaleThreshold: "2+ trains, shared reagent prep", leadTimeMonths: 12, trl: 9 },
  },

  /* ═══════════════════════════ CO2 PURIFICATION UNIT ═══════════════════════════ */
  {
    keywords: ["co2 purification"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Air Liquide Engineering", model: "Cryocap™ CO₂ Purification", country: "France", priceEur: 1200000, priceDisplay: "€1.2M", efficiency: "99.9% CO₂ purity, food grade", leadTimeMonths: 12, trl: 9 },
    bestEfficiency: { manufacturer: "Linde Engineering", model: "RECTISOL® CO₂ Polish", country: "Germany", priceEur: 2500000, priceDisplay: "€2.5M", efficiency: "99.99% CO₂, <1 ppm impurities", leadTimeMonths: 16, trl: 9 },
    economiesOfScale: { manufacturer: "Wärtsilä (Hamworthy)", model: "CO₂ Liquefaction & Polish Train", country: "Norway", priceEur: 1800000, priceDisplay: "€1.8M/train (at 2+)", efficiency: "99.95% CO₂ purity", scaleThreshold: "2+ trains, shared cold box", leadTimeMonths: 14, trl: 9 },
  },

  /* ═══════════════════════════ SYNGAS CLEANUP UNIT ═══════════════════════════ */
  {
    keywords: ["syngas cleanup"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Haldor Topsoe (Topsoe)", model: "CataGuard™ Guard Bed System", country: "Denmark", priceEur: 450000, priceDisplay: "€450k", efficiency: "H₂S < 0.1 ppm, HCl removal", leadTimeMonths: 8, trl: 9 },
    bestEfficiency: { manufacturer: "Johnson Matthey", model: "PURASPEC™ Multi-Stage Cleanup", country: "UK", priceEur: 1100000, priceDisplay: "€1.1M", efficiency: "< 10 ppb total sulfur", leadTimeMonths: 14, trl: 9 },
    economiesOfScale: { manufacturer: "BASF (Catalyst Division)", model: "Puristar® R3-15 Guard System", country: "Germany", priceEur: 750000, priceDisplay: "€750k/train (at 2+)", efficiency: "H₂S < 0.05 ppm", scaleThreshold: "2+ trains, lead-lag configuration", leadTimeMonths: 10, trl: 9 },
  },

  /* ═══════════════════════════ SULFUR REMOVAL UNIT ═══════════════════════════ */
  {
    keywords: ["sulfur removal"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Merichem", model: "LO-CAT® II Liquid Redox", country: "USA", priceEur: 380000, priceDisplay: "€380k", efficiency: "99.9% H₂S removal, elemental S byproduct", leadTimeMonths: 8, trl: 9 },
    bestEfficiency: { manufacturer: "Shell Catalysts & Technologies", model: "Shell Sulfinol-X™", country: "Netherlands", priceEur: 950000, priceDisplay: "€950k", efficiency: "> 99.99%, bulk + fine removal", leadTimeMonths: 14, trl: 9 },
    economiesOfScale: { manufacturer: "Axens (IFP)", model: "SulphurGard™ Guard Beds", country: "France", priceEur: 550000, priceDisplay: "€550k/train (at 2+)", efficiency: "99.95% H₂S removal", scaleThreshold: "2+ trains, in-situ regeneration", leadTimeMonths: 10, trl: 9 },
  },

  /* ═══════════════════════════ H2S SCAVENGER BED ═══════════════════════════ */
  {
    keywords: ["h2s scavenger"],
    pricingUnit: "€ per unit",
    plantScaleQty: 2,
    bestPrice: { manufacturer: "Schlumberger (SLB)", model: "SULFATREAT® Granular", country: "USA", priceEur: 45000, priceDisplay: "€45k", efficiency: "Loading 25 lb S/100 lb media", leadTimeMonths: 3, trl: 9 },
    bestEfficiency: { manufacturer: "Molecular Products", model: "SOFNOLIME® SG H₂S Absorbent", country: "UK", priceEur: 85000, priceDisplay: "€85k", efficiency: "Loading 40 lb S/100 lb, CO₂ co-removal", leadTimeMonths: 5, trl: 9 },
    economiesOfScale: { manufacturer: "BASF", model: "Sorbead® H₂S Guard Bed", country: "Germany", priceEur: 62000, priceDisplay: "€62k/bed (at 4+ lead-lag)", efficiency: "Loading 30 lb S/100 lb", scaleThreshold: "4+ beds, rolling changeout schedule", leadTimeMonths: 4, trl: 9 },
  },

  /* ═══════════════════════════ AMINE TREATING UNIT ═══════════════════════════ */
  {
    keywords: ["amine treating", "amine unit"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Prosernat (TotalEnergies)", model: "AdvAmine™ MDEA Unit", country: "France", priceEur: 1500000, priceDisplay: "€1.5M", efficiency: "CO₂ < 50 ppm, low reboiler duty", leadTimeMonths: 12, trl: 9 },
    bestEfficiency: { manufacturer: "Shell Catalysts & Technologies", model: "CANSOLV™ DC-103 Amine", country: "Netherlands", priceEur: 3200000, priceDisplay: "€3.2M", efficiency: "CO₂ < 10 ppm, 2.3 GJ/tCO₂ reboiler", leadTimeMonths: 18, trl: 9 },
    economiesOfScale: { manufacturer: "Fluor", model: "Econamine FG Plus™", country: "USA", priceEur: 2200000, priceDisplay: "€2.2M/train (at 2+)", efficiency: "CO₂ < 25 ppm", scaleThreshold: "2+ trains, shared regen column", leadTimeMonths: 16, trl: 9 },
  },

  /* ═══════════════════════════ ADSORPTION PURIFICATION UNIT ═══════════════════════════ */
  {
    keywords: ["adsorption purification"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Chemviron (Calgon Carbon)", model: "Activated Carbon Vessel ACV-800", country: "Belgium", priceEur: 65000, priceDisplay: "€65k", efficiency: "VOC removal > 99%, regenerable", leadTimeMonths: 5, trl: 9 },
    bestEfficiency: { manufacturer: "CECA (Arkema)", model: "Molecular Sieve 13X Adsorber", country: "France", priceEur: 180000, priceDisplay: "€180k", efficiency: "H₂O to < 1 ppm, CO₂ to < 10 ppm", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "UOP (Honeywell)", model: "MOLSIV™ Adsorption System", country: "USA", priceEur: 120000, priceDisplay: "€120k/vessel (at 4+)", efficiency: "TSA/PSA, multi-contaminant", scaleThreshold: "4+ vessels, shared regeneration gas", leadTimeMonths: 7, trl: 9 },
  },

  /* ═══════════════════════════ DRYER UNIT ═══════════════════════════ */
  {
    keywords: ["dryer unit", "gas dryer", "desiccant dryer"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "SPX Flow", model: "Hankison HES Series Desiccant", country: "USA", priceEur: 35000, priceDisplay: "€35k", efficiency: "Dew point -40°C, heatless regen", leadTimeMonths: 4, trl: 9 },
    bestEfficiency: { manufacturer: "Beko Technologies", model: "DRYPOINT XC Plus", country: "Germany", priceEur: 85000, priceDisplay: "€85k", efficiency: "Dew point -70°C, heated regen", leadTimeMonths: 7, trl: 9 },
    economiesOfScale: { manufacturer: "Atlas Copco", model: "CD+ 2500 Desiccant Dryer", country: "Belgium", priceEur: 55000, priceDisplay: "€55k/unit (at 3+)", efficiency: "Dew point -40°C, energy-saving regen", scaleThreshold: "3+ units, N+1 redundancy", leadTimeMonths: 5, trl: 9 },
  },

  /* ═══════════════════════════ DEOXIDATION UNIT ═══════════════════════════ */
  {
    keywords: ["deoxidation", "deoxo"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "BASF", model: "DeoxoTech™ Catalytic Deoxo", country: "Germany", priceEur: 85000, priceDisplay: "€85k", efficiency: "O₂ < 1 ppm, Pd catalyst", leadTimeMonths: 5, trl: 9 },
    bestEfficiency: { manufacturer: "Johnson Matthey", model: "HiFUEL® DeOx Reactor", country: "UK", priceEur: 160000, priceDisplay: "€160k", efficiency: "O₂ < 0.1 ppm, Pt/Pd catalyst", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "Clariant", model: "OxyTrap™ Guard Beds", country: "Switzerland", priceEur: 110000, priceDisplay: "€110k/unit (at 2+)", efficiency: "O₂ < 0.5 ppm, extended life", scaleThreshold: "2+ units, lead-lag operation", leadTimeMonths: 6, trl: 9 },
  },

  /* ═══════════════════════════ SOLVENT REGENERATION UNIT ═══════════════════════════ */
  {
    keywords: ["solvent regeneration"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Koch Modular Process", model: "Stripper Column Regen Package", country: "USA", priceEur: 450000, priceDisplay: "€450k", efficiency: "95% solvent recovery, 3.0 GJ/t", leadTimeMonths: 10, trl: 9 },
    bestEfficiency: { manufacturer: "Sulzer Chemtech", model: "Advanced Reboiled Stripper", country: "Switzerland", priceEur: 950000, priceDisplay: "€950k", efficiency: "99% solvent recovery, 2.2 GJ/t", leadTimeMonths: 14, trl: 9 },
    economiesOfScale: { manufacturer: "Aker Solutions", model: "Mobile Regen Skid", country: "Norway", priceEur: 680000, priceDisplay: "€680k/train (at 2+)", efficiency: "97% solvent recovery, 2.6 GJ/t", scaleThreshold: "2+ trains, shared reboiler steam", leadTimeMonths: 12, trl: 9 },
  },

  /* ═══════════════════════════ REVERSE OSMOSIS UNIT ═══════════════════════════ */
  {
    keywords: ["reverse osmosis"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Toray Industries", model: "TMG20D-400 RO Membrane Train", country: "Japan", priceEur: 120000, priceDisplay: "€120k", efficiency: "99.7% salt rejection, 45 m³/h", leadTimeMonths: 5, trl: 9 },
    bestEfficiency: { manufacturer: "DuPont (FilmTec)", model: "XLE-440 Low-Energy RO", country: "USA", priceEur: 250000, priceDisplay: "€250k", efficiency: "99.8% rejection, 15% less energy", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "LG Chem (LG Water)", model: "LG BW 400 ES RO System", country: "South Korea", priceEur: 165000, priceDisplay: "€165k/train (at 3+)", efficiency: "99.7% rejection", scaleThreshold: "3+ trains, shared CIP system", leadTimeMonths: 6, trl: 9 },
  },

  /* ═══════════════════════════ ION EXCHANGE UNIT ═══════════════════════════ */
  {
    keywords: ["ion exchange"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Purolite", model: "Shallow Shell Cation/Anion IX", country: "UK", priceEur: 65000, priceDisplay: "€65k", efficiency: "< 1 µS/cm, 30 m³/h", leadTimeMonths: 5, trl: 9 },
    bestEfficiency: { manufacturer: "Lanxess (Lewatit)", model: "MonoPlus TP207 Chelating IX", country: "Germany", priceEur: 140000, priceDisplay: "€140k", efficiency: "Selective heavy metal removal, ppb level", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "DuPont Water Solutions", model: "AmberLite™ HPR IX System", country: "USA", priceEur: 95000, priceDisplay: "€95k/vessel (at 4+)", efficiency: "< 0.5 µS/cm", scaleThreshold: "4+ vessels, counter-current regen", leadTimeMonths: 6, trl: 9 },
  },

  /* ═══════════════════════════ ULTRAFILTRATION UNIT ═══════════════════════════ */
  {
    keywords: ["ultrafiltration"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Pall Water", model: "Aria™ AP-4 UF Module", country: "USA", priceEur: 85000, priceDisplay: "€85k", efficiency: "0.02 µm, 100 m³/h", leadTimeMonths: 5, trl: 9 },
    bestEfficiency: { manufacturer: "SUEZ (ZeeWeed)", model: "ZeeWeed 700B UF", country: "Canada", priceEur: 180000, priceDisplay: "€180k", efficiency: "0.01 µm, immersed membrane", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "Pentair (X-Flow)", model: "Aquaflex UF Rack", country: "Netherlands", priceEur: 120000, priceDisplay: "€120k/rack (at 4+)", efficiency: "0.02 µm, compact footprint", scaleThreshold: "4+ racks, shared backwash", leadTimeMonths: 6, trl: 9 },
  },

  /* ═══════════════════════════ ACTIVATED CARBON FILTER ═══════════════════════════ */
  {
    keywords: ["activated carbon filter"],
    pricingUnit: "€ per unit",
    plantScaleQty: 4,
    bestPrice: { manufacturer: "Jacobi Carbons", model: "EcoSorb GX Series Vessel", country: "Sweden", priceEur: 25000, priceDisplay: "€25k", efficiency: "Iodine # >1000, chlorine removal", leadTimeMonths: 3, trl: 9 },
    bestEfficiency: { manufacturer: "Calgon Carbon (Kuraray)", model: "F400 GAC Adsorber", country: "USA", priceEur: 55000, priceDisplay: "€55k", efficiency: "Iodine # >1100, TOC < 0.1 ppm", leadTimeMonths: 5, trl: 9 },
    economiesOfScale: { manufacturer: "Norit (Cabot)", model: "GAC 1240 Plus Vessel", country: "Netherlands", priceEur: 35000, priceDisplay: "€35k/vessel (at 6+)", efficiency: "Iodine # >1050", scaleThreshold: "6+ vessels, reactivation contract", leadTimeMonths: 4, trl: 9 },
  },

  /* ═══════════════════════════ WATER SOFTENER ═══════════════════════════ */
  {
    keywords: ["water softener"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Culligan", model: "HE Progressive Flow Softener", country: "USA", priceEur: 18000, priceDisplay: "€18k", efficiency: "< 1 ppm hardness, 50 m³/h", leadTimeMonths: 3, trl: 9 },
    bestEfficiency: { manufacturer: "Veolia (ELGA)", model: "PURELAB Flex Softener", country: "UK", priceEur: 38000, priceDisplay: "€38k", efficiency: "< 0.1 ppm hardness, smart regen", leadTimeMonths: 5, trl: 9 },
    economiesOfScale: { manufacturer: "BWT", model: "Rondomat Duo Industrial", country: "Austria", priceEur: 25000, priceDisplay: "€25k/unit (at 3+)", efficiency: "< 0.5 ppm hardness, duplex operation", scaleThreshold: "3+ units, continuous supply", leadTimeMonths: 4, trl: 9 },
  },

  /* ═══════════════════════════ COOLING WATER TREATMENT UNIT ═══════════════════════════ */
  {
    keywords: ["cooling water treatment"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Nalco (Ecolab)", model: "3D TRASAR™ Cooling System", country: "USA", priceEur: 65000, priceDisplay: "€65k", efficiency: "Cycles of concentration 6–8", leadTimeMonths: 4, trl: 9 },
    bestEfficiency: { manufacturer: "Kurita Water Industries", model: "ACRESSystem™ CWT", country: "Japan", priceEur: 140000, priceDisplay: "€140k", efficiency: "Cycles 8–10, biocide-free", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "Solenis", model: "OnGuard™ 3C Controller + Chemical Feed", country: "USA", priceEur: 95000, priceDisplay: "€95k/loop (at 3+)", efficiency: "Cycles 7, auto-blowdown", scaleThreshold: "3+ loops, centralized chemical storage", leadTimeMonths: 5, trl: 9 },
  },

  /* ═══════════════════════════ EFFLUENT NEUTRALIZATION UNIT ═══════════════════════════ */
  {
    keywords: ["effluent neutralization"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Prominent", model: "Dulcodes pH Neutralization Skid", country: "Germany", priceEur: 35000, priceDisplay: "€35k", efficiency: "pH 6–9 discharge, NaOH/HCl dosing", leadTimeMonths: 4, trl: 9 },
    bestEfficiency: { manufacturer: "Veolia Water Technologies", model: "Actiflo® Neutralization System", country: "France", priceEur: 120000, priceDisplay: "€120k", efficiency: "pH ± 0.2 control, micro-sand settling", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "Evoqua (Xylem)", model: "Neutralex™ System", country: "USA", priceEur: 75000, priceDisplay: "€75k/unit (at 2+)", efficiency: "pH 6.5–8.5, limestone bed", scaleThreshold: "2+ units, shared chemical tank", leadTimeMonths: 6, trl: 9 },
  },

  /* ═══════════════════════════ WASTEWATER TREATMENT UNIT ═══════════════════════════ */
  {
    keywords: ["wastewater treatment"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Aqua-Pure Ventures", model: "MBBR Wastewater Package 50 m³/h", country: "India", priceEur: 280000, priceDisplay: "€280k", efficiency: "BOD < 20 mg/L, biological", leadTimeMonths: 8, trl: 9 },
    bestEfficiency: { manufacturer: "SUEZ", model: "LEAPmbr Membrane Bioreactor", country: "France", priceEur: 750000, priceDisplay: "€750k", efficiency: "BOD < 5 mg/L, TSS < 1 mg/L", leadTimeMonths: 14, trl: 9 },
    economiesOfScale: { manufacturer: "Veolia Water Technologies", model: "Biothane UASB + Aerobic", country: "Netherlands", priceEur: 480000, priceDisplay: "€480k/train (at 2+)", efficiency: "COD removal > 95%, biogas recovery", scaleThreshold: "2+ trains, shared sludge handling", leadTimeMonths: 10, trl: 9 },
  },

  /* ═══════════════════════════ SLUDGE DEWATERING UNIT ═══════════════════════════ */
  {
    keywords: ["sludge dewatering"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Andritz", model: "Belt Press SMX-Q", country: "Austria", priceEur: 120000, priceDisplay: "€120k", efficiency: "25% dry solids, 30 m³/h", leadTimeMonths: 6, trl: 9 },
    bestEfficiency: { manufacturer: "Alfa Laval", model: "ALDEC G3 Decanter Centrifuge", country: "Sweden", priceEur: 320000, priceDisplay: "€320k", efficiency: "35% dry solids, polymer optimized", leadTimeMonths: 10, trl: 9 },
    economiesOfScale: { manufacturer: "Flottweg", model: "Xelletor Series Centrifuge", country: "Germany", priceEur: 220000, priceDisplay: "€220k/unit (at 2+)", efficiency: "30% dry solids, energy-saving", scaleThreshold: "2+ units, shared polymer prep", leadTimeMonths: 8, trl: 9 },
  },

  /* ═══════════════════════════ BRINE CONCENTRATOR ═══════════════════════════ */
  {
    keywords: ["brine concentrator"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Veolia (HPD)", model: "BRINE Concentrator BC-100", country: "USA", priceEur: 1500000, priceDisplay: "€1.5M", efficiency: "95% water recovery, 250 g/L TDS", leadTimeMonths: 14, trl: 9 },
    bestEfficiency: { manufacturer: "Saltworks Technologies", model: "SaltMaker Evaporator Crystallizer", country: "Canada", priceEur: 2800000, priceDisplay: "€2.8M", efficiency: "99% recovery, ZLD capable", leadTimeMonths: 18, trl: 8 },
    economiesOfScale: { manufacturer: "Aquatech International", model: "EVRAS Brine Concentrator", country: "USA", priceEur: 2000000, priceDisplay: "€2M/unit (at 2+)", efficiency: "97% recovery", scaleThreshold: "2+ units, shared crystallizer", leadTimeMonths: 16, trl: 9 },
  },

  /* ═══════════════════════════ EVAPORATOR ═══════════════════════════ */
  {
    keywords: ["evaporator"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "GEA", model: "Forced Circulation Evaporator FCV", country: "Germany", priceEur: 350000, priceDisplay: "€350k", efficiency: "4-effect, 0.25 kg steam/kg evap.", leadTimeMonths: 10, trl: 9 },
    bestEfficiency: { manufacturer: "Alfa Laval", model: "AlfaVap MVR Evaporator", country: "Sweden", priceEur: 750000, priceDisplay: "€750k", efficiency: "MVR, 0.04 kWh/kg evap.", leadTimeMonths: 14, trl: 9 },
    economiesOfScale: { manufacturer: "Veolia (HPD)", model: "Multi-Effect Falling Film", country: "USA", priceEur: 520000, priceDisplay: "€520k/effect (at 4+)", efficiency: "6-effect, 0.17 kg steam/kg", scaleThreshold: "4+ effects, shared condenser", leadTimeMonths: 12, trl: 9 },
  },

  /* ═══════════════════════════ CRYSTALLIZER ═══════════════════════════ */
  {
    keywords: ["crystallizer"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Swenson Technology (Komline-Sanderson)", model: "DTB Crystallizer", country: "USA", priceEur: 650000, priceDisplay: "€650k", efficiency: "Mean crystal 500 µm, 90% yield", leadTimeMonths: 12, trl: 9 },
    bestEfficiency: { manufacturer: "GEA", model: "Oslo-Type Forced Circ. Crystallizer", country: "Germany", priceEur: 1200000, priceDisplay: "€1.2M", efficiency: "Mean crystal 1.5 mm, 98% yield", leadTimeMonths: 16, trl: 9 },
    economiesOfScale: { manufacturer: "Veolia (HPD)", model: "Forced Circulation ZLD Crystallizer", country: "USA", priceEur: 900000, priceDisplay: "€900k/unit (at 2+)", efficiency: "Mean crystal 800 µm, 95% yield", scaleThreshold: "2+ units, shared centrifuge", leadTimeMonths: 14, trl: 9 },
  },

  /* ═══════════════════════════ AIR SEPARATION UNIT ═══════════════════════════ */
  {
    keywords: ["air separation unit"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Kaifeng Air Separation", model: "KDON-3000/3000 ASU", country: "China", priceEur: 3500000, priceDisplay: "€3.5M", efficiency: "0.40 kWh/Nm³ O₂, N₂ co-product", leadTimeMonths: 12, trl: 9 },
    bestEfficiency: { manufacturer: "Air Products", model: "Large Tonnage Cryogenic ASU", country: "USA", priceEur: 9500000, priceDisplay: "€9.5M", efficiency: "0.30 kWh/Nm³ O₂, Ar co-production", leadTimeMonths: 22, trl: 9 },
    economiesOfScale: { manufacturer: "Messer", model: "Modular ASU 5000 tpd O₂", country: "Germany", priceEur: 7200000, priceDisplay: "€7.2M/train (at 2+)", efficiency: "0.33 kWh/Nm³ O₂", scaleThreshold: "2+ trains, shared cold box", leadTimeMonths: 20, trl: 9 },
  },

  /* ═══════════════════════════ NITROGEN GENERATION UNIT ═══════════════════════════ */
  {
    keywords: ["nitrogen generation", "n2 generator"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Parker Hannifin", model: "NITROSource PSA N₂ 500 Nm³/h", country: "USA", priceEur: 120000, priceDisplay: "€120k", efficiency: "99.5% N₂ purity, PSA", leadTimeMonths: 5, trl: 9 },
    bestEfficiency: { manufacturer: "Atlas Copco", model: "NGP+ 1500 Membrane N₂", country: "Belgium", priceEur: 280000, priceDisplay: "€280k", efficiency: "99.999% N₂, membrane + deoxo", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "Air Products", model: "PRISM® Membrane N₂ Modular", country: "USA", priceEur: 180000, priceDisplay: "€180k/unit (at 3+)", efficiency: "99.9% N₂", scaleThreshold: "3+ units, plant-wide N₂ header", leadTimeMonths: 6, trl: 9 },
  },

  /* ═══════════════════════════ OXYGEN GENERATION UNIT ═══════════════════════════ */
  {
    keywords: ["oxygen generation", "o2 generator"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Novair", model: "OXYSWING PSA O₂ 200 Nm³/h", country: "France", priceEur: 150000, priceDisplay: "€150k", efficiency: "93% O₂ purity, VPSA", leadTimeMonths: 6, trl: 9 },
    bestEfficiency: { manufacturer: "Linde Engineering", model: "LOXDEAL™ VPSA O₂", country: "Germany", priceEur: 450000, priceDisplay: "€450k", efficiency: "95% O₂, 0.35 kWh/Nm³", leadTimeMonths: 10, trl: 9 },
    economiesOfScale: { manufacturer: "Air Liquide", model: "Modular VPSA O₂ 500 tpd", country: "France", priceEur: 320000, priceDisplay: "€320k/unit (at 2+)", efficiency: "93% O₂", scaleThreshold: "2+ units, shared vacuum system", leadTimeMonths: 8, trl: 9 },
  },

  /* ═══════════════════════════ DAC CONTACTOR ═══════════════════════════ */
  {
    keywords: ["dac contactor"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Carbon Engineering (Occidental)", model: "Liquid Solvent Contactor L1", country: "Canada", priceEur: 2500000, priceDisplay: "€2.5M", efficiency: "1 MtCO₂/yr design, KOH solvent", leadTimeMonths: 18, trl: 7 },
    bestEfficiency: { manufacturer: "Climeworks", model: "Orca Solid Sorbent Contactor", country: "Switzerland", priceEur: 4500000, priceDisplay: "€4.5M", efficiency: "99% capture, 80°C regen heat", leadTimeMonths: 22, trl: 8 },
    economiesOfScale: { manufacturer: "Global Thermostat (Woodside)", model: "Modular DAC Contactor Unit", country: "USA", priceEur: 3200000, priceDisplay: "€3.2M/unit (at 10+)", efficiency: "Low-grade heat regen, <100°C", scaleThreshold: "10+ units, mega-scale hub", leadTimeMonths: 20, trl: 7 },
  },

  /* ═══════════════════════════ DAC REGENERATION UNIT ═══════════════════════════ */
  {
    keywords: ["dac regeneration"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Carbon Engineering", model: "Calciner / Pellet Reactor", country: "Canada", priceEur: 3500000, priceDisplay: "€3.5M", efficiency: "900°C calcination, CaCO₃ to CaO", leadTimeMonths: 18, trl: 7 },
    bestEfficiency: { manufacturer: "Climeworks", model: "Vacuum Steam Regenerator", country: "Switzerland", priceEur: 2800000, priceDisplay: "€2.8M", efficiency: "80–120°C, low-temp waste heat", leadTimeMonths: 20, trl: 8 },
    economiesOfScale: { manufacturer: "Svante (formerly Inventys)", model: "Veloxotherm™ Rapid TSA Regen", country: "Canada", priceEur: 3000000, priceDisplay: "€3M/unit (at 4+)", efficiency: "6-min cycle time, rotary TSA", scaleThreshold: "4+ units, shared CO₂ compression", leadTimeMonths: 18, trl: 7 },
  },

  /* ═══════════════════════════ DIRECT OCEAN CAPTURE ═══════════════════════════ */
  {
    keywords: ["direct ocean capture", "doc"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Ebb Carbon", model: "Electrochemical Ocean Alkalinity Module", country: "USA", priceEur: 1800000, priceDisplay: "€1.8M", efficiency: "1000 tCO₂/yr, electrochemical", leadTimeMonths: 14, trl: 5 },
    bestEfficiency: { manufacturer: "Equatic", model: "Aqueous Electrolysis DOC", country: "USA", priceEur: 3500000, priceDisplay: "€3.5M", efficiency: "3600 tCO₂/yr, H₂ co-product", leadTimeMonths: 18, trl: 6 },
    economiesOfScale: { manufacturer: "Captura", model: "Electrodialysis Ocean Module", country: "USA", priceEur: 2500000, priceDisplay: "€2.5M/unit (at 5+)", efficiency: "2000 tCO₂/yr", scaleThreshold: "5+ units, coastal hub deployment", leadTimeMonths: 16, trl: 5 },
  },

  /* ═══════════════════════════ GASIFIER (already exists, adding pyrolysis) ═══════════════════════════ */

  /* ═══════════════════════════ PYROLYSIS REACTOR ═══════════════════════════ */
  {
    keywords: ["pyrolysis reactor", "pyrolysis"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "BTG Bioliquids", model: "Empyro Fast Pyrolysis 5 tph", country: "Netherlands", priceEur: 3200000, priceDisplay: "€3.2M", efficiency: "70% bio-oil yield, 500°C", leadTimeMonths: 16, trl: 8 },
    bestEfficiency: { manufacturer: "Ensyn (Enviva)", model: "RTP™ Circulating Fluidized Bed", country: "Canada", priceEur: 6500000, priceDisplay: "€6.5M", efficiency: "75% bio-oil yield, rapid quench", leadTimeMonths: 20, trl: 8 },
    economiesOfScale: { manufacturer: "Agilyx", model: "Mixed Plastic Pyrolysis System", country: "USA", priceEur: 4800000, priceDisplay: "€4.8M/line (at 2+)", efficiency: "65% oil yield, mixed feedstock", scaleThreshold: "2+ lines, shared quench & refining", leadTimeMonths: 18, trl: 7 },
  },

  /* ═══════════════════════════ HYDROTHERMAL LIQUEFACTION UNIT ═══════════════════════════ */
  {
    keywords: ["hydrothermal liquefaction", "htl"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Steeper Energy", model: "Hydrofaction™ HTL Pilot 5 bbl/d", country: "Denmark", priceEur: 5500000, priceDisplay: "€5.5M", efficiency: "45% bio-crude yield, 400°C / 300 bar", leadTimeMonths: 20, trl: 6 },
    bestEfficiency: { manufacturer: "Licella (iQRenew)", model: "Cat-HTR™ Catalytic HTL", country: "Australia", priceEur: 9500000, priceDisplay: "€9.5M", efficiency: "55% bio-crude yield, catalytic", leadTimeMonths: 24, trl: 7 },
    economiesOfScale: { manufacturer: "Topsoe / Steeper Energy", model: "Hydrofaction Commercial 100 bbl/d", country: "Denmark", priceEur: 18000000, priceDisplay: "€18M/train (at 2+)", efficiency: "50% bio-crude yield", scaleThreshold: "2+ trains, shared upgrading", leadTimeMonths: 28, trl: 6 },
  },

  /* ═══════════════════════════ TORREFACTION UNIT ═══════════════════════════ */
  {
    keywords: ["torrefaction"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Topell Energy", model: "Torbed Reactor 10 tph", country: "Netherlands", priceEur: 2200000, priceDisplay: "€2.2M", efficiency: "90% energy yield, 280°C", leadTimeMonths: 12, trl: 8 },
    bestEfficiency: { manufacturer: "ECN/TNO", model: "BO2-Technology Torrefaction", country: "Netherlands", priceEur: 4200000, priceDisplay: "€4.2M", efficiency: "95% energy yield, densified pellets", leadTimeMonths: 16, trl: 8 },
    economiesOfScale: { manufacturer: "Andritz", model: "ACB Torrefaction Module", country: "Austria", priceEur: 3000000, priceDisplay: "€3M/line (at 2+)", efficiency: "92% energy yield", scaleThreshold: "2+ lines, shared pelletizer", leadTimeMonths: 14, trl: 8 },
  },

  /* ═══════════════════════════ BIOMASS COMBUSTION UNIT ═══════════════════════════ */
  {
    keywords: ["biomass combustion"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "ANDRITZ", model: "BFB Boiler 30 MWth", country: "Austria", priceEur: 4500000, priceDisplay: "€4.5M", efficiency: "88% thermal eff., multi-fuel", leadTimeMonths: 14, trl: 9 },
    bestEfficiency: { manufacturer: "Valmet", model: "CFB Boiler 100 MWth", country: "Finland", priceEur: 12000000, priceDisplay: "€12M", efficiency: "92% thermal eff., ultra-low emissions", leadTimeMonths: 22, trl: 9 },
    economiesOfScale: { manufacturer: "Babcock & Wilcox", model: "Stirling Biomass Boiler Modular", country: "USA", priceEur: 7500000, priceDisplay: "€7.5M/unit (at 2+)", efficiency: "90% thermal eff.", scaleThreshold: "2+ units, shared fuel handling", leadTimeMonths: 18, trl: 9 },
  },

  /* ═══════════════════════════ ANAEROBIC DIGESTER ═══════════════════════════ */
  {
    keywords: ["anaerobic digester", "digester"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Envitec Biogas", model: "CSTR Digester 5000 m³", country: "Germany", priceEur: 1200000, priceDisplay: "€1.2M", efficiency: "60% VS destruction, mesophilic", leadTimeMonths: 10, trl: 9 },
    bestEfficiency: { manufacturer: "Weltec Biopower", model: "Stainless Steel CSTR 6000 m³", country: "Germany", priceEur: 2500000, priceDisplay: "€2.5M", efficiency: "75% VS destruction, thermophilic", leadTimeMonths: 14, trl: 9 },
    economiesOfScale: { manufacturer: "BTS Biogas", model: "Modular Digester 4000 m³", country: "Italy", priceEur: 1800000, priceDisplay: "€1.8M/unit (at 3+)", efficiency: "68% VS destruction", scaleThreshold: "3+ units, shared gas upgrading", leadTimeMonths: 12, trl: 9 },
  },

  /* ═══════════════════════════ BIOGAS UPGRADING UNIT ═══════════════════════════ */
  {
    keywords: ["biogas upgrading"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Greenlane Biogas", model: "Pressure Swing Adsorption 500 Nm³/h", country: "Canada", priceEur: 350000, priceDisplay: "€350k", efficiency: "97% CH₄ recovery, PSA", leadTimeMonths: 8, trl: 9 },
    bestEfficiency: { manufacturer: "Pentair Haffmans", model: "Membrane Biogas Upgrader", country: "Netherlands", priceEur: 650000, priceDisplay: "€650k", efficiency: "99.5% CH₄, 3-stage membrane", leadTimeMonths: 10, trl: 9 },
    economiesOfScale: { manufacturer: "Bright Biomethane", model: "Containerized Membrane Upgrader", country: "Netherlands", priceEur: 480000, priceDisplay: "€480k/unit (at 3+)", efficiency: "98.5% CH₄ recovery", scaleThreshold: "3+ units, biogas hub model", leadTimeMonths: 8, trl: 9 },
  },

  /* ═══════════════════════════ WATER GAS SHIFT REACTOR ═══════════════════════════ */
  {
    keywords: ["water gas shift"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Clariant", model: "ShiftMax® 820 HTS Reactor", country: "Switzerland", priceEur: 1200000, priceDisplay: "€1.2M", efficiency: "CO conversion 95%, Fe/Cr catalyst", leadTimeMonths: 12, trl: 9 },
    bestEfficiency: { manufacturer: "Topsoe", model: "SSK Sour Shift Reactor", country: "Denmark", priceEur: 2800000, priceDisplay: "€2.8M", efficiency: "CO conversion 99%, CoMo catalyst", leadTimeMonths: 16, trl: 9 },
    economiesOfScale: { manufacturer: "Johnson Matthey", model: "KATALCO™ 71-5 LTS Reactor", country: "UK", priceEur: 1800000, priceDisplay: "€1.8M/reactor (at 2+)", efficiency: "CO conversion 97%", scaleThreshold: "2+ reactors, HTS+LTS train", leadTimeMonths: 14, trl: 9 },
  },

  /* ═══════════════════════════ REVERSE WATER GAS SHIFT REACTOR ═══════════════════════════ */
  {
    keywords: ["reverse water gas shift", "rwgs"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "INERATEC", model: "Compact RWGS Module 50 kg/h CO", country: "Germany", priceEur: 1500000, priceDisplay: "€1.5M", efficiency: "CO₂ conversion 60%, 800°C", leadTimeMonths: 14, trl: 7 },
    bestEfficiency: { manufacturer: "Topsoe", model: "eREACT™ RWGS Electrically Heated", country: "Denmark", priceEur: 3500000, priceDisplay: "€3.5M", efficiency: "CO₂ conversion 75%, 95% selectivity", leadTimeMonths: 20, trl: 7 },
    economiesOfScale: { manufacturer: "Sunfire", model: "RWGS Module 500 Nm³/h CO", country: "Germany", priceEur: 2400000, priceDisplay: "€2.4M/module (at 4+)", efficiency: "CO₂ conversion 65%", scaleThreshold: "4+ modules, integrated with SOEC", leadTimeMonths: 18, trl: 7 },
  },

  /* ═══════════════════════════ METHANATION REACTOR ═══════════════════════════ */
  {
    keywords: ["methanation reactor"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Hitachi Zosen Inova", model: "Biologische Methanation CSTR", country: "Switzerland", priceEur: 1800000, priceDisplay: "€1.8M", efficiency: "98% CH₄ selectivity, 60°C biological", leadTimeMonths: 12, trl: 8 },
    bestEfficiency: { manufacturer: "Topsoe", model: "TREMP™ Catalytic Methanation", country: "Denmark", priceEur: 3500000, priceDisplay: "€3.5M", efficiency: "99.5% CH₄, 3-stage adiabatic", leadTimeMonths: 18, trl: 9 },
    economiesOfScale: { manufacturer: "Electrochaea", model: "BioCat Power-to-Gas Reactor", country: "Denmark", priceEur: 2500000, priceDisplay: "€2.5M/unit (at 3+)", efficiency: "98% CH₄, archaea-based", scaleThreshold: "3+ units, modular scale-out", leadTimeMonths: 14, trl: 7 },
  },

  /* ═══════════════════════════ FISCHER-TROPSCH REACTOR ═══════════════════════════ */
  {
    keywords: ["fischer tropsch", "ft reactor"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "INERATEC", model: "Compact FT Microreactor 50 bbl/d", country: "Germany", priceEur: 5500000, priceDisplay: "€5.5M", efficiency: "CO conversion 85%, cobalt cat.", leadTimeMonths: 16, trl: 7 },
    bestEfficiency: { manufacturer: "Shell (Catalyst & Technologies)", model: "SMDS FT Slurry Reactor", country: "Netherlands", priceEur: 25000000, priceDisplay: "€25M", efficiency: "CO conversion 95%, 1000+ bbl/d", leadTimeMonths: 30, trl: 9 },
    economiesOfScale: { manufacturer: "Velocys", model: "Modular FT Microchannel Reactor", country: "UK", priceEur: 8500000, priceDisplay: "€8.5M/unit (at 4+)", efficiency: "CO conversion 90%", scaleThreshold: "4+ units, numbering-up strategy", leadTimeMonths: 20, trl: 7 },
  },

  /* ═══════════════════════════ METHANOL SYNTHESIS REACTOR ═══════════════════════════ */
  {
    keywords: ["methanol synthesis"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Johnson Matthey", model: "DAVY™ MeOH Converter 300 tpd", country: "UK", priceEur: 3500000, priceDisplay: "€3.5M", efficiency: "Per-pass 40%, Cu/Zn/Al catalyst", leadTimeMonths: 16, trl: 9 },
    bestEfficiency: { manufacturer: "Topsoe", model: "SynCOR Methanol™ ATR-based", country: "Denmark", priceEur: 6500000, priceDisplay: "€6.5M", efficiency: "Per-pass 64%, isothermal reactor", leadTimeMonths: 22, trl: 9 },
    economiesOfScale: { manufacturer: "Lurgi (Air Liquide)", model: "MegaMethanol™ 5000 tpd", country: "Germany", priceEur: 12000000, priceDisplay: "€12M/reactor (world-scale)", efficiency: "Per-pass 50%, 2-reactor loop", scaleThreshold: "5000+ tpd, world-scale reference", leadTimeMonths: 26, trl: 9 },
  },

  /* ═══════════════════════════ DME SYNTHESIS REACTOR ═══════════════════════════ */
  {
    keywords: ["dme synthesis", "dimethyl ether"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Haldor Topsoe", model: "TIGAS™ DME from Syngas", country: "Denmark", priceEur: 2800000, priceDisplay: "€2.8M", efficiency: "70% DME selectivity, zeolite cat.", leadTimeMonths: 16, trl: 8 },
    bestEfficiency: { manufacturer: "Air Liquide Engineering", model: "Direct DME Synthesis Reactor", country: "France", priceEur: 5200000, priceDisplay: "€5.2M", efficiency: "85% DME selectivity, bifunctional catalyst", leadTimeMonths: 20, trl: 7 },
    economiesOfScale: { manufacturer: "Lurgi (Air Liquide)", model: "MeOH-to-DME Dehydration 500 tpd", country: "Germany", priceEur: 3800000, priceDisplay: "€3.8M/reactor (at 2+)", efficiency: "80% DME yield", scaleThreshold: "2+ reactors, shared MeOH feed", leadTimeMonths: 18, trl: 9 },
  },

  /* ═══════════════════════════ AMMONIA SYNTHESIS REACTOR ═══════════════════════════ */
  {
    keywords: ["ammonia synthesis"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "KBR", model: "KAAP™ Ammonia Converter", country: "USA", priceEur: 4500000, priceDisplay: "€4.5M", efficiency: "Per-pass 22%, Ru catalyst, low P", leadTimeMonths: 18, trl: 9 },
    bestEfficiency: { manufacturer: "Topsoe", model: "S-300 Radial-Flow Converter", country: "Denmark", priceEur: 8500000, priceDisplay: "€8.5M", efficiency: "Per-pass 28%, 3-bed inter-cooled", leadTimeMonths: 24, trl: 9 },
    economiesOfScale: { manufacturer: "thyssenkrupp Uhde", model: "Dual-Pressure Synthesis Loop 3000 tpd", country: "Germany", priceEur: 15000000, priceDisplay: "€15M/loop (world-scale)", efficiency: "Per-pass 25%", scaleThreshold: "3000+ tpd, single-train reference", leadTimeMonths: 28, trl: 9 },
  },

  /* ═══════════════════════════ HYDROTREATER ═══════════════════════════ */
  {
    keywords: ["hydrotreater", "hydrotreating"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Axens (IFP)", model: "Prime-D Hydrotreating Reactor", country: "France", priceEur: 3200000, priceDisplay: "€3.2M", efficiency: "S < 10 ppm, CoMo catalyst", leadTimeMonths: 16, trl: 9 },
    bestEfficiency: { manufacturer: "Topsoe", model: "HDS/HDN Deep Hydrotreater", country: "Denmark", priceEur: 6500000, priceDisplay: "€6.5M", efficiency: "S < 1 ppm, N < 0.5 ppm", leadTimeMonths: 22, trl: 9 },
    economiesOfScale: { manufacturer: "Shell Catalysts & Technologies", model: "ATOMAX™ Hydrotreater", country: "Netherlands", priceEur: 4800000, priceDisplay: "€4.8M/reactor (at 2+)", efficiency: "S < 5 ppm, high space velocity", scaleThreshold: "2+ reactors, shared H₂ recycle", leadTimeMonths: 18, trl: 9 },
  },

  /* ═══════════════════════════ HYDROCRACKER ═══════════════════════════ */
  {
    keywords: ["hydrocracker"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Chevron Lummus Global", model: "ISOCRACKING™ Reactor", country: "USA", priceEur: 8500000, priceDisplay: "€8.5M", efficiency: "95% conversion, amorphous catalyst", leadTimeMonths: 22, trl: 9 },
    bestEfficiency: { manufacturer: "UOP (Honeywell)", model: "Unicracking™ HC Reactor", country: "USA", priceEur: 15000000, priceDisplay: "€15M", efficiency: "99% conversion, zeolite catalyst", leadTimeMonths: 28, trl: 9 },
    economiesOfScale: { manufacturer: "Axens", model: "HyK Hydrocracker 2-Stage", country: "France", priceEur: 12000000, priceDisplay: "€12M/train (at 2+)", efficiency: "97% conversion", scaleThreshold: "2+ trains, shared fractionation", leadTimeMonths: 26, trl: 9 },
  },

  /* ═══════════════════════════ HYDROISOMERIZATION REACTOR ═══════════════════════════ */
  {
    keywords: ["hydroisomerization"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "UOP (Honeywell)", model: "Penex™ Isomerization Reactor", country: "USA", priceEur: 3500000, priceDisplay: "€3.5M", efficiency: "RON 83, Pt/zeolite catalyst", leadTimeMonths: 16, trl: 9 },
    bestEfficiency: { manufacturer: "Axens", model: "ATIS-2L Isomerization", country: "France", priceEur: 5800000, priceDisplay: "€5.8M", efficiency: "RON 88, DIH recycle", leadTimeMonths: 20, trl: 9 },
    economiesOfScale: { manufacturer: "Topsoe", model: "TK-941 HydroFlex™ Iso Reactor", country: "Denmark", priceEur: 4500000, priceDisplay: "€4.5M/reactor (at 2+)", efficiency: "Pour point < -30°C", scaleThreshold: "2+ reactors, integrated dewaxing", leadTimeMonths: 18, trl: 9 },
  },

  /* ═══════════════════════════ ALKYLATION REACTOR ═══════════════════════════ */
  {
    keywords: ["alkylation reactor"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "DuPont (Stratco)", model: "Contactor™ HF Alkylation", country: "USA", priceEur: 6500000, priceDisplay: "€6.5M", efficiency: "RON 96, iC4/olefin ratio 12:1", leadTimeMonths: 20, trl: 9 },
    bestEfficiency: { manufacturer: "Albemarle (CBFS)", model: "AlkyClean™ Solid Acid Alkylation", country: "Netherlands", priceEur: 12000000, priceDisplay: "€12M", efficiency: "RON 97, no HF/H₂SO₄", leadTimeMonths: 26, trl: 8 },
    economiesOfScale: { manufacturer: "UOP (Honeywell)", model: "Alkylene™ Ionic Liquid Alkylation", country: "USA", priceEur: 9000000, priceDisplay: "€9M/unit (at 2+)", efficiency: "RON 96.5, ionic liquid catalyst", scaleThreshold: "2+ units, shared acid regen", leadTimeMonths: 22, trl: 8 },
  },

  /* ═══════════════════════════ POLYMERIZATION REACTOR ═══════════════════════════ */
  {
    keywords: ["polymerization reactor"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "LyondellBasell", model: "Spheripol™ PP Reactor", country: "Netherlands", priceEur: 8500000, priceDisplay: "€8.5M", efficiency: "400+ kt/yr, loop reactor", leadTimeMonths: 22, trl: 9 },
    bestEfficiency: { manufacturer: "Borealis (INEOS)", model: "Borstar® PE 3G Reactor", country: "Austria", priceEur: 15000000, priceDisplay: "€15M", efficiency: "Bimodal PE, multi-zone circ. reactor", leadTimeMonths: 28, trl: 9 },
    economiesOfScale: { manufacturer: "INEOS Technologies", model: "Innovene™ Gas-Phase PE Reactor", country: "UK", priceEur: 12000000, priceDisplay: "€12M/train (at 2+)", efficiency: "500+ kt/yr, single reactor", scaleThreshold: "2+ trains, shared pelletization", leadTimeMonths: 26, trl: 9 },
  },

  /* ═══════════════════════════ ABSORBER COLUMN ═══════════════════════════ */
  {
    keywords: ["absorber column", "absorber"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Koch-Glitsch", model: "Random Packing Absorber DN2000", country: "USA", priceEur: 380000, priceDisplay: "€380k", efficiency: "95% CO₂ absorption, random pack", leadTimeMonths: 10, trl: 9 },
    bestEfficiency: { manufacturer: "Sulzer Chemtech", model: "Structured Packing Absorber MellapakPlus", country: "Switzerland", priceEur: 750000, priceDisplay: "€750k", efficiency: "99% absorption, low pressure drop", leadTimeMonths: 14, trl: 9 },
    economiesOfScale: { manufacturer: "HAT International", model: "Modular Absorber Column", country: "Germany", priceEur: 520000, priceDisplay: "€520k/column (at 2+)", efficiency: "97% absorption", scaleThreshold: "2+ columns, shared solvent loop", leadTimeMonths: 12, trl: 9 },
  },

  /* ═══════════════════════════ STRIPPER COLUMN ═══════════════════════════ */
  {
    keywords: ["stripper column", "stripper"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Koch-Glitsch", model: "FLEXITRAY® Stripper DN1500", country: "USA", priceEur: 320000, priceDisplay: "€320k", efficiency: "99% stripping, valve trays", leadTimeMonths: 10, trl: 9 },
    bestEfficiency: { manufacturer: "Sulzer Chemtech", model: "Advanced Reboiled Stripper Column", country: "Switzerland", priceEur: 680000, priceDisplay: "€680k", efficiency: "99.9% stripping, structured pack", leadTimeMonths: 14, trl: 9 },
    economiesOfScale: { manufacturer: "HAT International", model: "Modular Stripper Column", country: "Germany", priceEur: 450000, priceDisplay: "€450k/column (at 2+)", efficiency: "99.5% stripping", scaleThreshold: "2+ columns, shared reboiler", leadTimeMonths: 12, trl: 9 },
  },

  /* ═══════════════════════════ AMMONIA STORAGE TANK ═══════════════════════════ */
  {
    keywords: ["ammonia storage tank"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "CB&I (McDermott)", model: "Refrigerated NH₃ Tank 30,000 t", country: "USA", priceEur: 8500000, priceDisplay: "€8.5M", efficiency: "-33°C atmospheric, single wall", leadTimeMonths: 18, trl: 9 },
    bestEfficiency: { manufacturer: "TechnipFMC", model: "Full-Containment NH₃ Tank 50,000 t", country: "France", priceEur: 18000000, priceDisplay: "€18M", efficiency: "-33°C, double containment", leadTimeMonths: 24, trl: 9 },
    economiesOfScale: { manufacturer: "Linde Engineering", model: "Modular NH₃ Storage Terminal", country: "Germany", priceEur: 12000000, priceDisplay: "€12M/tank (at 2+)", efficiency: "-33°C, shared refrigeration", scaleThreshold: "2+ tanks, terminal configuration", leadTimeMonths: 22, trl: 9 },
  },

  /* ═══════════════════════════ HYDROGEN STORAGE TANK ═══════════════════════════ */
  {
    keywords: ["hydrogen storage tank", "h2 storage"],
    pricingUnit: "€ per unit",
    plantScaleQty: 8,
    bestPrice: { manufacturer: "Hexagon Purus", model: "X-STORE 500 bar Type IV", country: "Norway", priceEur: 220000, priceDisplay: "€220k", efficiency: "500 bar, 8 kg H₂/vessel, composite", leadTimeMonths: 6, trl: 9 },
    bestEfficiency: { manufacturer: "Chart Industries", model: "Cryogenic LH₂ Tank 100 m³", country: "USA", priceEur: 850000, priceDisplay: "€850k", efficiency: "Boil-off <0.2%/day, vacuum insulated", leadTimeMonths: 14, trl: 9 },
    economiesOfScale: { manufacturer: "NPROXX", model: "Type IV 700-bar Rack System", country: "Germany", priceEur: 350000, priceDisplay: "€350k/rack (at 10+)", efficiency: "700 bar, 40 kg/rack", scaleThreshold: "10+ racks, automated refueling", leadTimeMonths: 8, trl: 9 },
  },

  /* ═══════════════════════════ CO2 STORAGE TANK ═══════════════════════════ */
  {
    keywords: ["co2 storage tank"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Chart Industries", model: "Horizontal CO₂ Bullet 100 t", country: "USA", priceEur: 280000, priceDisplay: "€280k", efficiency: "-20°C / 20 bar, low-pressure", leadTimeMonths: 8, trl: 9 },
    bestEfficiency: { manufacturer: "Linde Engineering", model: "Vacuum-Insulated CO₂ Sphere 500 t", country: "Germany", priceEur: 1200000, priceDisplay: "€1.2M", efficiency: "-50°C / 7 bar, low boil-off", leadTimeMonths: 14, trl: 9 },
    economiesOfScale: { manufacturer: "MAN Energy Solutions (Turbo)", model: "CO₂ Terminal Storage 2000 t", country: "Germany", priceEur: 750000, priceDisplay: "€750k/tank (at 4+)", efficiency: "-30°C / 15 bar", scaleThreshold: "4+ tanks, shared liquefaction", leadTimeMonths: 12, trl: 9 },
  },

  /* ═══════════════════════════ NATURAL GAS / CNG / LPG STORAGE TANKS ═══════════════════════════ */
  {
    keywords: ["natural gas storage tank", "cng storage", "lpg storage"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Worthington Industries", model: "CNG Type I Steel Cylinder", country: "USA", priceEur: 12000, priceDisplay: "€12k", efficiency: "200 bar, 80 L water capacity", leadTimeMonths: 3, trl: 9 },
    bestEfficiency: { manufacturer: "Hexagon Composites", model: "X-STORE CNG Type IV Module", country: "Norway", priceEur: 65000, priceDisplay: "€65k", efficiency: "250 bar, 450 L, 70% lighter", leadTimeMonths: 6, trl: 9 },
    economiesOfScale: { manufacturer: "Faber Industrie", model: "CNG Cascade Storage Bank", country: "Italy", priceEur: 35000, priceDisplay: "€35k/bank (at 6+)", efficiency: "250 bar, sequential filling", scaleThreshold: "6+ banks, refueling station", leadTimeMonths: 5, trl: 9 },
  },

  /* ═══════════════════════════ HYDROCARBON / METHANOL / ETHANOL STORAGE TANK ═══════════════════════════ */
  {
    keywords: ["hydrocarbon storage", "methanol storage", "ethanol storage"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Äager (Ergil)", model: "API 650 Floating Roof Tank 5000 m³", country: "Turkey", priceEur: 450000, priceDisplay: "€450k", efficiency: "Atmospheric, EFR, low emissions", leadTimeMonths: 10, trl: 9 },
    bestEfficiency: { manufacturer: "CB&I (McDermott)", model: "Internal Floating Roof Tank 10,000 m³", country: "USA", priceEur: 1200000, priceDisplay: "€1.2M", efficiency: "Atmospheric, IFRT, ultra-low VOC", leadTimeMonths: 14, trl: 9 },
    economiesOfScale: { manufacturer: "Teysha (Toyo Kanetsu)", model: "Fixed Cone Roof Tank Farm", country: "Japan", priceEur: 750000, priceDisplay: "€750k/tank (at 4+)", efficiency: "API 650, shared dyke", scaleThreshold: "4+ tanks, terminal pricing", leadTimeMonths: 12, trl: 9 },
  },

  /* ═══════════════════════════ BUFFER TANK ═══════════════════════════ */
  {
    keywords: ["buffer tank"],
    pricingUnit: "€ per unit",
    plantScaleQty: 4,
    bestPrice: { manufacturer: "Stamag (Stallkamp)", model: "SS304 Buffer Vessel 50 m³", country: "Germany", priceEur: 28000, priceDisplay: "€28k", efficiency: "Atmospheric, agitated", leadTimeMonths: 4, trl: 9 },
    bestEfficiency: { manufacturer: "Pierre Guérin", model: "Jacketed Buffer Tank 100 m³ 316L", country: "France", priceEur: 85000, priceDisplay: "€85k", efficiency: "Heated/cooled jacket, CIP ready", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "Paul Mueller Company", model: "Templock® Buffer Tank Modular", country: "USA", priceEur: 55000, priceDisplay: "€55k/tank (at 4+)", efficiency: "ASME-stamped, temp controlled", scaleThreshold: "4+ tanks, shared process loop", leadTimeMonths: 6, trl: 9 },
  },

  /* ═══════════════════════════ HYDROGEN TUBE TRAILER LOADING UNIT ═══════════════════════════ */
  {
    keywords: ["tube trailer loading", "h2 trailer"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Wystrach", model: "H₂ Tube Trailer Loading Bay", country: "Germany", priceEur: 180000, priceDisplay: "€180k", efficiency: "500 bar, 1000 kg/trailer", leadTimeMonths: 8, trl: 9 },
    bestEfficiency: { manufacturer: "Hexagon Purus", model: "X-STORE Mobile Pipeline Loading", country: "Norway", priceEur: 350000, priceDisplay: "€350k", efficiency: "500 bar, 1200 kg Type IV composite", leadTimeMonths: 12, trl: 9 },
    economiesOfScale: { manufacturer: "NPROXX", model: "Automated H₂ Loading Gantry", country: "Germany", priceEur: 250000, priceDisplay: "€250k/bay (at 3+)", efficiency: "Automated connect/disconnect", scaleThreshold: "3+ bays, continuous dispatch", leadTimeMonths: 10, trl: 9 },
  },

  /* ═══════════════════════════ TANK TRUCK LOADING UNIT ═══════════════════════════ */
  {
    keywords: ["tank truck loading"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Emco Wheaton", model: "Marine Loading Arm, Road Tanker", country: "USA", priceEur: 65000, priceDisplay: "€65k", efficiency: "500 m³/h, bottom loading, vapor recovery", leadTimeMonths: 5, trl: 9 },
    bestEfficiency: { manufacturer: "Kanon Loading Equipment", model: "Bottom Loading Arm + VRU", country: "Netherlands", priceEur: 120000, priceDisplay: "€120k", efficiency: "1000 m³/h, ATEX Zone 0", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "SafeRack", model: "Multi-Spot Loading Gantry", country: "USA", priceEur: 85000, priceDisplay: "€85k/spot (at 4+)", efficiency: "4+ spots, shared VRU", scaleThreshold: "4+ spots, terminal throughput", leadTimeMonths: 6, trl: 9 },
  },

  /* ═══════════════════════════ RAIL LOADING UNIT ═══════════════════════════ */
  {
    keywords: ["rail loading"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Kanon Loading Equipment", model: "Top Rail Loading Arm", country: "Netherlands", priceEur: 95000, priceDisplay: "€95k", efficiency: "800 m³/h, for rail tank cars", leadTimeMonths: 6, trl: 9 },
    bestEfficiency: { manufacturer: "Emco Wheaton", model: "Articulated Rail Loading + Metering", country: "USA", priceEur: 180000, priceDisplay: "€180k", efficiency: "Custody-transfer metering, OIML R117", leadTimeMonths: 10, trl: 9 },
    economiesOfScale: { manufacturer: "Woodfield Systems", model: "Multi-Spot Rail Gantry", country: "UK", priceEur: 130000, priceDisplay: "€130k/spot (at 3+)", efficiency: "3+ spots, sequential loading", scaleThreshold: "3+ spots, shared pumps & VRU", leadTimeMonths: 8, trl: 9 },
  },

  /* ═══════════════════════════ SHIP LOADING UNIT ═══════════════════════════ */
  {
    keywords: ["ship loading", "marine loading"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Emco Wheaton", model: "Marine Loading Arm MLA", country: "USA", priceEur: 280000, priceDisplay: "€280k", efficiency: "2000 m³/h, 16\", QCDC", leadTimeMonths: 10, trl: 9 },
    bestEfficiency: { manufacturer: "SVT (Woodfield)", model: "Marine Loading Arm + ERS", country: "UK", priceEur: 520000, priceDisplay: "€520k", efficiency: "3500 m³/h, emergency release system", leadTimeMonths: 14, trl: 9 },
    economiesOfScale: { manufacturer: "Kanon Loading Equipment", model: "Multi-Product Marine Terminal Arms", country: "Netherlands", priceEur: 380000, priceDisplay: "€380k/arm (at 4+)", efficiency: "Multi-product, shared ESD system", scaleThreshold: "4+ arms, terminal package", leadTimeMonths: 12, trl: 9 },
  },

  /* ═══════════════════════════ CO2 LIQUEFACTION UNIT ═══════════════════════════ */
  {
    keywords: ["co2 liquefaction"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Wärtsilä (Hamworthy)", model: "CO₂ Liquefaction Skid 100 tpd", country: "Norway", priceEur: 1800000, priceDisplay: "€1.8M", efficiency: "-30°C / 15 bar, ship-ready", leadTimeMonths: 12, trl: 9 },
    bestEfficiency: { manufacturer: "Linde Engineering", model: "CO₂ Purification & Liquefaction Train", country: "Germany", priceEur: 4200000, priceDisplay: "€4.2M", efficiency: "99.99% CO₂, food-grade, -50°C", leadTimeMonths: 18, trl: 9 },
    economiesOfScale: { manufacturer: "MAN Energy Solutions", model: "CO₂ Hub Liquefaction Terminal", country: "Germany", priceEur: 2800000, priceDisplay: "€2.8M/train (at 3+)", efficiency: "-30°C / 15 bar, 500 tpd/train", scaleThreshold: "3+ trains, shared storage & export", leadTimeMonths: 16, trl: 9 },
  },

  /* ═══════════════════════════ HYDROGEN LIQUEFACTION UNIT ═══════════════════════════ */
  {
    keywords: ["hydrogen liquefaction"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Chart Industries", model: "IPSMR® LH₂ Module 5 tpd", country: "USA", priceEur: 8500000, priceDisplay: "€8.5M", efficiency: "10 kWh/kg LH₂, pre-cooling", leadTimeMonths: 18, trl: 8 },
    bestEfficiency: { manufacturer: "Linde Engineering", model: "Large-Scale LH₂ Liquefier 100 tpd", country: "Germany", priceEur: 28000000, priceDisplay: "€28M", efficiency: "6 kWh/kg LH₂, turbo-expander", leadTimeMonths: 28, trl: 9 },
    economiesOfScale: { manufacturer: "Air Liquide", model: "EcoLH₂ Liquefaction 50 tpd", country: "France", priceEur: 18000000, priceDisplay: "€18M/train (at 2+)", efficiency: "7 kWh/kg LH₂", scaleThreshold: "2+ trains, shared cryogenic infrastructure", leadTimeMonths: 24, trl: 9 },
  },

  /* ═══════════════════════════ NATURAL GAS LIQUEFACTION ═══════════════════════════ */
  {
    keywords: ["natural gas liquefaction", "lng plant"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Chart Industries", model: "IPSMR® Micro-LNG 100 tpd", country: "USA", priceEur: 12000000, priceDisplay: "€12M", efficiency: "0.35 kWh/kg LNG, single mixed ref.", leadTimeMonths: 16, trl: 9 },
    bestEfficiency: { manufacturer: "Air Products", model: "AP-C3MR™ LNG Process", country: "USA", priceEur: 120000000, priceDisplay: "€120M", efficiency: "0.28 kWh/kg LNG, mega-train 5 Mtpa", leadTimeMonths: 42, trl: 9 },
    economiesOfScale: { manufacturer: "Linde Engineering", model: "LIMUM® Modular LNG 500 tpd", country: "Germany", priceEur: 35000000, priceDisplay: "€35M/train (at 2+)", efficiency: "0.30 kWh/kg LNG", scaleThreshold: "2+ trains, shared storage & export", leadTimeMonths: 30, trl: 9 },
  },

  /* ═══════════════════════════ CATALYTIC OXIDIZER ═══════════════════════════ */
  {
    keywords: ["catalytic oxidizer"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "MEGTEC (Babcock & Wilcox)", model: "CleanSwitch™ RCO", country: "USA", priceEur: 220000, priceDisplay: "€220k", efficiency: "99% VOC DRE, catalytic, 95% heat recovery", leadTimeMonths: 8, trl: 9 },
    bestEfficiency: { manufacturer: "Anguil Environmental", model: "Catalytic Oxidizer with HEX", country: "USA", priceEur: 420000, priceDisplay: "€420k", efficiency: "99.9% DRE, Pt/Pd catalyst", leadTimeMonths: 10, trl: 9 },
    economiesOfScale: { manufacturer: "Dürr (Clean Technology Systems)", model: "Ecopure® CTO Modular", country: "Germany", priceEur: 320000, priceDisplay: "€320k/unit (at 2+)", efficiency: "99.5% DRE", scaleThreshold: "2+ units, shared ductwork", leadTimeMonths: 8, trl: 9 },
  },

  /* ═══════════════════════════ VENT STACK ═══════════════════════════ */
  {
    keywords: ["vent stack"],
    pricingUnit: "€ per unit",
    plantScaleQty: 3,
    bestPrice: { manufacturer: "Zeeco", model: "Self-Supporting Vent Stack 30 m", country: "USA", priceEur: 85000, priceDisplay: "€85k", efficiency: "Atmospheric, wind-load designed", leadTimeMonths: 5, trl: 9 },
    bestEfficiency: { manufacturer: "NAO Inc.", model: "Guy-Wired Vent Stack 60 m, H₂ service", country: "USA", priceEur: 180000, priceDisplay: "€180k", efficiency: "H₂ dispersion modeling optimized", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "John Zink Hamworthy", model: "Multi-Service Vent Stack", country: "USA", priceEur: 120000, priceDisplay: "€120k/stack (at 3+)", efficiency: "Combined H₂/N₂/process vent", scaleThreshold: "3+ stacks, shared dispersion study", leadTimeMonths: 6, trl: 9 },
  },

  /* ═══════════════════════════ BLOWDOWN SYSTEM ═══════════════════════════ */
  {
    keywords: ["blowdown system", "pressure relief system"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Zeeco", model: "Atmospheric Blowdown Drum", country: "USA", priceEur: 180000, priceDisplay: "€180k", efficiency: "API 521, atmospheric depressuring", leadTimeMonths: 6, trl: 9 },
    bestEfficiency: { manufacturer: "John Zink Hamworthy", model: "Closed Blowdown System + KO Drum", country: "USA", priceEur: 450000, priceDisplay: "€450k", efficiency: "Zero emissions, closed loop flare", leadTimeMonths: 10, trl: 9 },
    economiesOfScale: { manufacturer: "NAO Inc.", model: "Modular Blowdown System", country: "USA", priceEur: 280000, priceDisplay: "€280k/system (at 2+)", efficiency: "API 521, shared flare", scaleThreshold: "2+ systems, shared relief header", leadTimeMonths: 8, trl: 9 },
  },

  /* ═══════════════════════════ INERTING SYSTEM / NITROGEN BLANKETING ═══════════════════════════ */
  {
    keywords: ["inerting system", "nitrogen blanketing"],
    pricingUnit: "€ per unit",
    plantScaleQty: 3,
    bestPrice: { manufacturer: "Parker Hannifin", model: "N₂ Blanketing Panel + Breather Valve", country: "USA", priceEur: 15000, priceDisplay: "€15k", efficiency: "Set-pressure ±5 mbar, ATEX", leadTimeMonths: 3, trl: 9 },
    bestEfficiency: { manufacturer: "Pepperl+Fuchs (Bebco)", model: "EPS Purge + Pressurize System", country: "Germany", priceEur: 35000, priceDisplay: "€35k", efficiency: "Type X/Y/Z purge, SIL 2", leadTimeMonths: 6, trl: 9 },
    economiesOfScale: { manufacturer: "Rotarex", model: "Automated N₂ Blanketing Manifold", country: "Luxembourg", priceEur: 22000, priceDisplay: "€22k/unit (at 8+)", efficiency: "Centralized N₂ supply", scaleThreshold: "8+ vessels, shared N₂ generator", leadTimeMonths: 4, trl: 9 },
  },

  /* ═══════════════════════════ GAS DETECTION SYSTEM ═══════════════════════════ */
  {
    keywords: ["gas detection system", "gas detector"],
    pricingUnit: "€ per unit",
    plantScaleQty: 30,
    bestPrice: { manufacturer: "Dräger", model: "Polytron 8100 EC Point Detector", country: "Germany", priceEur: 1800, priceDisplay: "€1,800", efficiency: "H₂/CO/H₂S, electrochemical, SIL 2", leadTimeMonths: 3, trl: 9 },
    bestEfficiency: { manufacturer: "Honeywell Analytics", model: "Searchzone Sonik Open-Path Ultrasonic", country: "USA", priceEur: 12000, priceDisplay: "€12k", efficiency: "Ultrasonic leak detection, 25 m range", leadTimeMonths: 6, trl: 9 },
    economiesOfScale: { manufacturer: "MSA Safety", model: "ULTIMA X5000 Multi-Gas + IoT Gateway", country: "USA", priceEur: 4500, priceDisplay: "€4,500/unit (at 20+)", efficiency: "5-gas, HART + wireless", scaleThreshold: "20+ units, plant-wide IoT mesh", leadTimeMonths: 4, trl: 9 },
  },

  /* ═══════════════════════════ FIRE SUPPRESSION SYSTEM ═══════════════════════════ */
  {
    keywords: ["fire suppression"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Tyco (Johnson Controls)", model: "Deluge Valve System DV-5", country: "USA", priceEur: 95000, priceDisplay: "€95k", efficiency: "Water deluge, 500 L/min/m²", leadTimeMonths: 5, trl: 9 },
    bestEfficiency: { manufacturer: "Viking Group", model: "Hi-Fog® Water Mist System", country: "Finland", priceEur: 280000, priceDisplay: "€280k", efficiency: "90% less water vs deluge, Class A/B/C", leadTimeMonths: 10, trl: 9 },
    economiesOfScale: { manufacturer: "Novec (3M / Chemours)", model: "Novec 1230 Clean Agent System", country: "USA", priceEur: 180000, priceDisplay: "€180k/zone (at 4+)", efficiency: "Clean agent, zero water damage", scaleThreshold: "4+ zones, shared cylinder bank", leadTimeMonths: 6, trl: 9 },
  },

  /* ═══════════════════════════ BIOMASS RECEIVING STATION ═══════════════════════════ */
  {
    keywords: ["biomass receiving"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "Bruks Siwertell", model: "Truck Receiving Hopper + Conveyor", country: "Sweden", priceEur: 350000, priceDisplay: "€350k", efficiency: "200 t/h, truck tipping + belt", leadTimeMonths: 8, trl: 9 },
    bestEfficiency: { manufacturer: "Vecoplan", model: "Automated Biomass Receiving & Screening", country: "Germany", priceEur: 750000, priceDisplay: "€750k", efficiency: "500 t/h, screening + metal detection", leadTimeMonths: 12, trl: 9 },
    economiesOfScale: { manufacturer: "ANDRITZ", model: "BioFeed Receiving Terminal", country: "Austria", priceEur: 520000, priceDisplay: "€520k/line (at 2+)", efficiency: "300 t/h, rail + truck", scaleThreshold: "2+ lines, shared storage", leadTimeMonths: 10, trl: 9 },
  },

  /* ═══════════════════════════ BIOMASS STORAGE SILO ═══════════════════════════ */
  {
    keywords: ["biomass storage silo", "biomass silo"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Laidig Systems", model: "Reclaim Silo 2000 m³", country: "USA", priceEur: 280000, priceDisplay: "€280k", efficiency: "Bottom reclaim, FIFO, dust-free", leadTimeMonths: 8, trl: 9 },
    bestEfficiency: { manufacturer: "Dome Technology", model: "Concrete Dome Silo 5000 m³", country: "USA", priceEur: 650000, priceDisplay: "€650k", efficiency: "Weather-tight, O₂ monitoring, fire suppression", leadTimeMonths: 12, trl: 9 },
    economiesOfScale: { manufacturer: "Saxlund International", model: "Steel Silo + Walking Floor", country: "UK", priceEur: 420000, priceDisplay: "€420k/silo (at 3+)", efficiency: "3000 m³, shared extraction", scaleThreshold: "3+ silos, multi-species storage", leadTimeMonths: 10, trl: 9 },
  },

  /* ═══════════════════════════ BIOMASS DRY STORAGE BUNKER ═══════════════════════════ */
  {
    keywords: ["dry storage bunker", "biomass bunker"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Keith Manufacturing", model: "Walking Floor Bunker 200 m³", country: "USA", priceEur: 120000, priceDisplay: "€120k", efficiency: "Walking floor discharge, 50 t/h", leadTimeMonths: 6, trl: 9 },
    bestEfficiency: { manufacturer: "BRUKS Siwertell", model: "Enclosed Bunker with Agitator 500 m³", country: "Sweden", priceEur: 280000, priceDisplay: "€280k", efficiency: "Anti-bridging, dust extraction", leadTimeMonths: 10, trl: 9 },
    economiesOfScale: { manufacturer: "Saxlund", model: "Push-Floor Bunker Modular", country: "UK", priceEur: 180000, priceDisplay: "€180k/bunker (at 3+)", efficiency: "300 m³, shared conveyor", scaleThreshold: "3+ bunkers, flexible feedstock", leadTimeMonths: 8, trl: 9 },
  },

  /* ═══════════════════════════ BIOMASS SLURRY TANK ═══════════════════════════ */
  {
    keywords: ["biomass slurry tank", "slurry tank"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Stallkamp", model: "Glass-Lined Slurry Tank 500 m³", country: "Germany", priceEur: 85000, priceDisplay: "€85k", efficiency: "Agitated, up to 15% DM", leadTimeMonths: 6, trl: 9 },
    bestEfficiency: { manufacturer: "Lipp (BAUER)", model: "Stainless Slurry Tank 1000 m³", country: "Germany", priceEur: 180000, priceDisplay: "€180k", efficiency: "SS316, heated, 20% DM", leadTimeMonths: 10, trl: 9 },
    economiesOfScale: { manufacturer: "EnviTec Biogas", model: "Modular Pre-Mixing Tank", country: "Germany", priceEur: 120000, priceDisplay: "€120k/tank (at 3+)", efficiency: "700 m³, shared feeding pump", scaleThreshold: "3+ tanks, multi-substrate blending", leadTimeMonths: 8, trl: 9 },
  },

  /* ═══════════════════════════ FEEDSTOCK BLENDING UNIT ═══════════════════════════ */
  {
    keywords: ["feedstock blending"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Ottevanger Milling Engineers", model: "Multi-Component Blender 20 tph", country: "Netherlands", priceEur: 120000, priceDisplay: "€120k", efficiency: "±2% blend accuracy, 6 hoppers", leadTimeMonths: 6, trl: 9 },
    bestEfficiency: { manufacturer: "BHS-Sonthofen", model: "DKX Twin-Shaft Continuous Mixer", country: "Germany", priceEur: 280000, priceDisplay: "€280k", efficiency: "±0.5% accuracy, residence time 30s", leadTimeMonths: 10, trl: 9 },
    economiesOfScale: { manufacturer: "Schenck Process", model: "FlexMix® Gravimetric Blender", country: "Germany", priceEur: 180000, priceDisplay: "€180k/unit (at 2+)", efficiency: "±1%, loss-in-weight feeding", scaleThreshold: "2+ units, shared recipe management", leadTimeMonths: 8, trl: 9 },
  },

  /* ═══════════════════════════ GAS MIXER ═══════════════════════════ */
  {
    keywords: ["gas mixer"],
    pricingUnit: "€ per unit",
    plantScaleQty: 3,
    bestPrice: { manufacturer: "Witt-Gasetechnik", model: "KM100-3 Static Gas Mixer", country: "Germany", priceEur: 8500, priceDisplay: "€8,500", efficiency: "±1%, 3-gas, up to 200 Nm³/h", leadTimeMonths: 3, trl: 9 },
    bestEfficiency: { manufacturer: "Bronkhorst", model: "FLEXI-BLEND Dynamic Gas Mixer", country: "Netherlands", priceEur: 28000, priceDisplay: "€28k", efficiency: "±0.2%, mass flow controlled", leadTimeMonths: 6, trl: 9 },
    economiesOfScale: { manufacturer: "Linde (BOC)", model: "MIXMASTER™ Inline Gas Blender", country: "Germany", priceEur: 18000, priceDisplay: "€18k/unit (at 4+)", efficiency: "±0.5%, pipeline-ready", scaleThreshold: "4+ units, centralized analysis", leadTimeMonths: 5, trl: 9 },
  },

  /* ═══════════════════════════ LIQUID MIXER ═══════════════════════════ */
  {
    keywords: ["liquid mixer"],
    pricingUnit: "€ per unit",
    plantScaleQty: 4,
    bestPrice: { manufacturer: "EKATO", model: "HWL Hydrofoil Impeller, 10 m³ vessel", country: "Germany", priceEur: 25000, priceDisplay: "€25k", efficiency: "0.3 kW/m³, low shear", leadTimeMonths: 4, trl: 9 },
    bestEfficiency: { manufacturer: "Philadelphia Mixing Solutions", model: "TurboJet™ High-Efficiency Mixer", country: "USA", priceEur: 65000, priceDisplay: "€65k", efficiency: "0.1 kW/m³, premium impeller design", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "Lightnin (SPX Flow)", model: "A320 Fluidfoil Agitator", country: "USA", priceEur: 38000, priceDisplay: "€38k/unit (at 6+)", efficiency: "0.2 kW/m³", scaleThreshold: "6+ units, fleet standardization", leadTimeMonths: 5, trl: 9 },
  },

  /* ═══════════════════════════ CONVEYING EQUIPMENT (SCREW, BELT, BUCKET) ═══════════════════════════ */
  {
    keywords: ["screw conveyor"],
    pricingUnit: "€ per unit",
    plantScaleQty: 6,
    bestPrice: { manufacturer: "WAM Group", model: "TXF Tubular Screw Conveyor", country: "Italy", priceEur: 12000, priceDisplay: "€12k", efficiency: "50 tph, dust-tight, 12 m length", leadTimeMonths: 3, trl: 9 },
    bestEfficiency: { manufacturer: "Coperion", model: "ZSK Twin-Screw Feeder", country: "Germany", priceEur: 45000, priceDisplay: "€45k", efficiency: "±0.5% volumetric, heated jacket", leadTimeMonths: 6, trl: 9 },
    economiesOfScale: { manufacturer: "Martin Sprocket & Gear", model: "Sectional Screw Conveyor", country: "USA", priceEur: 22000, priceDisplay: "€22k/unit (at 5+)", efficiency: "75 tph, modular sections", scaleThreshold: "5+ units, spare parts commonality", leadTimeMonths: 4, trl: 9 },
  },
  {
    keywords: ["belt conveyor"],
    pricingUnit: "€ per unit",
    plantScaleQty: 4,
    bestPrice: { manufacturer: "Continental (ContiTech)", model: "Steelcord Belt Conveyor 1200 mm", country: "Germany", priceEur: 85000, priceDisplay: "€85k", efficiency: "1500 tph, 200 m length", leadTimeMonths: 6, trl: 9 },
    bestEfficiency: { manufacturer: "Beumer Group", model: "Pipe Conveyor 800 mm", country: "Germany", priceEur: 220000, priceDisplay: "€220k", efficiency: "800 tph, enclosed, steep incline", leadTimeMonths: 10, trl: 9 },
    economiesOfScale: { manufacturer: "Metso Outotec", model: "Modular Overland Belt Conveyor", country: "Finland", priceEur: 150000, priceDisplay: "€150k/section (at 3+)", efficiency: "2000 tph, energy-efficient drives", scaleThreshold: "3+ sections, shared tensioning", leadTimeMonths: 8, trl: 9 },
  },
  {
    keywords: ["bucket elevator"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Zuther", model: "Chain Bucket Elevator ZBE 500", country: "Germany", priceEur: 45000, priceDisplay: "€45k", efficiency: "200 tph, 30 m lift, ATEX", leadTimeMonths: 5, trl: 9 },
    bestEfficiency: { manufacturer: "Beumer Group", model: "Belt Bucket Elevator BOB", country: "Germany", priceEur: 120000, priceDisplay: "€120k", efficiency: "500 tph, 60 m lift, centrifugal", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "Coperion (Torfwerk)", model: "Modular Elevator KWS", country: "USA", priceEur: 75000, priceDisplay: "€75k/unit (at 2+)", efficiency: "300 tph, 45 m lift", scaleThreshold: "2+ units, shared head frame", leadTimeMonths: 6, trl: 9 },
  },

  /* ═══════════════════════════ SIZE REDUCTION / SHREDDER / CHIP SCREEN ═══════════════════════════ */
  {
    keywords: ["size reduction mill", "hammer mill"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Andritz", model: "HM Multi-Purpose Hammer Mill", country: "Austria", priceEur: 120000, priceDisplay: "€120k", efficiency: "20 tph, particle < 10 mm", leadTimeMonths: 6, trl: 9 },
    bestEfficiency: { manufacturer: "Pallmann", model: "PSKM Knife Ring Flaker", country: "Germany", priceEur: 280000, priceDisplay: "€280k", efficiency: "30 tph, uniform flake < 5 mm", leadTimeMonths: 10, trl: 9 },
    economiesOfScale: { manufacturer: "Vecoplan", model: "VIZ Shredder + Screen Combo", country: "Germany", priceEur: 180000, priceDisplay: "€180k/line (at 2+)", efficiency: "40 tph, integrated screening", scaleThreshold: "2+ lines, shared feed conveyor", leadTimeMonths: 8, trl: 9 },
  },
  {
    keywords: ["shredder"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Vecoplan", model: "VIZ 2500 Single-Shaft Shredder", country: "Germany", priceEur: 150000, priceDisplay: "€150k", efficiency: "30 tph, output < 80 mm", leadTimeMonths: 6, trl: 9 },
    bestEfficiency: { manufacturer: "Lindner", model: "Polaris 2800 Dual-Shaft Shredder", country: "Austria", priceEur: 350000, priceDisplay: "€350k", efficiency: "50 tph, output < 50 mm, auto-reverse", leadTimeMonths: 10, trl: 9 },
    economiesOfScale: { manufacturer: "UNTHA", model: "RS150 4-Shaft Shredder", country: "Austria", priceEur: 220000, priceDisplay: "€220k/unit (at 2+)", efficiency: "40 tph, uniform output", scaleThreshold: "2+ units, shared metal separator", leadTimeMonths: 8, trl: 9 },
  },
  {
    keywords: ["chip screen", "biomass screen"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Bruks Siwertell", model: "Disc Screen BDS 40", country: "Sweden", priceEur: 65000, priceDisplay: "€65k", efficiency: "40 tph, 3 fractions", leadTimeMonths: 4, trl: 9 },
    bestEfficiency: { manufacturer: "Andritz", model: "Vibrating Screen VSD-05", country: "Austria", priceEur: 140000, priceDisplay: "€140k", efficiency: "80 tph, 5 fractions, self-cleaning", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "Metso Outotec", model: "Rotary Trommel Screen", country: "Finland", priceEur: 95000, priceDisplay: "€95k/unit (at 2+)", efficiency: "60 tph, 3 fractions", scaleThreshold: "2+ units, shared reject handling", leadTimeMonths: 6, trl: 9 },
  },

  /* ═══════════════════════════ MAGNETIC SEPARATOR ═══════════════════════════ */
  {
    keywords: ["magnetic separator"],
    pricingUnit: "€ per unit",
    plantScaleQty: 3,
    bestPrice: { manufacturer: "Eriez", model: "Suspended Electromagnet SE-5036", country: "USA", priceEur: 18000, priceDisplay: "€18k", efficiency: "Ferrous removal, overhead mount", leadTimeMonths: 3, trl: 9 },
    bestEfficiency: { manufacturer: "Steinert", model: "FINESSE Eddy Current + Magnet", country: "Germany", priceEur: 65000, priceDisplay: "€65k", efficiency: "Ferrous + non-ferrous, < 2 mm detection", leadTimeMonths: 6, trl: 9 },
    economiesOfScale: { manufacturer: "Bunting Magnetics", model: "Cross-Belt Separator FF Series", country: "UK", priceEur: 35000, priceDisplay: "€35k/unit (at 3+)", efficiency: "High-intensity rare earth magnet", scaleThreshold: "3+ units, multi-stream installation", leadTimeMonths: 4, trl: 9 },
  },

  /* ═══════════════════════════ SOLIDS DRYER ═══════════════════════════ */
  {
    keywords: ["solids dryer", "rotary dryer", "flash dryer"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Andritz", model: "Feed & Biofuel Drum Dryer FBD", country: "Austria", priceEur: 280000, priceDisplay: "€280k", efficiency: "10% → 90% DM, 20 tph, rotary", leadTimeMonths: 8, trl: 9 },
    bestEfficiency: { manufacturer: "GEA", model: "Barr-Rosin Superheated Steam Dryer", country: "Germany", priceEur: 650000, priceDisplay: "€650k", efficiency: "Energy recovery, zero emissions", leadTimeMonths: 14, trl: 9 },
    economiesOfScale: { manufacturer: "Swiss Combi", model: "Belt Dryer SCD-40", country: "Switzerland", priceEur: 420000, priceDisplay: "€420k/unit (at 2+)", efficiency: "Low-temp drying, waste heat usable", scaleThreshold: "2+ units, shared heat source", leadTimeMonths: 10, trl: 9 },
  },

  /* ═══════════════════════════ PELLETIZER ═══════════════════════════ */
  {
    keywords: ["pelletizer"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Andritz", model: "Feed & Biofuel Pellet Mill PM20", country: "Austria", priceEur: 180000, priceDisplay: "€180k", efficiency: "5 tph, 6-8 mm pellets", leadTimeMonths: 6, trl: 9 },
    bestEfficiency: { manufacturer: "CPM (Consolidated Process Machinery)", model: "Century Series 7000HD", country: "USA", priceEur: 380000, priceDisplay: "€380k", efficiency: "10 tph, ENplus A1 quality", leadTimeMonths: 10, trl: 9 },
    economiesOfScale: { manufacturer: "Bühler", model: "Pellet Mill RWPR 900", country: "Switzerland", priceEur: 250000, priceDisplay: "€250k/unit (at 3+)", efficiency: "8 tph, dual die", scaleThreshold: "3+ units, shared conditioning", leadTimeMonths: 8, trl: 9 },
  },

  /* ═══════════════════════════ BRIQUETTER ═══════════════════════════ */
  {
    keywords: ["briquetter"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "RUF Briquetting", model: "RUF 1500 Hydraulic Briquetter", country: "Germany", priceEur: 120000, priceDisplay: "€120k", efficiency: "1500 kg/h, 60 mm Ø briquettes", leadTimeMonths: 5, trl: 9 },
    bestEfficiency: { manufacturer: "Weima", model: "TH 714 Briquette Press", country: "Germany", priceEur: 220000, priceDisplay: "€220k", efficiency: "2500 kg/h, density > 1.1 kg/dm³", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "CF Nielsen", model: "BP 6500 Mechanical Briquetter", country: "Denmark", priceEur: 160000, priceDisplay: "€160k/unit (at 2+)", efficiency: "6500 kg/h, piston type", scaleThreshold: "2+ units, shared feedstock prep", leadTimeMonths: 6, trl: 9 },
  },

  /* ═══════════════════════════ FLASH SEPARATOR ═══════════════════════════ */
  {
    keywords: ["flash separator"],
    pricingUnit: "€ per unit",
    plantScaleQty: 3,
    bestPrice: { manufacturer: "Peerless (CECO)", model: "Vertical Flash Drum", country: "USA", priceEur: 65000, priceDisplay: "€65k", efficiency: "99% liquid separation, mesh pad", leadTimeMonths: 5, trl: 9 },
    bestEfficiency: { manufacturer: "Koch-Glitsch", model: "DEMISTER® Mist Eliminator Flash Drum", country: "USA", priceEur: 140000, priceDisplay: "€140k", efficiency: "99.9%, vane + mesh, < 0.1 ppm carryover", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "HAT International", model: "Modular Flash Vessel", country: "Germany", priceEur: 95000, priceDisplay: "€95k/unit (at 3+)", efficiency: "99.5% liquid separation", scaleThreshold: "3+ units, shared condensate system", leadTimeMonths: 6, trl: 9 },
  },

  /* ═══════════════════════════ EXPANDER ═══════════════════════════ */
  {
    keywords: ["expander", "turboexpander"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Atlas Copco Gas and Process (Rotoflow)", model: "RE-1 Cryogenic Turboexpander", country: "USA", priceEur: 450000, priceDisplay: "€450k", efficiency: "88% isentropic, gas bearings", leadTimeMonths: 10, trl: 9 },
    bestEfficiency: { manufacturer: "Linde Engineering (Cryostar)", model: "TurbXpand™ LNG Expander", country: "France", priceEur: 950000, priceDisplay: "€950k", efficiency: "92% isentropic, magnetic bearings", leadTimeMonths: 14, trl: 9 },
    economiesOfScale: { manufacturer: "Air Products", model: "Integrated Expander-Compressor", country: "USA", priceEur: 680000, priceDisplay: "€680k/unit (at 2+)", efficiency: "90% isentropic, expander + booster", scaleThreshold: "2+ units, matched cold box", leadTimeMonths: 12, trl: 9 },
  },

  /* ═══════════════════════════ FEEDER HOPPER ═══════════════════════════ */
  {
    keywords: ["feeder hopper"],
    pricingUnit: "€ per unit",
    plantScaleQty: 4,
    bestPrice: { manufacturer: "Schenck Process", model: "Multidos® Weighfeeder", country: "Germany", priceEur: 22000, priceDisplay: "€22k", efficiency: "±0.5%, belt weighfeeder, 50 tph", leadTimeMonths: 4, trl: 9 },
    bestEfficiency: { manufacturer: "K-Tron (Coperion)", model: "Loss-in-Weight Feeder K-ML-D5-KT20", country: "Switzerland", priceEur: 55000, priceDisplay: "€55k", efficiency: "±0.1%, gravimetric, 20 tph", leadTimeMonths: 6, trl: 9 },
    economiesOfScale: { manufacturer: "Brabender Technologie", model: "FlexWall® Feeder System", country: "Germany", priceEur: 35000, priceDisplay: "€35k/unit (at 4+)", efficiency: "±0.25%, multi-component", scaleThreshold: "4+ units, recipe management system", leadTimeMonths: 5, trl: 9 },
  },

  /* ═══════════════════════════ VFD DRIVE ═══════════════════════════ */
  {
    keywords: ["vfd drive", "variable frequency drive"],
    pricingUnit: "€ per unit",
    plantScaleQty: 20,
    bestPrice: { manufacturer: "ABB", model: "ACS580 General Purpose VFD", country: "Switzerland", priceEur: 3500, priceDisplay: "€3,500", efficiency: "98%, 0.75–250 kW, HVAC/pump", leadTimeMonths: 3, trl: 9 },
    bestEfficiency: { manufacturer: "Siemens", model: "SINAMICS G120X Infrastructure VFD", country: "Germany", priceEur: 6500, priceDisplay: "€6,500", efficiency: "98.5%, integrated EMC filter", leadTimeMonths: 5, trl: 9 },
    economiesOfScale: { manufacturer: "Danfoss", model: "VACON® NXP Liquid Cooled", country: "Denmark", priceEur: 4800, priceDisplay: "€4,800/unit (at 15+)", efficiency: "98.2%, IP54, SIL 2 ready", scaleThreshold: "15+ units, fleet commissioning", leadTimeMonths: 4, trl: 9 },
  },

  /* ═══════════════════════════ FIREWATER PUMP UNIT ═══════════════════════════ */
  {
    keywords: ["firewater pump"],
    pricingUnit: "€ per unit",
    plantScaleQty: 2,
    bestPrice: { manufacturer: "Xylem (AC Fire Pump)", model: "8100 Series Split-Case", country: "USA", priceEur: 65000, priceDisplay: "€65k", efficiency: "1500 GPM @ 125 psi, electric", leadTimeMonths: 5, trl: 9 },
    bestEfficiency: { manufacturer: "Grundfos (Peerless)", model: "AEF Vertical Turbine Fire Pump", country: "Denmark", priceEur: 120000, priceDisplay: "€120k", efficiency: "2500 GPM @ 150 psi, UL/FM listed", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "SPP Pumps", model: "Diesel + Electric Fire Pump Package", country: "UK", priceEur: 85000, priceDisplay: "€85k/pkg (at 2+)", efficiency: "2000 GPM, NFPA 20 compliant", scaleThreshold: "2+ packages, jockey pump shared", leadTimeMonths: 6, trl: 9 },
  },

  /* ═══════════════════════════ OIL WATER SEPARATOR ═══════════════════════════ */
  {
    keywords: ["oil water separator"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Highland Tank", model: "API 421 Gravity Separator", country: "USA", priceEur: 35000, priceDisplay: "€35k", efficiency: "Oil in effluent < 15 ppm, gravity", leadTimeMonths: 4, trl: 9 },
    bestEfficiency: { manufacturer: "Veolia (Enhydra)", model: "TPI Coalescer OWS", country: "France", priceEur: 95000, priceDisplay: "€95k", efficiency: "Oil in effluent < 5 ppm, coalescer plates", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "Hydrasep", model: "Modular CPI Separator", country: "UK", priceEur: 55000, priceDisplay: "€55k/unit (at 2+)", efficiency: "Oil < 10 ppm, corrugated plate", scaleThreshold: "2+ units, shared sludge handling", leadTimeMonths: 5, trl: 9 },
  },

  /* ═══════════════════════════ COOLING TOWER MAKEUP WATER SYSTEM ═══════════════════════════ */
  {
    keywords: ["cooling tower makeup"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Nalco (Ecolab)", model: "3D TRASAR™ Makeup Controller", country: "USA", priceEur: 45000, priceDisplay: "€45k", efficiency: "Auto makeup + blowdown, CoC 6+", leadTimeMonths: 4, trl: 9 },
    bestEfficiency: { manufacturer: "Veolia Water Technologies", model: "Integrated MU + Side-Stream Filter", country: "France", priceEur: 120000, priceDisplay: "€120k", efficiency: "CoC 8+, side-stream filtration", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "Evoqua (Xylem)", model: "VANTAGE® CT Makeup System", country: "USA", priceEur: 75000, priceDisplay: "€75k/system (at 2+)", efficiency: "CoC 7, auto chemical dosing", scaleThreshold: "2+ systems, shared chemical storage", leadTimeMonths: 6, trl: 9 },
  },

  /* ═══════════════════════════ FLUE GAS BLOWER ═══════════════════════════ */
  {
    keywords: ["flue gas blower"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Howden", model: "VariAx Axial Fan FG-3000", country: "UK", priceEur: 85000, priceDisplay: "€85k", efficiency: "82% static eff., 200°C service", leadTimeMonths: 6, trl: 9 },
    bestEfficiency: { manufacturer: "TLT-Turbo", model: "Centrifugal FG Fan HAF Series", country: "Germany", priceEur: 180000, priceDisplay: "€180k", efficiency: "88% static eff., high-temp alloy", leadTimeMonths: 10, trl: 9 },
    economiesOfScale: { manufacturer: "Clarage (Twin City Fan)", model: "ID Fan Size 73 Multi-Service", country: "USA", priceEur: 120000, priceDisplay: "€120k/unit (at 2+)", efficiency: "85% static eff.", scaleThreshold: "2+ units, shared silencer/duct", leadTimeMonths: 8, trl: 9 },
  },

  /* ═══════════════════════════ MERCURY REMOVAL UNIT ═══════════════════════════ */
  {
    keywords: ["mercury removal"],
    pricingUnit: "€ per unit",
    bestPrice: { manufacturer: "Johnson Matthey", model: "PURASPEC™ 2156 Hg Guard Bed", country: "UK", priceEur: 85000, priceDisplay: "€85k", efficiency: "Hg < 0.01 µg/Nm³, sulfided carbon", leadTimeMonths: 5, trl: 9 },
    bestEfficiency: { manufacturer: "UOP (Honeywell)", model: "HgSIV™ Molecular Sieve Hg Removal", country: "USA", priceEur: 180000, priceDisplay: "€180k", efficiency: "Hg < 0.001 µg/Nm³, regenerable", leadTimeMonths: 8, trl: 9 },
    economiesOfScale: { manufacturer: "BASF", model: "Activated Carbon Hg Adsorber", country: "Germany", priceEur: 120000, priceDisplay: "€120k/bed (at 2+)", efficiency: "Hg < 0.01 µg/Nm³", scaleThreshold: "2+ beds, lead-lag operation", leadTimeMonths: 6, trl: 9 },
  },

  /* ═══════════════════════════ DESALINATION ═══════════════════════════ */
  {
    keywords: ["desalination"],
    pricingUnit: "€ total installed",
    bestPrice: { manufacturer: "IDE Technologies", model: "PROGREEN™ SWRO 10,000 m³/d", country: "Israel", priceEur: 4500000, priceDisplay: "€4.5M", efficiency: "3.5 kWh/m³, energy recovery", leadTimeMonths: 14, trl: 9 },
    bestEfficiency: { manufacturer: "Veolia Water Technologies", model: "Barrel™ SWRO 20,000 m³/d", country: "France", priceEur: 9500000, priceDisplay: "€9.5M", efficiency: "2.8 kWh/m³, isobaric ERD", leadTimeMonths: 20, trl: 9 },
    economiesOfScale: { manufacturer: "Acciona Agua", model: "Modular SWRO Container 5000 m³/d", country: "Spain", priceEur: 3200000, priceDisplay: "€3.2M/container (at 4+)", efficiency: "3.2 kWh/m³", scaleThreshold: "4+ containers, mega-plant assembly", leadTimeMonths: 16, trl: 9 },
  },
];

/* ═══════════════════════════ MATCHER FUNCTION ═══════════════════════════ */

export type ProcurementStrategy = "bestPrice" | "bestEfficiency" | "economiesOfScale";

export function matchProcurement(
  label: string,
  strategy: ProcurementStrategy
): ManufacturerOption | null {
  const l = label.toLowerCase();
  for (const entry of procurementDatabase) {
    for (const kw of entry.keywords) {
      if (l.includes(kw)) {
        return entry[strategy];
      }
    }
  }
  return null;
}

/** Get the full procurement entry for a label (for comparison views) */
export function getProcurementEntry(label: string): EquipmentProcurement | null {
  const l = label.toLowerCase();
  for (const entry of procurementDatabase) {
    for (const kw of entry.keywords) {
      if (l.includes(kw)) return entry;
    }
  }
  return null;
}

export const strategyLabels: Record<ProcurementStrategy, { label: string; description: string; icon: string }> = {
  bestPrice: {
    label: "Best Price",
    description: "Lowest CAPEX, cost-competitive manufacturers, proven technology",
    icon: "dollar",
  },
  bestEfficiency: {
    label: "Highest Efficiency",
    description: "Maximum output per unit, premium manufacturers, best-in-class performance",
    icon: "zap",
  },
  economiesOfScale: {
    label: "Economies of Scale",
    description: "Volume pricing & modular designs, optimized for large-scale deployment",
    icon: "scale",
  },
};
