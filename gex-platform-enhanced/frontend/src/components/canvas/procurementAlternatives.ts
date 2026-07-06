/**
 * Alternative manufacturer options for each equipment category.
 * Maps from the first keyword of an EquipmentProcurement entry
 * to 2-3 additional real-world manufacturer options.
 *
 * These are merged into the Supplier Database catalog at display-time.
 */
import type { ManufacturerOption } from "./procurementDatabase";

export interface AlternativeOption extends ManufacturerOption {
  /** Which strategy this alternative is closest to */
  strategyTag: "bestPrice" | "bestEfficiency" | "economiesOfScale";
}

/** key = first keyword from the procurementDatabase entry */
export const procurementAlternatives: Record<string, AlternativeOption[]> = {
  /* ── ELECTROLYSIS ── */
  electrolyzer: [
    { strategyTag: "bestEfficiency", manufacturer: "ITM Power", model: "NEPTUNE PEM 5 MW", country: "UK", priceEur: 1050, priceDisplay: "€1,050/kW", efficiency: "4.6 kWh/Nm³ H₂, 52 kg/h per stack", scaleThreshold: ">5 MW", leadTimeMonths: 12, trl: 9 },
    { strategyTag: "bestPrice", manufacturer: "Peric Hydrogen", model: "ALK 1000 Nm³/h", country: "China", priceEur: 310, priceDisplay: "€310/kW", efficiency: "4.5 kWh/Nm³ H₂ (LHV)", scaleThreshold: ">10 MW", leadTimeMonths: 6, trl: 9 },
    { strategyTag: "economiesOfScale", manufacturer: "Plug Power", model: "EX-5500D PEM 5 MW Module", country: "USA", priceEur: 750, priceDisplay: "€750/kW (at 50+ MW)", efficiency: "4.7 kWh/Nm³ H₂", scaleThreshold: "50+ MW, turnkey", leadTimeMonths: 10, trl: 9 },
  ],

  /* ── COMPRESSORS (H₂) ── */
  compressor: [
    { strategyTag: "bestPrice", manufacturer: "PDC Machines", model: "PDC-13 Diaphragm 200 bar", country: "USA", priceEur: 350000, priceDisplay: "€350k", efficiency: "86% isentropic, up to 450 bar", leadTimeMonths: 8, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Hitachi", model: "Oil-Free Reciprocating HC Series", country: "Japan", priceEur: 850000, priceDisplay: "€850k", efficiency: "91% isentropic, 5-stage to 900 bar", leadTimeMonths: 16, trl: 9 },
  ],

  /* ── WATER TREATMENT ── */
  "water treatment": [
    { strategyTag: "bestPrice", manufacturer: "Pall Water", model: "Aria™ UF + RO Train", country: "USA", priceEur: 165000, priceDisplay: "€165k", efficiency: "94% recovery, 40 m³/h", leadTimeMonths: 6, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Evoqua (Xylem)", model: "CDI™ Continuous Deionization", country: "USA", priceEur: 310000, priceDisplay: "€310k", efficiency: "99.7% ion rejection, chemical-free", leadTimeMonths: 8, trl: 9 },
    { strategyTag: "economiesOfScale", manufacturer: "Aquatech International", model: "HERO™ High-Efficiency RO", country: "USA", priceEur: 280000, priceDisplay: "€280k/train (at 3+)", efficiency: "98% recovery, zero liquid discharge ready", scaleThreshold: "3+ trains", leadTimeMonths: 8, trl: 9 },
  ],

  /* ── PURIFICATION (PSA) ── */
  purif: [
    { strategyTag: "bestPrice", manufacturer: "Xebec Adsorption", model: "H-3200 PSA H₂", country: "Canada", priceEur: 650000, priceDisplay: "€650k", efficiency: "99.99% H₂ purity, 84% recovery", leadTimeMonths: 8, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Mahler AGS", model: "Hydrogen PSA 10-Bed", country: "Germany", priceEur: 1050000, priceDisplay: "€1.05M", efficiency: "99.999% H₂ purity, 93% recovery", leadTimeMonths: 12, trl: 9 },
  ],

  /* ── HEAT EXCHANGERS ── */
  "heat exchanger": [
    { strategyTag: "bestPrice", manufacturer: "Hisaka Works", model: "UX Series Plate Heat Exchanger", country: "Japan", priceEur: 75000, priceDisplay: "€75k", efficiency: "91% thermal eff., up to 180°C", leadTimeMonths: 5, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Tranter", model: "SUPERMAX™ Shell & Plate", country: "USA", priceEur: 180000, priceDisplay: "€180k", efficiency: "97% thermal eff., up to 900°C", leadTimeMonths: 10, trl: 9 },
    { strategyTag: "economiesOfScale", manufacturer: "GEA Heat Exchangers", model: "WTT Welded Plate", country: "Germany", priceEur: 110000, priceDisplay: "€110k/unit (20% off at 5+)", efficiency: "95% thermal eff.", scaleThreshold: "5+ units", leadTimeMonths: 6, trl: 9 },
  ],

  /* ── PUMPS ── */
  pump: [
    { strategyTag: "bestPrice", manufacturer: "Flowserve", model: "INNOMAG TB-MAG Sealless", country: "USA", priceEur: 32000, priceDisplay: "€32k", efficiency: "80% hydraulic eff., zero-leak", leadTimeMonths: 4, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "ITT Goulds", model: "IC 3196 Chemical Process Pump", country: "USA", priceEur: 95000, priceDisplay: "€95k", efficiency: "89% hydraulic eff., API 610", leadTimeMonths: 8, trl: 9 },
  ],

  /* ── REFORMING REACTORS ── */
  reformer: [
    { strategyTag: "bestPrice", manufacturer: "Haldor Topsoe", model: "Side-Fired Reformer SFR-100", country: "Denmark", priceEur: 3800000, priceDisplay: "€3.8M", efficiency: "80% conversion eff.", leadTimeMonths: 18, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Linde Engineering", model: "Multi-Tubular Reformer", country: "Germany", priceEur: 5800000, priceDisplay: "€5.8M", efficiency: "92% methane conversion, integrated WHR", leadTimeMonths: 22, trl: 9 },
  ],

  /* ── SYNTHESIS REACTORS ── */
  reactor: [
    { strategyTag: "bestPrice", manufacturer: "Haldor Topsoe", model: "S-200 Radial-Flow Converter", country: "Denmark", priceEur: 3100000, priceDisplay: "€3.1M", efficiency: "Per-pass 38%", leadTimeMonths: 18, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Johnson Matthey", model: "DAVY™ Low-Pressure MeOH", country: "UK", priceEur: 4800000, priceDisplay: "€4.8M", efficiency: "Per-pass 55%, tube-cooled", leadTimeMonths: 20, trl: 9 },
  ],

  /* ── STORAGE TANKS ── */
  tank: [
    { strategyTag: "bestPrice", manufacturer: "Worthington Industries", model: "Type III Steel/Composite 350 bar", country: "USA", priceEur: 180000, priceDisplay: "€180k", efficiency: "350 bar, 6 kg/vessel", leadTimeMonths: 5, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Linde Engineering", model: "Vacuum-Insulated LH₂ Sphere", country: "Germany", priceEur: 1200000, priceDisplay: "€1.2M", efficiency: "Boil-off <0.1%/day, 300 m³", leadTimeMonths: 18, trl: 9 },
    { strategyTag: "economiesOfScale", manufacturer: "Faber Industrie", model: "CNG/H₂ Cylinder Rack", country: "Italy", priceEur: 250000, priceDisplay: "€250k/rack (at 12+)", efficiency: "450 bar, 25 kg/rack", scaleThreshold: "12+ racks, cascade filling", leadTimeMonths: 6, trl: 9 },
  ],

  /* ── BOILERS / HRSG ── */
  boiler: [
    { strategyTag: "bestPrice", manufacturer: "Cleaver-Brooks", model: "ClearFire CFH Condensing Boiler", country: "USA", priceEur: 850000, priceDisplay: "€850k", efficiency: "87% thermal eff., H₂-ready", leadTimeMonths: 8, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Siemens Energy", model: "Benson Once-Through HRSG", country: "Germany", priceEur: 3200000, priceDisplay: "€3.2M", efficiency: "96% thermal eff., supercritical", leadTimeMonths: 18, trl: 9 },
  ],

  /* ── TURBINES ── */
  turbine: [
    { strategyTag: "bestPrice", manufacturer: "Solar Turbines (CAT)", model: "Titan 250 Gas Turbine", country: "USA", priceEur: 4500000, priceDisplay: "€4.5M", efficiency: "35% simple cycle, 30% H₂ blend", leadTimeMonths: 12, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Mitsubishi Power", model: "H-25 Gas Turbine (H₂ co-fire)", country: "Japan", priceEur: 8500000, priceDisplay: "€8.5M", efficiency: "40% simple cycle, 100% H₂ capable", leadTimeMonths: 18, trl: 9 },
  ],

  /* ── SEPARATORS ── */
  separator: [
    { strategyTag: "bestPrice", manufacturer: "AMACS Process Towers", model: "Structured Packing Column", country: "USA", priceEur: 110000, priceDisplay: "€110k", efficiency: "HETP 0.38 m", leadTimeMonths: 5, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "HAT International", model: "High-Performance Random Packing", country: "Germany", priceEur: 200000, priceDisplay: "€200k", efficiency: "HETP 0.25 m, low fouling", leadTimeMonths: 8, trl: 9 },
  ],

  /* ── DISTILLATION ── */
  distillation: [
    { strategyTag: "bestPrice", manufacturer: "Raschig", model: "Pall Ring Tray Column", country: "Germany", priceEur: 380000, priceDisplay: "€380k", efficiency: "72% tray efficiency, low cost", leadTimeMonths: 8, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Montz", model: "BSH Structured Packing Column", country: "Germany", priceEur: 750000, priceDisplay: "€750k", efficiency: "HETP 0.12 m, ultra-high purity", leadTimeMonths: 12, trl: 9 },
  ],

  /* ── FILTERS ── */
  filter: [
    { strategyTag: "bestPrice", manufacturer: "Parker Hannifin", model: "Fulflo® Cartridge Filter Vessel", country: "USA", priceEur: 45000, priceDisplay: "€45k", efficiency: "99.5%, 1 µm, easy changeout", leadTimeMonths: 3, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Eaton Filtration", model: "DCF-2000 Self-Cleaning Filter", country: "USA", priceEur: 160000, priceDisplay: "€160k", efficiency: "99.98%, auto-backwash, continuous", leadTimeMonths: 8, trl: 9 },
  ],

  /* ── COOLING TOWERS ── */
  "cooling tower": [
    { strategyTag: "bestPrice", manufacturer: "BAC (Baltimore Aircoil)", model: "Series 3000 Induced Draft", country: "USA", priceEur: 200000, priceDisplay: "€200k", efficiency: "Approach 3.8°C, fiberglass", leadTimeMonths: 7, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Evapco", model: "AT Hybrid Adiabatic Cooler", country: "USA", priceEur: 420000, priceDisplay: "€420k", efficiency: "Approach 2.0°C, 80% water savings", leadTimeMonths: 12, trl: 9 },
  ],

  /* ── GASIFIERS ── */
  gasifier: [
    { strategyTag: "bestPrice", manufacturer: "HoSt Group", model: "Downdraft Fixed-Bed 500 kWth", country: "Netherlands", priceEur: 1800000, priceDisplay: "€1.8M", efficiency: "Cold gas eff. 72%, low tar", leadTimeMonths: 12, trl: 8 },
    { strategyTag: "bestEfficiency", manufacturer: "Sierra Energy", model: "FastOx™ Gasifier", country: "USA", priceEur: 6200000, priceDisplay: "€6.2M", efficiency: "Cold gas eff. 85%, oxygen-blown", leadTimeMonths: 20, trl: 7 },
  ],

  /* ── CO₂ CAPTURE ── */
  "co2 capture": [
    { strategyTag: "bestPrice", manufacturer: "Carbon Clean", model: "CycloneCC Modular 100 ktCO₂/yr", country: "UK", priceEur: 1500000, priceDisplay: "€1.5M", efficiency: "90% capture, rotating packed bed", leadTimeMonths: 12, trl: 8 },
    { strategyTag: "bestEfficiency", manufacturer: "Fluor", model: "Econamine FG Plus™", country: "USA", priceEur: 2800000, priceDisplay: "€2.8M", efficiency: "95% capture, advanced amine, 2.4 GJ/tCO₂", leadTimeMonths: 18, trl: 9 },
  ],

  /* ── FUEL CELLS ── */
  "fuel cell": [
    { strategyTag: "bestPrice", manufacturer: "Hyzon Motors", model: "200 kW PEM FC Module", country: "USA", priceEur: 550, priceDisplay: "€550/kW", efficiency: "55% electrical eff.", leadTimeMonths: 5, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "FuelCell Energy", model: "SureSource 3000 MCFC", country: "USA", priceEur: 3200, priceDisplay: "€3,200/kW", efficiency: "60% electrical, 90% CHP eff.", leadTimeMonths: 14, trl: 9 },
  ],

  /* ── ASU / N₂ / O₂ ── */
  "air separation": [
    { strategyTag: "bestPrice", manufacturer: "CRYOGENMASH", model: "KdA-3000 Cryogenic ASU", country: "Russia", priceEur: 3800000, priceDisplay: "€3.8M", efficiency: "0.40 kWh/Nm³ O₂", leadTimeMonths: 14, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Air Products", model: "PRISM® Membrane N₂ + Cryo O₂", country: "USA", priceEur: 7500000, priceDisplay: "€7.5M", efficiency: "0.33 kWh/Nm³ O₂, N₂ co-product", leadTimeMonths: 18, trl: 9 },
  ],

  /* ── FLARE SYSTEMS ── */
  flare: [
    { strategyTag: "bestPrice", manufacturer: "Honeywell (Callidus)", model: "LSVF™ Low-Smoke Utility Flare", country: "USA", priceEur: 250000, priceDisplay: "€250k", efficiency: "99.5% DRE, steam-assisted", leadTimeMonths: 6, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Tornado Combustion Technologies", model: "Tornado XP Enclosed Flare", country: "USA", priceEur: 480000, priceDisplay: "€480k", efficiency: "99.99% DRE, zero visible flame", leadTimeMonths: 8, trl: 9 },
  ],

  /* ── TRANSFORMERS / ELECTRICAL ── */
  transformer: [
    { strategyTag: "bestPrice", manufacturer: "Hyundai Electric", model: "Oil-Immersed Transformer 40 MVA", country: "South Korea", priceEur: 88000, priceDisplay: "€88k", efficiency: "99.3%, compact design", leadTimeMonths: 6, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Schneider Electric", model: "Trihal Cast-Resin Dry Transformer", country: "France", priceEur: 195000, priceDisplay: "€195k", efficiency: "99.5%, C2 fire-safe, eco-design", leadTimeMonths: 10, trl: 9 },
  ],

  /* ── LIQUEFACTION ── */
  liquefaction: [
    { strategyTag: "bestPrice", manufacturer: "Stirling Cryogenics", model: "StirLIN-4 Small-Scale H₂ Liquefier", country: "Netherlands", priceEur: 8500000, priceDisplay: "€8.5M", efficiency: "10 kWh/kg LH₂, 5 tpd", leadTimeMonths: 16, trl: 8 },
    { strategyTag: "bestEfficiency", manufacturer: "Air Products", model: "AP-X LH₂ Liquefier", country: "USA", priceEur: 28000000, priceDisplay: "€28M", efficiency: "5.8 kWh/kg LH₂, 150 tpd", leadTimeMonths: 28, trl: 9 },
  ],

  /* ── POWER RECTIFIER ── */
  "power rectifier": [
    { strategyTag: "bestPrice", manufacturer: "Rectifier Technologies", model: "TFE 1000A DC Rectifier", country: "Australia", priceEur: 72000, priceDisplay: "€72k", efficiency: "96% AC-DC, thyristor-based", leadTimeMonths: 5, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "REFU Elektronik", model: "REFUdrive CL 500 kW", country: "Germany", priceEur: 145000, priceDisplay: "€145k", efficiency: "98% AC-DC, IGBT-based", leadTimeMonths: 8, trl: 9 },
  ],

  /* ── INVERTER ── */
  inverter: [
    { strategyTag: "bestPrice", manufacturer: "GoodWe", model: "HT 250K Central Inverter", country: "China", priceEur: 38000, priceDisplay: "€38k", efficiency: "98.7% DC-AC", leadTimeMonths: 3, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "ABB (FIMER)", model: "PVS-175 String Inverter", country: "Italy", priceEur: 82000, priceDisplay: "€82k", efficiency: "99.1% peak DC-AC, SiC topology", leadTimeMonths: 6, trl: 9 },
  ],

  /* ── SWITCHGEAR ── */
  switchgear: [
    { strategyTag: "bestPrice", manufacturer: "Hyundai Electric", model: "HVF 24 kV Vacuum Switchgear", country: "South Korea", priceEur: 48000, priceDisplay: "€48k", efficiency: "SF₆-free, vacuum breaker", leadTimeMonths: 5, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Siemens Energy", model: "NXPLUS C 36 kV GIS", country: "Germany", priceEur: 135000, priceDisplay: "€135k", efficiency: "Gas-insulated, compact footprint", leadTimeMonths: 10, trl: 9 },
  ],

  /* ── MOTOR CONTROL CENTER ── */
  "motor control center": [
    { strategyTag: "bestPrice", manufacturer: "Schneider Electric", model: "Okken MCC Low-Voltage", country: "France", priceEur: 32000, priceDisplay: "€32k/section", efficiency: "IEC 61439-2, type-tested", leadTimeMonths: 6, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Eaton", model: "Freedom 2100 Intelligent MCC", country: "USA", priceEur: 58000, priceDisplay: "€58k/section", efficiency: "Predictive analytics, IoT-enabled", leadTimeMonths: 8, trl: 9 },
  ],

  /* ── UPS ── */
  "uninterruptible power supply": [
    { strategyTag: "bestPrice", manufacturer: "Vertiv", model: "Liebert EXL S1 800 kVA", country: "USA", priceEur: 105000, priceDisplay: "€105k", efficiency: "97% double-conversion", leadTimeMonths: 5, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Socomec", model: "DELPHYS GP 1000 kVA", country: "France", priceEur: 240000, priceDisplay: "€240k", efficiency: "99.2% ECO mode", leadTimeMonths: 8, trl: 9 },
  ],

  /* ── BESS ── */
  "battery energy storage": [
    { strategyTag: "bestPrice", manufacturer: "EVE Energy", model: "LF280K LFP Container 20ft", country: "China", priceEur: 135, priceDisplay: "€135/kWh", efficiency: "95% round-trip, 6000 cycles", leadTimeMonths: 5, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Fluence", model: "Gridstack Pro 4h Duration", country: "USA", priceEur: 260, priceDisplay: "€260/kWh", efficiency: "97% round-trip, augmentation-free", leadTimeMonths: 10, trl: 9 },
  ],

  /* ── PIPELINE ── */
  pipeline: [
    { strategyTag: "bestPrice", manufacturer: "ArcelorMittal Tubular", model: "API 5L X52 H₂ Service", country: "Luxembourg", priceEur: 290, priceDisplay: "€290/m", efficiency: "API 5L X52, up to 80 bar", leadTimeMonths: 8, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Nippon Steel", model: "OCTG H₂-Resistant Line Pipe X65", country: "Japan", priceEur: 620, priceDisplay: "€620/m", efficiency: "API 5L X65, HIC/SSC tested", leadTimeMonths: 14, trl: 9 },
  ],

  /* ── COMPRESSOR STATION ── */
  "compressor station": [
    { strategyTag: "bestPrice", manufacturer: "Dresser-Rand (Siemens)", model: "DATUM Centrifugal Station", country: "USA", priceEur: 3200000, priceDisplay: "€3.2M", efficiency: "89% polytropic, oil-free", leadTimeMonths: 14, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "MAN Energy Solutions", model: "RG Integrally-Geared Station", country: "Germany", priceEur: 5800000, priceDisplay: "€5.8M", efficiency: "93% polytropic, intercooled", leadTimeMonths: 18, trl: 9 },
  ],

  /* ── HEADER ── */
  header: [
    { strategyTag: "bestPrice", manufacturer: "Gestamp Renewables", model: "Carbon Steel Header DN400", country: "Spain", priceEur: 38000, priceDisplay: "€38k", efficiency: "EN 13480, up to 80 bar", leadTimeMonths: 4, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Mannesmann Stainless Tubes", model: "Duplex SS Header DN600", country: "Germany", priceEur: 110000, priceDisplay: "€110k", efficiency: "ASME VIII, H₂/sour service", leadTimeMonths: 10, trl: 9 },
  ],

  /* ── VALVES ── */
  valve: [
    { strategyTag: "bestPrice", manufacturer: "Velan", model: "Forged Gate Valve API 602", country: "Canada", priceEur: 1100, priceDisplay: "€1,100", efficiency: "Class 800, up to DN50", leadTimeMonths: 3, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Cameron (Schlumberger)", model: "ORBIT Rising Stem Ball Valve", country: "USA", priceEur: 5200, priceDisplay: "€5,200", efficiency: "Zero-leakage, metal-seated, H₂ service", leadTimeMonths: 6, trl: 9 },
  ],

  /* ── JT VALVE ── */
  "jt valve": [
    { strategyTag: "bestPrice", manufacturer: "Samson", model: "Type 3291 JT Service Globe Valve", country: "Germany", priceEur: 15000, priceDisplay: "€15k", efficiency: "Cv to 3000, cryogenic trim", leadTimeMonths: 5, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Flowserve (Valtek)", model: "Mark One JT Control Valve", country: "USA", priceEur: 32000, priceDisplay: "€32k", efficiency: "Anti-cavitation, low noise, SIL 3", leadTimeMonths: 8, trl: 9 },
  ],

  /* ── CONTROL VALVE ── */
  "control valve": [
    { strategyTag: "bestPrice", manufacturer: "Azbil (Yamatake)", model: "CV3000 Globe Control Valve", country: "Japan", priceEur: 2800, priceDisplay: "€2,800", efficiency: "DN15–DN200, HART", leadTimeMonths: 4, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Metso (Neles)", model: "Segment Ball Valve R-Series", country: "Finland", priceEur: 7200, priceDisplay: "€7,200", efficiency: "SIL 3, Neles NDX positioner", leadTimeMonths: 6, trl: 9 },
  ],

  /* ── CHECK VALVE ── */
  "check valve": [
    { strategyTag: "bestPrice", manufacturer: "Goodwin International", model: "Dual-Plate Wafer Check", country: "UK", priceEur: 750, priceDisplay: "€750", efficiency: "Low cracking, DN50–400", leadTimeMonths: 3, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Neway Valve", model: "Nozzle Check Valve, Non-Slam", country: "China", priceEur: 3200, priceDisplay: "€3,200", efficiency: "Center-guided, API 594", leadTimeMonths: 4, trl: 9 },
  ],

  /* ── PRESSURE REGULATING VALVE ── */
  "pressure regulating valve": [
    { strategyTag: "bestPrice", manufacturer: "Honeywell (Elster)", model: "MR Series Pressure Regulator", country: "Germany", priceEur: 2200, priceDisplay: "€2,200", efficiency: "Inlet 200 bar, spring-loaded", leadTimeMonths: 3, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Parker Hannifin", model: "Veriflo 54000 High-Purity Reg", country: "USA", priceEur: 4800, priceDisplay: "€4,800", efficiency: "Droop <1%, tied diaphragm", leadTimeMonths: 5, trl: 9 },
  ],

  /* ── PRESSURE RELIEF VALVE ── */
  "pressure relief valve": [
    { strategyTag: "bestPrice", manufacturer: "Curtiss-Wright (Farris)", model: "2600 Series Spring PRV", country: "USA", priceEur: 1600, priceDisplay: "€1,600", efficiency: "API 526, ASME certified", leadTimeMonths: 3, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Danfoss (Sempell)", model: "Pilot-Operated PRV", country: "Germany", priceEur: 5800, priceDisplay: "€5,800", efficiency: "99% set pressure, modulating", leadTimeMonths: 6, trl: 9 },
  ],

  /* ── RUPTURE DISC ── */
  "rupture disc": [
    { strategyTag: "bestPrice", manufacturer: "Continental Disc Corp", model: "Ultrx® Pre-Scored Disc", country: "USA", priceEur: 320, priceDisplay: "€320", efficiency: "±2% burst, ASME UD stamp", leadTimeMonths: 2, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Oseco", model: "FDB Forward-Acting Disc", country: "USA", priceEur: 580, priceDisplay: "€580", efficiency: "±1% burst, vacuum & pressure rated", leadTimeMonths: 3, trl: 9 },
  ],

  /* ── ORIFICE ── */
  orifice: [
    { strategyTag: "bestPrice", manufacturer: "Rosemount (Emerson)", model: "1195 Orifice Plate Assembly", country: "USA", priceEur: 1200, priceDisplay: "€1,200", efficiency: "ISO 5167, corner taps, ±1%", leadTimeMonths: 3, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Krohne", model: "OPTIBAR DP 7060 Orifice", country: "Germany", priceEur: 3500, priceDisplay: "€3,500", efficiency: "Integrated DP, ±0.3%", leadTimeMonths: 5, trl: 9 },
  ],

  /* ── SAMPLING SYSTEM ── */
  "sampling system": [
    { strategyTag: "bestPrice", manufacturer: "Circor (Dopak)", model: "Closed-Loop Liquid Sampler", country: "Germany", priceEur: 7500, priceDisplay: "€7,500", efficiency: "ISO 3170, zero emissions", leadTimeMonths: 4, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "A+ FlameInline", model: "AutoSampler Multi-Stream Panel", country: "Netherlands", priceEur: 25000, priceDisplay: "€25k", efficiency: "16-stream, GC/MS integration", leadTimeMonths: 8, trl: 9 },
  ],

  /* ── METERING SYSTEM ── */
  "metering system": [
    { strategyTag: "bestPrice", manufacturer: "Krohne", model: "OPTIMASS 6400 Coriolis", country: "Germany", priceEur: 7500, priceDisplay: "€7,500", efficiency: "±0.1%, twin-tube", leadTimeMonths: 4, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Honeywell (Elster)", model: "Q.Sonic Max Ultrasonic", country: "Germany", priceEur: 22000, priceDisplay: "€22k", efficiency: "±0.03%, custody transfer, 8-path", leadTimeMonths: 6, trl: 9 },
  ],

  /* ── CO2 COMPRESSOR ── */
  "co2 compressor": [
    { strategyTag: "bestPrice", manufacturer: "Siemens Energy", model: "STC-SV CO₂ Centrifugal", country: "Germany", priceEur: 2000000, priceDisplay: "€2M", efficiency: "87% polytropic, dry gas seals", leadTimeMonths: 14, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Mitsubishi Heavy Industries", model: "MCO-I CO₂ Compressor", country: "Japan", priceEur: 3500000, priceDisplay: "€3.5M", efficiency: "91% polytropic, integral gearbox", leadTimeMonths: 18, trl: 9 },
  ],

  /* ── SYNGAS COMPRESSOR ── */
  "syngas compressor": [
    { strategyTag: "bestPrice", manufacturer: "Dresser-Rand (Siemens)", model: "DATUM Syngas Centrifugal", country: "USA", priceEur: 2500000, priceDisplay: "€2.5M", efficiency: "86% polytropic, API 617", leadTimeMonths: 16, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "MAN Energy Solutions", model: "RG Integrally-Geared Syngas", country: "Germany", priceEur: 4200000, priceDisplay: "€4.2M", efficiency: "90% polytropic, variable IGV", leadTimeMonths: 18, trl: 9 },
  ],

  /* ── NATURAL GAS COMPRESSOR ── */
  "natural gas compressor": [
    { strategyTag: "bestPrice", manufacturer: "Bauer Compressors", model: "GIB 26-S NG Compressor", country: "Germany", priceEur: 580000, priceDisplay: "€580k", efficiency: "86% isentropic, 2-stage", leadTimeMonths: 8, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Baker Hughes (Nuovo Pignone)", model: "MCL NG Centrifugal", country: "Italy", priceEur: 1600000, priceDisplay: "€1.6M", efficiency: "91% polytropic, dry gas seals", leadTimeMonths: 14, trl: 9 },
  ],

  /* ── AIR COMPRESSOR ── */
  "air compressor": [
    { strategyTag: "bestPrice", manufacturer: "Ingersoll Rand", model: "MSG Centac C800 Oil-Free", country: "USA", priceEur: 280000, priceDisplay: "€280k", efficiency: "ISO 8573-1 Class 0, 200 kW", leadTimeMonths: 6, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Kaeser Compressors", model: "FSG 420-2 Oil-Free Screw", country: "Germany", priceEur: 520000, priceDisplay: "€520k", efficiency: "Specific power 5.8 kW/(m³/min)", leadTimeMonths: 8, trl: 9 },
  ],

  /* ── INSTRUMENT AIR COMPRESSOR ── */
  "instrument air compressor": [
    { strategyTag: "bestPrice", manufacturer: "Ingersoll Rand", model: "Sierra Oil-Free 37 kW", country: "USA", priceEur: 28000, priceDisplay: "€28k", efficiency: "ISO 8573-1 Class 0, 7 bar", leadTimeMonths: 3, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Boge", model: "S-4 Oil-Free Scroll 15 kW", country: "Germany", priceEur: 55000, priceDisplay: "€55k", efficiency: "Ultra-quiet, 62 dB(A)", leadTimeMonths: 4, trl: 9 },
  ],

  /* ── REFRIGERATION COMPRESSOR ── */
  "refrigeration compressor": [
    { strategyTag: "bestPrice", manufacturer: "Bitzer", model: "CSH Screw Compressor NH₃ 300 kW", country: "Germany", priceEur: 65000, priceDisplay: "€65k", efficiency: "COP 4.2, R717", leadTimeMonths: 5, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Mycom (Mayekawa)", model: "N Series Screw NH₃ 800 kW", country: "Japan", priceEur: 180000, priceDisplay: "€180k", efficiency: "COP 5.8, variable Vi", leadTimeMonths: 8, trl: 9 },
  ],

  /* ── BLOWER ── */
  blower: [
    { strategyTag: "bestPrice", manufacturer: "Aerzen", model: "GM Series Roots Blower", country: "Germany", priceEur: 22000, priceDisplay: "€22k", efficiency: "1000 Nm³/h, Δp 1 bar", leadTimeMonths: 4, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Howden", model: "Turbo Blower SG Series", country: "UK", priceEur: 85000, priceDisplay: "€85k", efficiency: "86%, magnetic bearing, oil-free", leadTimeMonths: 8, trl: 9 },
  ],

  /* ── ELECTRIC GENERATOR ── */
  "electric generator": [
    { strategyTag: "bestPrice", manufacturer: "Leroy-Somer (Nidec)", model: "LSA 50.2 Alternator 2 MVA", country: "France", priceEur: 120000, priceDisplay: "€120k", efficiency: "96.5%, IP23, AVR", leadTimeMonths: 6, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "ABB", model: "AMG 1600 Synchronous 5 MVA", country: "Finland", priceEur: 380000, priceDisplay: "€380k", efficiency: "98%, brushless excitation", leadTimeMonths: 10, trl: 9 },
  ],

  /* ── ENGINE GENERATOR SET ── */
  "engine generator set": [
    { strategyTag: "bestPrice", manufacturer: "Caterpillar", model: "CG260-16 H₂-Ready Genset 4.5 MW", country: "USA", priceEur: 1800000, priceDisplay: "€1.8M", efficiency: "44% electrical, dual fuel", leadTimeMonths: 10, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Wärtsilä", model: "W34DF 9 MW Dual-Fuel Engine", country: "Finland", priceEur: 4200000, priceDisplay: "€4.2M", efficiency: "50% electrical, H₂ blend 25%", leadTimeMonths: 14, trl: 9 },
  ],

  /* ── STEAM DRUM ── */
  "steam drum": [
    { strategyTag: "bestPrice", manufacturer: "Larsen & Toubro", model: "Steam Drum 50 t/h, CS", country: "India", priceEur: 220000, priceDisplay: "€220k", efficiency: "ASME VIII, internal cyclones", leadTimeMonths: 8, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Doosan Enerbility", model: "HP Steam Drum 120 bar", country: "South Korea", priceEur: 550000, priceDisplay: "€550k", efficiency: "Chevron mist eliminators, SA-516 Gr.70", leadTimeMonths: 14, trl: 9 },
  ],

  /* ── DEAERATOR ── */
  deaerator: [
    { strategyTag: "bestPrice", manufacturer: "Sterling Deaerator Co.", model: "Spray-Tray Deaerator 50 t/h", country: "USA", priceEur: 85000, priceDisplay: "€85k", efficiency: "O₂ < 7 ppb, 3 trays", leadTimeMonths: 6, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Spirax Sarco", model: "HF-50P Pressurized Deaerator", country: "UK", priceEur: 180000, priceDisplay: "€180k", efficiency: "O₂ < 5 ppb, spray + tray", leadTimeMonths: 10, trl: 9 },
  ],

  /* ── CONDENSATE POLISHING UNIT ── */
  "condensate polishing": [
    { strategyTag: "bestPrice", manufacturer: "Graver Technologies", model: "Powdex® Precoat Filter", country: "USA", priceEur: 120000, priceDisplay: "€120k", efficiency: "Fe/Cu < 5 ppb, cation conductivity < 0.1 µS", leadTimeMonths: 6, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Veolia (Elga)", model: "CPHU Mixed-Bed Polisher", country: "France", priceEur: 280000, priceDisplay: "€280k", efficiency: "Conductivity < 0.055 µS/cm, nuclear grade", leadTimeMonths: 10, trl: 9 },
  ],

  /* ── THERMAL OIL HEATER ── */
  "thermal oil heater": [
    { strategyTag: "bestPrice", manufacturer: "Pirobloc", model: "GFT Series 3 MWth", country: "Spain", priceEur: 180000, priceDisplay: "€180k", efficiency: "88%, up to 350°C", leadTimeMonths: 6, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Thermax", model: "Thermopac 5 MWth Coil-Type", country: "India", priceEur: 350000, priceDisplay: "€350k", efficiency: "92%, up to 350°C, low NOx", leadTimeMonths: 10, trl: 9 },
  ],

  /* ── FIRED HEATER ── */
  "fired heater": [
    { strategyTag: "bestPrice", manufacturer: "Born Inc.", model: "Cabin-Type Process Heater", country: "USA", priceEur: 1100000, priceDisplay: "€1.1M", efficiency: "87% thermal, natural draft", leadTimeMonths: 12, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "ISGEC Heavy Engineering", model: "Reformer Furnace H₂ Service", country: "India", priceEur: 2500000, priceDisplay: "€2.5M", efficiency: "93% with air preheat, ultra-low NOx", leadTimeMonths: 18, trl: 9 },
  ],

  /* ── FLUE GAS COOLER ── */
  "flue gas cooler": [
    { strategyTag: "bestPrice", manufacturer: "HeatMatrix", model: "Polymer Heat Exchanger FGC", country: "Netherlands", priceEur: 110000, priceDisplay: "€110k", efficiency: "Corrosion-proof, flue gas to 100°C", leadTimeMonths: 6, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Alfa Laval", model: "Aalborg Wet FGC", country: "Denmark", priceEur: 320000, priceDisplay: "€320k", efficiency: "Flue gas to 40°C, 15% fuel saving", leadTimeMonths: 10, trl: 9 },
  ],

  /* ── WASTE HEAT RECOVERY ── */
  "waste heat recovery": [
    { strategyTag: "bestPrice", manufacturer: "Cannon Bono Energia", model: "WHRU 15 bar Steam Package", country: "Italy", priceEur: 580000, priceDisplay: "€580k", efficiency: "80% recovery, 15 bar saturated", leadTimeMonths: 10, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Alfa Laval Aalborg", model: "Micro WHRU 40 bar Superheated", country: "Denmark", priceEur: 1500000, priceDisplay: "€1.5M", efficiency: "90% recovery, compact footprint", leadTimeMonths: 14, trl: 9 },
  ],

  /* ── ORC ── */
  "organic rankine cycle": [
    { strategyTag: "bestPrice", manufacturer: "Rank", model: "microORC 50 kWe", country: "Spain", priceEur: 280000, priceDisplay: "€280k", efficiency: "12% net, 90°C+ source", leadTimeMonths: 6, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Enertime", model: "ORCHID 3 MW ORC", country: "France", priceEur: 3800000, priceDisplay: "€3.8M", efficiency: "22% net, R1233zd working fluid", leadTimeMonths: 14, trl: 9 },
  ],

  /* ── REFRIGERATION SYSTEM ── */
  "refrigeration system": [
    { strategyTag: "bestPrice", manufacturer: "Bitzer", model: "ECOLINE+ Screw Chiller 400 kW", country: "Germany", priceEur: 250000, priceDisplay: "€250k", efficiency: "COP 4.3, R717", leadTimeMonths: 5, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Mayekawa", model: "NewTon NH₃/CO₂ Cascade 2 MW", country: "Japan", priceEur: 720000, priceDisplay: "€720k", efficiency: "COP 6.5, natural refrigerants only", leadTimeMonths: 12, trl: 9 },
  ],

  /* ── ESP ── */
  "electrostatic precipitator": [
    { strategyTag: "bestPrice", manufacturer: "Hamon Research-Cottrell", model: "Dry ESP 3-Field", country: "Belgium", priceEur: 780000, priceDisplay: "€780k", efficiency: "99.3% PM removal", leadTimeMonths: 10, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Siemens (Elex)", model: "Wet Tubular ESP", country: "Germany", priceEur: 1600000, priceDisplay: "€1.6M", efficiency: "99.95%, sub-micron, acid mist", leadTimeMonths: 14, trl: 9 },
  ],

  /* ── SCRUBBER ── */
  scrubber: [
    { strategyTag: "bestPrice", manufacturer: "Tri-Mer Corporation", model: "Cloud Chamber Scrubber", country: "USA", priceEur: 300000, priceDisplay: "€300k", efficiency: "94% SOx, sub-micron particles", leadTimeMonths: 7, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "SLY Inc.", model: "Venturi + Packed Tower Combo", country: "USA", priceEur: 850000, priceDisplay: "€850k", efficiency: "99.5% SOx, multi-pollutant", leadTimeMonths: 12, trl: 9 },
  ],

  /* ── CO2 PURIFICATION ── */
  "co2 purification": [
    { strategyTag: "bestPrice", manufacturer: "Pentair (Haffmans)", model: "CO₂ Recovery & Purification Unit", country: "Netherlands", priceEur: 1050000, priceDisplay: "€1.05M", efficiency: "99.8% CO₂, food/beverage grade", leadTimeMonths: 10, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Bright Biomethane", model: "CO₂ Liquefaction & Polish", country: "Netherlands", priceEur: 2200000, priceDisplay: "€2.2M", efficiency: "99.995% CO₂, EOR grade", leadTimeMonths: 14, trl: 9 },
  ],

  /* ── SYNGAS CLEANUP ── */
  "syngas cleanup": [
    { strategyTag: "bestPrice", manufacturer: "Süd-Chemie (Clariant)", model: "ActiSorb Guard Bed System", country: "Germany", priceEur: 380000, priceDisplay: "€380k", efficiency: "H₂S < 0.5 ppm, ZnO sorbent", leadTimeMonths: 6, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "UOP (Honeywell)", model: "Selexol™ Physical Absorption", country: "USA", priceEur: 1500000, priceDisplay: "€1.5M", efficiency: "H₂S < 4 ppm, CO₂ co-removal", leadTimeMonths: 14, trl: 9 },
  ],

  /* ── SULFUR REMOVAL ── */
  "sulfur removal": [
    { strategyTag: "bestPrice", manufacturer: "Chemviron (Calgon Carbon)", model: "Activated Carbon H₂S Bed", country: "Belgium", priceEur: 280000, priceDisplay: "€280k", efficiency: "99.5% H₂S removal, impregnated AC", leadTimeMonths: 5, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Clariant", model: "TwinDeSulf™ Bio-Desulfurization", country: "Switzerland", priceEur: 850000, priceDisplay: "€850k", efficiency: "99.99%, biological, zero chemicals", leadTimeMonths: 12, trl: 9 },
  ],

  /* ── H2S SCAVENGER ── */
  "h2s scavenger": [
    { strategyTag: "bestPrice", manufacturer: "Newpoint Gas", model: "Iron Sponge H₂S Scrubber", country: "USA", priceEur: 35000, priceDisplay: "€35k", efficiency: "Loading 20 lb S/100 lb, low cost", leadTimeMonths: 2, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Chemviron", model: "Impregnated Activated Carbon Bed", country: "Belgium", priceEur: 75000, priceDisplay: "€75k", efficiency: "Loading 45 lb S/100 lb, regenerable", leadTimeMonths: 4, trl: 9 },
  ],

  /* ── AMINE TREATING ── */
  "amine treating": [
    { strategyTag: "bestPrice", manufacturer: "Huntsman", model: "JEFFSOL® Amine Treating Unit", country: "USA", priceEur: 1300000, priceDisplay: "€1.3M", efficiency: "CO₂ < 75 ppm, MDEA", leadTimeMonths: 10, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "BASF", model: "OASE® Blue Amine Process", country: "Germany", priceEur: 2800000, priceDisplay: "€2.8M", efficiency: "CO₂ < 5 ppm, 2.0 GJ/tCO₂, advanced solvent", leadTimeMonths: 16, trl: 9 },
  ],

  /* ── ADSORPTION PURIFICATION ── */
  "adsorption purification": [
    { strategyTag: "bestPrice", manufacturer: "Jacobi Carbons", model: "Granular AC Adsorber 1200 kg", country: "Sweden", priceEur: 55000, priceDisplay: "€55k", efficiency: "VOC > 99%, coconut shell AC", leadTimeMonths: 4, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Linde Engineering", model: "Mole Sieve 5A Deep Dryer + Purifier", country: "Germany", priceEur: 200000, priceDisplay: "€200k", efficiency: "H₂O < 0.5 ppm, CO₂ < 1 ppm", leadTimeMonths: 8, trl: 9 },
  ],

  /* ── DRYER UNIT ── */
  "dryer unit": [
    { strategyTag: "bestPrice", manufacturer: "Parker (Zander)", model: "KEN Series Membrane Dryer", country: "Germany", priceEur: 18000, priceDisplay: "€18k", efficiency: "Dew point -30°C, no power needed", leadTimeMonths: 3, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Donaldson", model: "Ultrapac Smart Desiccant Dryer", country: "USA", priceEur: 72000, priceDisplay: "€72k", efficiency: "Dew point -70°C, energy-saving regen", leadTimeMonths: 6, trl: 9 },
  ],

  /* ── DEOXIDATION ── */
  deoxidation: [
    { strategyTag: "bestPrice", manufacturer: "Süd-Chemie (Clariant)", model: "G-132 CuO DeOx Catalyst Bed", country: "Germany", priceEur: 70000, priceDisplay: "€70k", efficiency: "O₂ < 1 ppm, CuO on alumina", leadTimeMonths: 4, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "BASF", model: "R3-16 Special Pd/Al₂O₃ DeOx", country: "Germany", priceEur: 145000, priceDisplay: "€145k", efficiency: "O₂ < 0.05 ppm, semiconductor grade", leadTimeMonths: 6, trl: 9 },
  ],

  /* ── SOLVENT REGENERATION ── */
  "solvent regeneration": [
    { strategyTag: "bestPrice", manufacturer: "Praj Industries", model: "Heat-Integrated Stripper Package", country: "India", priceEur: 380000, priceDisplay: "€380k", efficiency: "94% recovery, 2.8 GJ/t", leadTimeMonths: 8, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Topsoe", model: "eCOs™ Electrified Regen System", country: "Denmark", priceEur: 1100000, priceDisplay: "€1.1M", efficiency: "99.5% recovery, 1.8 GJ/t, electric heat", leadTimeMonths: 14, trl: 8 },
  ],

  /* ── REVERSE OSMOSIS ── */
  "reverse osmosis": [
    { strategyTag: "bestPrice", manufacturer: "Hydranautics (Nitto)", model: "SWC5 Seawater RO Membrane", country: "Japan", priceEur: 105000, priceDisplay: "€105k", efficiency: "99.8% salt rejection, 40 m³/h", leadTimeMonths: 4, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Pentair X-Flow", model: "Aquaflex UF + RO Integrated", country: "Netherlands", priceEur: 270000, priceDisplay: "€270k", efficiency: "99.9% rejection, 20% energy savings", leadTimeMonths: 8, trl: 9 },
  ],

  /* ── ION EXCHANGE ── */
  "ion exchange": [
    { strategyTag: "bestPrice", manufacturer: "Rohm & Haas (DuPont)", model: "Amberlite™ IR120 Cation IX", country: "USA", priceEur: 55000, priceDisplay: "€55k", efficiency: "< 2 µS/cm, 25 m³/h", leadTimeMonths: 4, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Thermax", model: "Tulsion® T-42 Mixed-Bed IX", country: "India", priceEur: 120000, priceDisplay: "€120k", efficiency: "< 0.1 µS/cm, nuclear grade", leadTimeMonths: 6, trl: 9 },
  ],

  /* ── ULTRAFILTRATION ── */
  ultrafiltration: [
    { strategyTag: "bestPrice", manufacturer: "Koch Membrane Systems", model: "HF Series Hollow Fiber UF", country: "USA", priceEur: 52000, priceDisplay: "€52k", efficiency: "0.03 µm, backwashable, 50 m³/h", leadTimeMonths: 4, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Inge (BASF)", model: "dizzer® XL Multibore UF", country: "Germany", priceEur: 120000, priceDisplay: "€120k", efficiency: "0.02 µm, multi-bore, low fouling", leadTimeMonths: 6, trl: 9 },
  ],

  /* ── ACTIVATED CARBON FILTER ── */
  "activated carbon filter": [
    { strategyTag: "bestPrice", manufacturer: "Evoqua (Xylem)", model: "Westates Carbon Adsorber", country: "USA", priceEur: 25000, priceDisplay: "€25k", efficiency: "Chlorine < 0.01 ppm, 30 m³/h", leadTimeMonths: 3, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Jacobi Carbons", model: "AquaSorb™ CS Pressure Filter", country: "Sweden", priceEur: 55000, priceDisplay: "€55k", efficiency: "COD removal 95%, premium coconut AC", leadTimeMonths: 5, trl: 9 },
  ],

  /* ── WATER SOFTENER ── */
  "water softener": [
    { strategyTag: "bestPrice", manufacturer: "Pentair", model: "Autotrol Performa Industrial Softener", country: "USA", priceEur: 18000, priceDisplay: "€18k", efficiency: "< 1 mg/L hardness, 30 m³/h", leadTimeMonths: 3, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "BWT", model: "Rondomat Duo Industrial Softener", country: "Austria", priceEur: 42000, priceDisplay: "€42k", efficiency: "< 0.1 mg/L, continuous twin-tank", leadTimeMonths: 4, trl: 9 },
  ],

  /* ── COOLING WATER TREATMENT ── */
  "cooling water treatment": [
    { strategyTag: "bestPrice", manufacturer: "Nalco (Ecolab)", model: "3DT TRASAR Cooling Water System", country: "USA", priceEur: 45000, priceDisplay: "€45k", efficiency: "10 CoC, automated chemical dosing", leadTimeMonths: 3, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Suez (Veolia)", model: "InSight™ Digital CW Treatment", country: "France", priceEur: 95000, priceDisplay: "€95k", efficiency: "15 CoC, AI-optimized dosing", leadTimeMonths: 6, trl: 9 },
  ],

  /* ── EFFLUENT NEUTRALIZATION ── */
  "effluent neutralization": [
    { strategyTag: "bestPrice", manufacturer: "Prominent", model: "DULCODOS pH Neutralization Skid", country: "Germany", priceEur: 35000, priceDisplay: "€35k", efficiency: "pH 6–9, dual acid/alkali", leadTimeMonths: 3, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Evoqua (Xylem)", model: "Neutralization + Flocculation Skid", country: "USA", priceEur: 85000, priceDisplay: "€85k", efficiency: "pH 6.5–8.5, metals co-precipitation", leadTimeMonths: 6, trl: 9 },
  ],

  /* ── WASTEWATER TREATMENT ── */
  "wastewater treatment": [
    { strategyTag: "bestPrice", manufacturer: "Aquatech International", model: "Biological MBBR WWT", country: "USA", priceEur: 280000, priceDisplay: "€280k", efficiency: "COD removal 95%, compact", leadTimeMonths: 8, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Veolia", model: "MBBR + MBR Hybrid WWT", country: "France", priceEur: 650000, priceDisplay: "€650k", efficiency: "COD 99%, BOD < 5 mg/L, reuse quality", leadTimeMonths: 12, trl: 9 },
  ],

  /* ── SLUDGE DEWATERING ── */
  "sludge dewatering": [
    { strategyTag: "bestPrice", manufacturer: "ANDRITZ", model: "C-Press Screw Press 10 m³/h", country: "Austria", priceEur: 120000, priceDisplay: "€120k", efficiency: "30% DS, low energy", leadTimeMonths: 6, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Alfa Laval", model: "ALDEC G3 Decanter Centrifuge", country: "Sweden", priceEur: 280000, priceDisplay: "€280k", efficiency: "40% DS, polymer-optimized", leadTimeMonths: 10, trl: 9 },
  ],

  /* ── BRINE CONCENTRATOR ── */
  "brine concentrator": [
    { strategyTag: "bestPrice", manufacturer: "SUEZ (Veolia)", model: "Brine Concentrator BC-100", country: "France", priceEur: 1200000, priceDisplay: "€1.2M", efficiency: "95% recovery, MVR driven", leadTimeMonths: 12, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Saltworks Technologies", model: "SaltMaker EvapX", country: "Canada", priceEur: 2200000, priceDisplay: "€2.2M", efficiency: "99% recovery, ZLD ready", leadTimeMonths: 16, trl: 9 },
  ],

  /* ── EVAPORATOR ── */
  evaporator: [
    { strategyTag: "bestPrice", manufacturer: "GEA", model: "Falling Film Evaporator MVR", country: "Germany", priceEur: 450000, priceDisplay: "€450k", efficiency: "10:1 concentration, 15 kWh/m³ evap.", leadTimeMonths: 8, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Alfa Laval", model: "AlfaFlash Plate Evaporator", country: "Sweden", priceEur: 850000, priceDisplay: "€850k", efficiency: "Triple-effect, 6 kWh/m³ evap.", leadTimeMonths: 12, trl: 9 },
  ],

  /* ── CRYSTALLIZER ── */
  crystallizer: [
    { strategyTag: "bestPrice", manufacturer: "Swenson Technology", model: "DTB Draft-Tube Crystallizer", country: "USA", priceEur: 550000, priceDisplay: "€550k", efficiency: "90% crystal yield, NaCl service", leadTimeMonths: 10, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "GEA", model: "Oslo-Type Forced Circulation", country: "Germany", priceEur: 1200000, priceDisplay: "€1.2M", efficiency: "98% yield, uniform crystal size", leadTimeMonths: 14, trl: 9 },
  ],

  /* ── DAC CONTACTOR ── */
  "dac contactor": [
    { strategyTag: "bestPrice", manufacturer: "Global Thermostat", model: "GT Monolith Contactor Module", country: "USA", priceEur: 1800000, priceDisplay: "€1.8M", efficiency: "500 tCO₂/yr, amine sorbent", leadTimeMonths: 14, trl: 7 },
    { strategyTag: "bestEfficiency", manufacturer: "Carbon Engineering (Oxy)", model: "Air-to-Fuel™ K-OH Contactor", country: "Canada", priceEur: 5500000, priceDisplay: "€5.5M", efficiency: "4000 tCO₂/yr, KOH aqueous", leadTimeMonths: 24, trl: 7 },
  ],

  /* ── DAC REGENERATION ── */
  "dac regeneration": [
    { strategyTag: "bestPrice", manufacturer: "Heirloom Carbon", model: "Limestone Calcination DAC Regen", country: "USA", priceEur: 1500000, priceDisplay: "€1.5M", efficiency: "3 GJ/tCO₂, electric kiln", leadTimeMonths: 14, trl: 6 },
    { strategyTag: "bestEfficiency", manufacturer: "Climeworks", model: "Vacuum-Swing Thermal Regen Unit", country: "Switzerland", priceEur: 4200000, priceDisplay: "€4.2M", efficiency: "1.8 GJ/tCO₂, 100°C low-grade heat", leadTimeMonths: 20, trl: 8 },
  ],

  /* ── DIRECT OCEAN CAPTURE ── */
  "direct ocean capture": [
    { strategyTag: "bestPrice", manufacturer: "Running Tide", model: "Bio-Enhanced Ocean CDR Module", country: "USA", priceEur: 1200000, priceDisplay: "€1.2M", efficiency: "800 tCO₂/yr, kelp + mineralization", leadTimeMonths: 12, trl: 5 },
    { strategyTag: "bestEfficiency", manufacturer: "Planetary Technologies", model: "Ocean Alkalinity Enhancement Unit", country: "Canada", priceEur: 3000000, priceDisplay: "€3M", efficiency: "5000 tCO₂/yr, Mg(OH)₂ addition", leadTimeMonths: 18, trl: 5 },
  ],

  /* ── PYROLYSIS REACTOR ── */
  "pyrolysis reactor": [
    { strategyTag: "bestPrice", manufacturer: "Klean Industries", model: "KleanGas™ Continuous Pyrolysis", country: "Canada", priceEur: 2800000, priceDisplay: "€2.8M", efficiency: "68% oil yield, mixed waste", leadTimeMonths: 14, trl: 7 },
    { strategyTag: "bestEfficiency", manufacturer: "Twence (TorrCoal)", model: "Slow Pyrolysis Biochar Reactor", country: "Netherlands", priceEur: 5500000, priceDisplay: "€5.5M", efficiency: "35% biochar + 35% bio-oil + 30% syngas", leadTimeMonths: 18, trl: 8 },
  ],

  /* ── HTL ── */
  "hydrothermal liquefaction": [
    { strategyTag: "bestPrice", manufacturer: "Genifuel", model: "HTL Pilot 5 bbl/d", country: "USA", priceEur: 4800000, priceDisplay: "€4.8M", efficiency: "42% bio-crude, wet feedstock", leadTimeMonths: 18, trl: 6 },
    { strategyTag: "bestEfficiency", manufacturer: "Aarhus University / SCF Technologies", model: "CatLiq™ Cat-HTL", country: "Denmark", priceEur: 8500000, priceDisplay: "€8.5M", efficiency: "52% bio-crude, heterogeneous catalyst", leadTimeMonths: 22, trl: 6 },
  ],

  /* ── TORREFACTION ── */
  torrefaction: [
    { strategyTag: "bestPrice", manufacturer: "Torrec", model: "Mobile Torrefaction Container 2 tph", country: "Austria", priceEur: 1800000, priceDisplay: "€1.8M", efficiency: "88% energy yield, containerized", leadTimeMonths: 10, trl: 7 },
    { strategyTag: "bestEfficiency", manufacturer: "Thermya (CNIM)", model: "TORSPYD™ 10 tph", country: "France", priceEur: 4800000, priceDisplay: "€4.8M", efficiency: "96% energy yield, integrated pelletization", leadTimeMonths: 16, trl: 8 },
  ],

  /* ── BIOMASS COMBUSTION ── */
  "biomass combustion": [
    { strategyTag: "bestPrice", manufacturer: "Justsen Energiteknik", model: "Stoker-Fired Boiler 5 MWth", country: "Denmark", priceEur: 2800000, priceDisplay: "€2.8M", efficiency: "86%, straw/wood chips", leadTimeMonths: 10, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "KPA Unicon", model: "BFB Boiler 50 MWth", country: "Finland", priceEur: 8500000, priceDisplay: "€8.5M", efficiency: "93%, multi-fuel, ultra-low emissions", leadTimeMonths: 18, trl: 9 },
  ],

  /* ── ANAEROBIC DIGESTER ── */
  "anaerobic digester": [
    { strategyTag: "bestPrice", manufacturer: "Agrikomp", model: "Complete Mix CSTR 3000 m³", country: "Germany", priceEur: 950000, priceDisplay: "€950k", efficiency: "58% VS destruction, mesophilic", leadTimeMonths: 8, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "EISENMANN (Dürr)", model: "Dry Fermentation Garage System", country: "Germany", priceEur: 2200000, priceDisplay: "€2.2M", efficiency: "72% VS, high-solids batch", leadTimeMonths: 12, trl: 9 },
  ],

  /* ── BIOGAS UPGRADING ── */
  "biogas upgrading": [
    { strategyTag: "bestPrice", manufacturer: "DMT Environmental", model: "Carborex® PWS Water Scrubber", country: "Netherlands", priceEur: 320000, priceDisplay: "€320k", efficiency: "96% CH₄, no chemicals", leadTimeMonths: 6, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Malmberg", model: "COMPACT Amine Biogas Upgrader", country: "Sweden", priceEur: 580000, priceDisplay: "€580k", efficiency: "99.8% CH₄, 0.1% methane slip", leadTimeMonths: 8, trl: 9 },
  ],

  /* ── WATER GAS SHIFT ── */
  "water gas shift": [
    { strategyTag: "bestPrice", manufacturer: "BASF", model: "K3-110 Fe/Cr HTS Catalyst Reactor", country: "Germany", priceEur: 1050000, priceDisplay: "€1.05M", efficiency: "CO conversion 94%", leadTimeMonths: 10, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Clariant", model: "ShiftMax® 217 Low-Temp Reactor", country: "Switzerland", priceEur: 2500000, priceDisplay: "€2.5M", efficiency: "CO conversion 99.5%, Cu/ZnO", leadTimeMonths: 14, trl: 9 },
  ],

  /* ── RWGS ── */
  "reverse water gas shift": [
    { strategyTag: "bestPrice", manufacturer: "Haldor Topsoe", model: "Bayonet RWGS Reactor", country: "Denmark", priceEur: 1800000, priceDisplay: "€1.8M", efficiency: "CO₂ conversion 58%, conventional heating", leadTimeMonths: 16, trl: 7 },
    { strategyTag: "bestEfficiency", manufacturer: "Johnson Matthey", model: "HiFUEL® eRWGS Module", country: "UK", priceEur: 3200000, priceDisplay: "€3.2M", efficiency: "CO₂ conversion 72%, electric heating", leadTimeMonths: 18, trl: 7 },
  ],

  /* ── METHANATION ── */
  "methanation reactor": [
    { strategyTag: "bestPrice", manufacturer: "MAN Energy Solutions", model: "Adiabatic Methanation 2-Stage", country: "Germany", priceEur: 2000000, priceDisplay: "€2M", efficiency: "98% CH₃, Ni catalyst", leadTimeMonths: 12, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Ineratec", model: "Microstructured Methanation Reactor", country: "Germany", priceEur: 3200000, priceDisplay: "€3.2M", efficiency: "99.8% CH₄, isothermal, compact", leadTimeMonths: 16, trl: 7 },
  ],

  /* ── FISCHER-TROPSCH ── */
  "fischer tropsch": [
    { strategyTag: "bestPrice", manufacturer: "Sasol", model: "Slurry-Phase FT Reactor 500 bbl/d", country: "South Africa", priceEur: 12000000, priceDisplay: "€12M", efficiency: "CO conversion 92%, Fe catalyst", leadTimeMonths: 24, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "bp (Infinia)", model: "Microchannel FT Reactor", country: "UK", priceEur: 9500000, priceDisplay: "€9.5M", efficiency: "CO conversion 93%, enhanced heat transfer", leadTimeMonths: 20, trl: 7 },
  ],

  /* ── METHANOL SYNTHESIS ── */
  "methanol synthesis": [
    { strategyTag: "bestPrice", manufacturer: "Casale", model: "Isothermal MeOH Reactor 200 tpd", country: "Switzerland", priceEur: 3000000, priceDisplay: "€3M", efficiency: "Per-pass 42%, boiling water reactor", leadTimeMonths: 16, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Air Liquide Engineering", model: "Lurgi MeOH Reactor 1000 tpd", country: "France", priceEur: 7500000, priceDisplay: "€7.5M", efficiency: "Per-pass 55%, tube-cooled + gas-cooled", leadTimeMonths: 22, trl: 9 },
  ],

  /* ── DME SYNTHESIS ── */
  "dme synthesis": [
    { strategyTag: "bestPrice", manufacturer: "Oberon Fuels", model: "Modular rDME Reactor 10 tpd", country: "USA", priceEur: 2200000, priceDisplay: "€2.2M", efficiency: "75% DME selectivity, containerized", leadTimeMonths: 12, trl: 8 },
    { strategyTag: "bestEfficiency", manufacturer: "Eurochem Engineering", model: "Direct CO₂-to-DME Reactor", country: "Italy", priceEur: 4500000, priceDisplay: "€4.5M", efficiency: "88% selectivity, bifunctional cat.", leadTimeMonths: 18, trl: 7 },
  ],

  /* ── AMMONIA SYNTHESIS ── */
  "ammonia synthesis": [
    { strategyTag: "bestPrice", manufacturer: "Casale", model: "Axial-Radial NH₃ Converter 300 tpd", country: "Switzerland", priceEur: 3800000, priceDisplay: "€3.8M", efficiency: "Per-pass 20%, wüstite catalyst", leadTimeMonths: 16, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Johnson Matthey", model: "KATALCO™ 74-1 Converter", country: "UK", priceEur: 7500000, priceDisplay: "€7.5M", efficiency: "Per-pass 26%, inter-bed heat recovery", leadTimeMonths: 22, trl: 9 },
  ],

  /* ── HYDROTREATER ── */
  hydrotreater: [
    { strategyTag: "bestPrice", manufacturer: "Haldor Topsoe", model: "TK-558 HDS Reactor", country: "Denmark", priceEur: 2800000, priceDisplay: "€2.8M", efficiency: "S < 15 ppm, NiMo catalyst", leadTimeMonths: 14, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Albemarle", model: "Nebula® Ultra-Deep HDS", country: "Netherlands", priceEur: 5500000, priceDisplay: "€5.5M", efficiency: "S < 0.5 ppm, bulk metal catalyst", leadTimeMonths: 20, trl: 9 },
  ],

  /* ── HYDROCRACKER ── */
  hydrocracker: [
    { strategyTag: "bestPrice", manufacturer: "Shell Catalysts & Technologies", model: "ISOALL™ HC Reactor", country: "Netherlands", priceEur: 9000000, priceDisplay: "€9M", efficiency: "96% conversion, amorphous cat.", leadTimeMonths: 22, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Topsoe", model: "TK-928 Dewaxing/Hydrocracking", country: "Denmark", priceEur: 13000000, priceDisplay: "€13M", efficiency: "99% conversion, maximum middle distillate", leadTimeMonths: 26, trl: 9 },
  ],

  /* ── HYDROISOMERIZATION ── */
  hydroisomerization: [
    { strategyTag: "bestPrice", manufacturer: "Shell", model: "SMDW™ Selective Dewaxing", country: "Netherlands", priceEur: 3200000, priceDisplay: "€3.2M", efficiency: "Pour point < -25°C, Pt/zeolite", leadTimeMonths: 14, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Chevron Lummus Global", model: "ISODEWAXING™ Reactor", country: "USA", priceEur: 5500000, priceDisplay: "€5.5M", efficiency: "Pour point < -40°C, high VI base oil", leadTimeMonths: 18, trl: 9 },
  ],

  /* ── ALKYLATION ── */
  "alkylation reactor": [
    { strategyTag: "bestPrice", manufacturer: "CEPSA (Detal™)", model: "LAB Alkylation Reactor", country: "Spain", priceEur: 5800000, priceDisplay: "€5.8M", efficiency: "RON 95, HF acid", leadTimeMonths: 18, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "CB&I (McDermott)", model: "CDAlky™ Solid Acid Alkylation", country: "USA", priceEur: 11000000, priceDisplay: "€11M", efficiency: "RON 97, no HF/H₂SO₄, zeolite", leadTimeMonths: 24, trl: 8 },
  ],

  /* ── POLYMERIZATION ── */
  "polymerization reactor": [
    { strategyTag: "bestPrice", manufacturer: "LyondellBasell", model: "Spherizone™ MZCR Reactor", country: "Netherlands", priceEur: 8500000, priceDisplay: "€8.5M", efficiency: "Multi-zone, broad MWD", leadTimeMonths: 22, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Borealis", model: "Borstar® 3G PE Reactor", country: "Austria", priceEur: 15000000, priceDisplay: "€15M", efficiency: "Tri-modal PE, superior mechanical properties", leadTimeMonths: 28, trl: 9 },
  ],

  /* ── LOADING UNITS ── */
  "hydrogen tube trailer": [
    { strategyTag: "bestPrice", manufacturer: "Luxfer Gas Cylinders", model: "G-Stor H₂ Tube Trailer 500 bar", country: "UK", priceEur: 650000, priceDisplay: "€650k", efficiency: "1100 kg H₂ per trailer, Type I", leadTimeMonths: 8, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Wystrach", model: "WyBundle® Mobile H₂ Storage 500 bar", country: "Germany", priceEur: 1200000, priceDisplay: "€1.2M", efficiency: "1500 kg H₂, Type IV composite", leadTimeMonths: 12, trl: 9 },
  ],

  "tank truck loading": [
    { strategyTag: "bestPrice", manufacturer: "Emco Wheaton", model: "Marine Loading Arm Tank Truck", country: "USA", priceEur: 85000, priceDisplay: "€85k", efficiency: "400 m³/h, bottom loading, ATEX", leadTimeMonths: 5, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Kanon Loading Equipment", model: "Dual-Arm Truck Loading System", country: "Netherlands", priceEur: 180000, priceDisplay: "€180k", efficiency: "600 m³/h, VRU integrated", leadTimeMonths: 8, trl: 9 },
  ],

  "rail loading": [
    { strategyTag: "bestPrice", manufacturer: "Emco Wheaton", model: "Rail Car Top Loading Arm", country: "USA", priceEur: 120000, priceDisplay: "€120k", efficiency: "500 m³/h, 3\" to 6\", ATEX", leadTimeMonths: 6, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "SafeRack", model: "Automated Rail Loading Gantry", country: "USA", priceEur: 350000, priceDisplay: "€350k", efficiency: "800 m³/h, automated positioning", leadTimeMonths: 10, trl: 9 },
  ],

  "ship loading": [
    { strategyTag: "bestPrice", manufacturer: "Kanon Loading Equipment", model: "Marine Loading Arm MLA-C", country: "Netherlands", priceEur: 280000, priceDisplay: "€280k", efficiency: "2000 m³/h, 16\", OCIMF compliant", leadTimeMonths: 8, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "SVT (TechnipFMC)", model: "LNG/LH₂ Marine Loading Arm", country: "Norway", priceEur: 850000, priceDisplay: "€850k", efficiency: "Cryogenic service, QCDC, powered ERS", leadTimeMonths: 14, trl: 9 },
  ],

  /* ── CO2 LIQUEFACTION ── */
  "co2 liquefaction": [
    { strategyTag: "bestPrice", manufacturer: "MAN Energy Solutions", model: "CO₂ Liquefaction Package 15 bar", country: "Germany", priceEur: 1500000, priceDisplay: "€1.5M", efficiency: "0.08 kWh/kg CO₂, intermediate pressure", leadTimeMonths: 10, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Wärtsilä (Hamworthy)", model: "CO₂ Reliq + Liquefaction Train", country: "Norway", priceEur: 3200000, priceDisplay: "€3.2M", efficiency: "0.06 kWh/kg CO₂, food/EOR grade", leadTimeMonths: 14, trl: 9 },
  ],

  /* ── HYDROGEN LIQUEFACTION ── */
  "hydrogen liquefaction": [
    { strategyTag: "bestPrice", manufacturer: "Chart Industries", model: "Compact H₂ Liquefier 5 tpd", country: "USA", priceEur: 9000000, priceDisplay: "€9M", efficiency: "10 kWh/kg LH₂", leadTimeMonths: 16, trl: 8 },
    { strategyTag: "bestEfficiency", manufacturer: "Air Liquide", model: "Turbo-Brayton LH₂ 30 tpd", country: "France", priceEur: 22000000, priceDisplay: "€22M", efficiency: "6 kWh/kg LH₂, world-scale", leadTimeMonths: 24, trl: 9 },
  ],

  /* ── NATURAL GAS LIQUEFACTION ── */
  "natural gas liquefaction": [
    { strategyTag: "bestPrice", manufacturer: "Black & Veatch (PRICO®)", model: "Single Mixed Ref LNG 200 tpd", country: "USA", priceEur: 15000000, priceDisplay: "€15M", efficiency: "0.33 kWh/kg LNG", leadTimeMonths: 18, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Shell", model: "DMR (Dual Mixed Refrigerant) LNG", country: "Netherlands", priceEur: 80000000, priceDisplay: "€80M", efficiency: "0.26 kWh/kg LNG, mega-train", leadTimeMonths: 36, trl: 9 },
  ],

  /* ── CATALYTIC OXIDIZER ── */
  "catalytic oxidizer": [
    { strategyTag: "bestPrice", manufacturer: "Ship & Shore Environmental", model: "Catalytic Thermal Oxidizer", country: "USA", priceEur: 200000, priceDisplay: "€200k", efficiency: "99% VOC, 90% heat recovery", leadTimeMonths: 6, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Condorchem Envitech", model: "Regenerative Catalytic Oxidizer", country: "Spain", priceEur: 380000, priceDisplay: "€380k", efficiency: "99.9% DRE, 97% heat recovery", leadTimeMonths: 8, trl: 9 },
  ],

  /* ── VENT STACK ── */
  "vent stack": [
    { strategyTag: "bestPrice", manufacturer: "Boardman (BSDI)", model: "Self-Supporting Stack 25 m", country: "USA", priceEur: 72000, priceDisplay: "€72k", efficiency: "CS lined, wind-code designed", leadTimeMonths: 4, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Hamon Deltak", model: "Alloy-Lined Vent Stack 50 m", country: "Belgium", priceEur: 160000, priceDisplay: "€160k", efficiency: "SS316 lined, corrosion resistant", leadTimeMonths: 8, trl: 9 },
  ],

  /* ── BLOWDOWN SYSTEM ── */
  "blowdown system": [
    { strategyTag: "bestPrice", manufacturer: "ERGIL", model: "Atmospheric Blowdown Tank", country: "Turkey", priceEur: 150000, priceDisplay: "€150k", efficiency: "API 521, ASME VIII", leadTimeMonths: 5, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "PEERLESS Mfg.", model: "Closed Drain/Blowdown System", country: "USA", priceEur: 420000, priceDisplay: "€420k", efficiency: "Zero-emission, BTEX recovery", leadTimeMonths: 10, trl: 9 },
  ],

  /* ── INERTING / N₂ BLANKETING ── */
  "inerting system": [
    { strategyTag: "bestPrice", manufacturer: "Witt-Gasetechnik", model: "N₂ Blanketing Control Panel", country: "Germany", priceEur: 12000, priceDisplay: "€12k", efficiency: "±3 mbar, tank breathing control", leadTimeMonths: 3, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Emerson (Asco)", model: "Redundant N₂ Purge & Blanket", country: "USA", priceEur: 32000, priceDisplay: "€32k", efficiency: "SIL 2, auto-replenish, O₂ monitoring", leadTimeMonths: 5, trl: 9 },
  ],

  /* ── GAS DETECTION ── */
  "gas detection system": [
    { strategyTag: "bestPrice", manufacturer: "Crowcon", model: "XGard IQ Fixed Gas Detector", country: "UK", priceEur: 1500, priceDisplay: "€1,500", efficiency: "H₂/CO/LEL, HART, SIL 2", leadTimeMonths: 2, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Emerson (Rosemount)", model: "925FG Flame & Gas Detector", country: "USA", priceEur: 8500, priceDisplay: "€8,500", efficiency: "Multi-spectrum IR+UV, 60 m range", leadTimeMonths: 5, trl: 9 },
  ],

  /* ── FIRE SUPPRESSION ── */
  "fire suppression": [
    { strategyTag: "bestPrice", manufacturer: "Reliable Automatic Sprinkler", model: "Deluge System F1FR-56", country: "USA", priceEur: 85000, priceDisplay: "€85k", efficiency: "NFPA 15, 600 L/min/m²", leadTimeMonths: 4, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Marioff (Carrier)", model: "HI-FOG® Water Mist", country: "Finland", priceEur: 300000, priceDisplay: "€300k", efficiency: "85% less water, IMO/FM approved", leadTimeMonths: 10, trl: 9 },
  ],

  /* ── BIOMASS RECEIVING ── */
  "biomass receiving": [
    { strategyTag: "bestPrice", manufacturer: "Keith Manufacturing", model: "Walking Floor Receiving Pit", country: "USA", priceEur: 280000, priceDisplay: "€280k", efficiency: "150 t/h, truck tipping", leadTimeMonths: 7, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Siwertell (Bruks)", model: "Ship Unloader + Enclosed Conveyor", country: "Sweden", priceEur: 1200000, priceDisplay: "€1.2M", efficiency: "800 t/h, dust-free, port terminal", leadTimeMonths: 14, trl: 9 },
  ],

  /* ── BIOMASS SILO ── */
  "biomass storage silo": [
    { strategyTag: "bestPrice", manufacturer: "Symaga", model: "Flat-Bottom Galv. Steel Silo 3000 m³", country: "Spain", priceEur: 220000, priceDisplay: "€220k", efficiency: "Aeration floor, moisture monitoring", leadTimeMonths: 6, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "FRAME Port Equipment", model: "Enclosed Biomass Dome 8000 m³", country: "Netherlands", priceEur: 850000, priceDisplay: "€850k", efficiency: "O₂/CO/T monitoring, fire suppression", leadTimeMonths: 14, trl: 9 },
  ],

  /* ── DRY STORAGE BUNKER ── */
  "dry storage bunker": [
    { strategyTag: "bestPrice", manufacturer: "Van Beek", model: "Push-Floor Bunker 150 m³", country: "Netherlands", priceEur: 95000, priceDisplay: "€95k", efficiency: "Hydraulic push, 40 t/h", leadTimeMonths: 5, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Stela Laxhuber", model: "Covered Dry Bunker + Dryer 400 m³", country: "Germany", priceEur: 320000, priceDisplay: "€320k", efficiency: "Integrated drying, 10% MC output", leadTimeMonths: 10, trl: 9 },
  ],

  /* ── BIOMASS SLURRY TANK ── */
  "biomass slurry tank": [
    { strategyTag: "bestPrice", manufacturer: "Landia", model: "GasMix Slurry Tank 600 m³", country: "Denmark", priceEur: 75000, priceDisplay: "€75k", efficiency: "Submersible mixer, 12% DM", leadTimeMonths: 5, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Paques (Paqell)", model: "Stainless Heated Slurry Vessel 1200 m³", country: "Netherlands", priceEur: 200000, priceDisplay: "€200k", efficiency: "SS316, 55°C thermophilic, 22% DM", leadTimeMonths: 10, trl: 9 },
  ],

  /* ── FEEDSTOCK BLENDING ── */
  "feedstock blending": [
    { strategyTag: "bestPrice", manufacturer: "Wynveen International", model: "Multi-Component Paddle Mixer", country: "Netherlands", priceEur: 95000, priceDisplay: "€95k", efficiency: "±3% blend, 15 tph, 4 hoppers", leadTimeMonths: 5, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Eirich", model: "RV-Series Intensive Mixer", country: "Germany", priceEur: 320000, priceDisplay: "€320k", efficiency: "±0.3%, residence time 20s, variable speed", leadTimeMonths: 10, trl: 9 },
  ],

  /* ── GAS MIXER ── */
  "gas mixer": [
    { strategyTag: "bestPrice", manufacturer: "Mélangeur (Elster)", model: "Static Mixer SM-500", country: "Germany", priceEur: 6500, priceDisplay: "€6,500", efficiency: "±2%, 2-gas, up to 100 Nm³/h", leadTimeMonths: 2, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Brooks Instrument", model: "GF Series Mass Flow Blender", country: "USA", priceEur: 32000, priceDisplay: "€32k", efficiency: "±0.1%, 4-gas, thermal MFC", leadTimeMonths: 6, trl: 9 },
  ],

  /* ── LIQUID MIXER ── */
  "liquid mixer": [
    { strategyTag: "bestPrice", manufacturer: "Chemineer (NOV)", model: "HT Hydrofoil Impeller 5 m³", country: "USA", priceEur: 18000, priceDisplay: "€18k", efficiency: "0.25 kW/m³, top-entry", leadTimeMonths: 4, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "SUMA Rührtechnik", model: "Optimix Side-Entry Mixer", country: "Germany", priceEur: 52000, priceDisplay: "€52k", efficiency: "0.08 kW/m³, large tank, low shear", leadTimeMonths: 6, trl: 9 },
  ],

  /* ── SCREW CONVEYOR ── */
  "screw conveyor": [
    { strategyTag: "bestPrice", manufacturer: "Continental Conveyor", model: "Tubular Screw 12 m, 40 tph", country: "USA", priceEur: 10000, priceDisplay: "€10k", efficiency: "CEMA class, carbon steel", leadTimeMonths: 3, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Flexicon", model: "Flexible Screw Conveyor SS316", country: "USA", priceEur: 35000, priceDisplay: "€35k", efficiency: "±1% dosing, enclosed, dust-free", leadTimeMonths: 5, trl: 9 },
  ],

  /* ── BELT CONVEYOR ── */
  "belt conveyor": [
    { strategyTag: "bestPrice", manufacturer: "Fenner Dunlop", model: "Steelcord Belt 1000 mm, 1000 tph", country: "UK", priceEur: 72000, priceDisplay: "€72k", efficiency: "150 m, troughed, fire retardant", leadTimeMonths: 5, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "ThyssenKrupp Industrial Solutions", model: "Energy-Efficient Overland Conveyor", country: "Germany", priceEur: 250000, priceDisplay: "€250k", efficiency: "2500 tph, regenerative drive", leadTimeMonths: 12, trl: 9 },
  ],

  /* ── BUCKET ELEVATOR ── */
  "bucket elevator": [
    { strategyTag: "bestPrice", manufacturer: "Tapco Inc.", model: "Heavy-Duty Bucket Elevator 20 m", country: "USA", priceEur: 38000, priceDisplay: "€38k", efficiency: "150 tph, ATEX, chain drive", leadTimeMonths: 4, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Schrage Conveying Systems", model: "Tubular Chain Elevator 50 m", country: "Germany", priceEur: 130000, priceDisplay: "€130k", efficiency: "400 tph, enclosed, gentle handling", leadTimeMonths: 8, trl: 9 },
  ],

  /* ── SIZE REDUCTION ── */
  "size reduction mill": [
    { strategyTag: "bestPrice", manufacturer: "Bliss Industries", model: "Eliminator Hammer Mill 15 tph", country: "USA", priceEur: 95000, priceDisplay: "€95k", efficiency: "Particle < 12 mm, screen change <5 min", leadTimeMonths: 5, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Hosokawa Alpine", model: "Contraplex Pin Mill", country: "Germany", priceEur: 250000, priceDisplay: "€250k", efficiency: "Particle < 1 mm, ultra-fine, classifier", leadTimeMonths: 10, trl: 9 },
  ],

  /* ── SHREDDER ── */
  shredder: [
    { strategyTag: "bestPrice", manufacturer: "UNTHA", model: "RS40 4-Shaft Shredder", country: "Austria", priceEur: 130000, priceDisplay: "€130k", efficiency: "25 tph, output < 60 mm", leadTimeMonths: 5, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Lindner Recyclingtech", model: "Komet 2800 HP Shredder", country: "Austria", priceEur: 320000, priceDisplay: "€320k", efficiency: "50 tph, output < 30 mm, variable speed", leadTimeMonths: 8, trl: 9 },
  ],

  /* ── CHIP SCREEN ── */
  "chip screen": [
    { strategyTag: "bestPrice", manufacturer: "West Salem Machinery", model: "Disc Screen 20 tph", country: "USA", priceEur: 55000, priceDisplay: "€55k", efficiency: "3 fractions, 2–50 mm cuts", leadTimeMonths: 4, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "BRUKS Siwertell", model: "Multi-Deck Vibrating Screen", country: "Sweden", priceEur: 140000, priceDisplay: "€140k", efficiency: "5 fractions, high throughput", leadTimeMonths: 8, trl: 9 },
  ],

  /* ── MAGNETIC SEPARATOR ── */
  "magnetic separator": [
    { strategyTag: "bestPrice", manufacturer: "Eriez", model: "SE Suspended Electromagnet", country: "USA", priceEur: 18000, priceDisplay: "€18k", efficiency: "Belt-over, ferrous removal, ATEX", leadTimeMonths: 3, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Bunting (Redditch)", model: "Eddy Current + Overband Combo", country: "UK", priceEur: 55000, priceDisplay: "€55k", efficiency: "Ferrous + non-ferrous, 99.9% separation", leadTimeMonths: 6, trl: 9 },
  ],

  /* ── SOLIDS DRYER ── */
  "solids dryer": [
    { strategyTag: "bestPrice", manufacturer: "Bühler", model: "OTW Belt Dryer 10 tph", country: "Switzerland", priceEur: 280000, priceDisplay: "€280k", efficiency: "Output MC < 10%, low temp, biomass", leadTimeMonths: 8, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Andritz (Gouda)", model: "Paddle Dryer, Indirect Heat", country: "Austria", priceEur: 550000, priceDisplay: "€550k", efficiency: "Output MC < 5%, closed loop, low emissions", leadTimeMonths: 12, trl: 9 },
  ],

  /* ── PELLETIZER ── */
  pelletizer: [
    { strategyTag: "bestPrice", manufacturer: "CPM (California Pellet Mill)", model: "7900 Series Ring Die 10 tph", country: "USA", priceEur: 180000, priceDisplay: "€180k", efficiency: "6-8 mm pellets, 15 kWh/t", leadTimeMonths: 6, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Andritz", model: "LM26 Flat Die Pellet Mill 15 tph", country: "Austria", priceEur: 350000, priceDisplay: "€350k", efficiency: "6 mm, 12 kWh/t, auto die adjust", leadTimeMonths: 10, trl: 9 },
  ],

  /* ── BRIQUETTER ── */
  briquetter: [
    { strategyTag: "bestPrice", manufacturer: "RUF Maschinenbau", model: "RUF 1500 Hydraulic Briquetter", country: "Germany", priceEur: 95000, priceDisplay: "€95k", efficiency: "1.5 t/h, 2500 bar, no binder", leadTimeMonths: 5, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Köppern", model: "Roller Press Briquetting System", country: "Germany", priceEur: 320000, priceDisplay: "€320k", efficiency: "10 t/h, pillow shape, high density", leadTimeMonths: 10, trl: 9 },
  ],

  /* ── FLASH SEPARATOR ── */
  "flash separator": [
    { strategyTag: "bestPrice", manufacturer: "Frames Group", model: "2-Phase Flash Drum", country: "Netherlands", priceEur: 85000, priceDisplay: "€85k", efficiency: "ASME VIII, mesh pad demister", leadTimeMonths: 5, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Exterran (Enerflex)", model: "3-Phase Test Separator", country: "USA", priceEur: 220000, priceDisplay: "€220k", efficiency: "Oil/gas/water, coalescer internals", leadTimeMonths: 10, trl: 9 },
  ],

  /* ── EXPANDER ── */
  expander: [
    { strategyTag: "bestPrice", manufacturer: "Atlas Copco", model: "Turbo Expander TE-1000", country: "Belgium", priceEur: 450000, priceDisplay: "€450k", efficiency: "88% isentropic, power recovery", leadTimeMonths: 8, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Cryostar (Linde)", model: "Cryogenic Turbo-Expander", country: "France", priceEur: 1200000, priceDisplay: "€1.2M", efficiency: "92% isentropic, LNG/LH₂ service", leadTimeMonths: 14, trl: 9 },
  ],

  /* ── VFD DRIVE ── */
  "vfd drive": [
    { strategyTag: "bestPrice", manufacturer: "Schneider Electric", model: "Altivar Process ATV600 250 kW", country: "France", priceEur: 12000, priceDisplay: "€12k", efficiency: "98%, sensorless vector, HART", leadTimeMonths: 3, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "ABB", model: "ACS880 Industrial Drive 500 kW", country: "Finland", priceEur: 35000, priceDisplay: "€35k", efficiency: "98.5%, DTC, STO SIL 3", leadTimeMonths: 5, trl: 9 },
  ],

  /* ── FIREWATER PUMP ── */
  "firewater pump": [
    { strategyTag: "bestPrice", manufacturer: "Xylem (AC Fire Pump)", model: "8100 Series Diesel Fire Pump 1500 GPM", country: "USA", priceEur: 65000, priceDisplay: "€65k", efficiency: "NFPA 20, UL/FM listed", leadTimeMonths: 5, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "SPP Pumps", model: "Electric Fire Pump 2500 GPM", country: "UK", priceEur: 120000, priceDisplay: "€120k", efficiency: "NFPA 20, 85% hydraulic eff.", leadTimeMonths: 8, trl: 9 },
  ],

  /* ── OIL WATER SEPARATOR ── */
  "oil water separator": [
    { strategyTag: "bestPrice", manufacturer: "Clarus Environmental", model: "CPI Oil/Water Separator", country: "USA", priceEur: 35000, priceDisplay: "€35k", efficiency: "< 10 ppm oil in water, gravity", leadTimeMonths: 4, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Veolia (Technomarine)", model: "Cyclotech Hydrocyclone OWS", country: "France", priceEur: 95000, priceDisplay: "€95k", efficiency: "< 5 ppm, no moving parts, compact", leadTimeMonths: 6, trl: 9 },
  ],

  /* ── COOLING TOWER MAKEUP WATER ── */
  "cooling tower makeup": [
    { strategyTag: "bestPrice", manufacturer: "Nalco (Ecolab)", model: "Integrated MU Water Treatment", country: "USA", priceEur: 55000, priceDisplay: "€55k", efficiency: "Softening + dosing + monitoring", leadTimeMonths: 4, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "Veolia", model: "Hydrex™ Smart MU System", country: "France", priceEur: 120000, priceDisplay: "€120k", efficiency: "AI-optimized, 20% water savings", leadTimeMonths: 6, trl: 9 },
  ],

  /* ── FLUE GAS BLOWER ── */
  "flue gas blower": [
    { strategyTag: "bestPrice", manufacturer: "Howden", model: "Axial Fan FG-Series 500 kW", country: "UK", priceEur: 120000, priceDisplay: "€120k", efficiency: "84%, variable pitch, 200°C", leadTimeMonths: 6, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "TLT-Turbo", model: "Radial FG Fan ZAF Series", country: "Germany", priceEur: 280000, priceDisplay: "€280k", efficiency: "88%, backward-curved, VFD", leadTimeMonths: 10, trl: 9 },
  ],

  /* ── MERCURY REMOVAL ── */
  "mercury removal": [
    { strategyTag: "bestPrice", manufacturer: "Johnson Matthey", model: "PURASPEC™ 2020 Hg Adsorbent", country: "UK", priceEur: 120000, priceDisplay: "€120k", efficiency: "Hg < 0.01 µg/Nm³, sulfur-impregnated AC", leadTimeMonths: 5, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "BASF", model: "Sorbead® Hg Guard Bed", country: "Germany", priceEur: 250000, priceDisplay: "€250k", efficiency: "Hg < 0.001 µg/Nm³, dual-stage", leadTimeMonths: 8, trl: 9 },
  ],

  /* ── FEEDER HOPPER ── */
  "feeder hopper": [
    { strategyTag: "bestPrice", manufacturer: "Schenck Process", model: "MULTIDOS® Weighfeeder", country: "Germany", priceEur: 28000, priceDisplay: "€28k", efficiency: "±0.5%, 50 tph, belt-type", leadTimeMonths: 4, trl: 9 },
    { strategyTag: "bestEfficiency", manufacturer: "K-Tron (Coperion)", model: "K-ML-D5-KT35 Loss-in-Weight", country: "Switzerland", priceEur: 65000, priceDisplay: "€65k", efficiency: "±0.1%, gravimetric, twin screw", leadTimeMonths: 6, trl: 9 },
  ],
};
