/**
 * EquipmentDetailBody — Shared rich detail panel used by:
 *   - EquipmentDetailDrawer (Supplier Database)
 *   - SupplierPickerDialog detail view (Browse Suppliers from canvas / Procurement)
 * Guarantees both views show the exact same data.
 */
import { Badge } from "@/components/ui/Badge";
import { Separator } from "@/components/ui/separator";
import {
  Factory, MapPin, Clock, Beaker, DollarSign, Zap, Droplets,
  ShieldCheck, Gauge, Fuel, ThermometerSun, Scale, Package,
  Truck, Settings, CheckCircle2, XCircle,
} from "lucide-react";

export interface EquipmentEntry {
  category: string;
  strategy: string; // strategy KEY: bestPrice | bestEfficiency | economiesOfScale
  pricingUnit: string;
  option: {
    manufacturer: string;
    model: string;
    country: string;
    priceEur: number;
    priceDisplay: string;
    efficiency: string;
    scaleThreshold?: string;
    leadTimeMonths: number;
    trl: number;
  };
}

const strategyLabels: Record<string, { label: string; cls: string }> = {
  bestPrice: { label: "Best Price", cls: "bg-success/10 text-success border-success/20" },
  bestEfficiency: { label: "Best Efficiency", cls: "bg-primary/10 text-primary border-primary/20" },
  economiesOfScale: { label: "Economies of Scale", cls: "bg-warning/10 text-warning border-warning/20" },
};

export function deriveSpecs(entry: EquipmentEntry) {
  const cat = entry.category.toLowerCase();
  const price = entry.option.priceEur;
  const isElectrolyzer = cat.includes("electrolyz");
  const isCompressor = cat.includes("compressor");
  const isPump = cat.includes("pump");
  const isReformer = cat.includes("reform");
  const isReactor = cat.includes("reactor") || cat.includes("synthesis");
  const isHeatExchanger = cat.includes("heat exchang");
  const isTank = cat.includes("tank") || cat.includes("storage");
  const isBoiler = cat.includes("boiler") || cat.includes("hrsg");
  const isTurbine = cat.includes("turbine") || cat.includes("rankine");
  const isFuelCell = cat.includes("fuel cell");
  const isDesalination = cat.includes("desalin");
  const isDac = cat.includes("direct air");
  const isCo2 = cat.includes("co₂") || cat.includes("co2");
  const isPurif = cat.includes("purif") || cat.includes("psa");
  const isWaterTreat = cat.includes("water treat");
  const isCooling = cat.includes("cooling");
  const isDigester = cat.includes("digest");
  const isPyrolysis = cat.includes("pyrolysis");
  const isSeparator = cat.includes("separator");
  const isValve = cat.includes("valve");

  let electricity = "Process-dependent, see datasheet";
  if (isElectrolyzer) electricity = "4.3–5.5 kWh/Nm³ H₂";
  else if (isCompressor) electricity = "0.8–1.5 kWh/kg H₂";
  else if (isPump) electricity = "15–75 kW per unit";
  else if (isDesalination) electricity = "3.5–4.5 kWh/m³";
  else if (isDac) electricity = "250–500 kWh/t CO₂";
  else if (isFuelCell) electricity = "Net generator, 0.6–0.7 V/cell";
  else if (isCooling) electricity = "50–200 kW";
  else if (isPurif) electricity = "0.3–0.8 kWh/Nm³";
  else if (isWaterTreat) electricity = "1.5–3.0 kWh/m³";
  else if (isTurbine) electricity = "Net generator (kW output)";
  else if (isReformer) electricity = "150–500 kW auxiliary";
  else if (isReactor) electricity = "50–300 kW auxiliary";
  else if (isDigester) electricity = "5–15 kWh/t feed";
  else if (isPyrolysis) electricity = "80–150 kWh/t biomass";
  else if (isSeparator) electricity = "10–60 kW";
  else if (isValve) electricity = "Negligible (actuator only)";

  let water = "Not applicable";
  if (isElectrolyzer) water = "9–10 L/kg H₂ (demineralised)";
  else if (isDesalination) water = "Feed: 2.5× product rate";
  else if (isWaterTreat) water = "Reject rate 15–25%";
  else if (isBoiler) water = "Feedwater: 1.2× steam rate";
  else if (isReformer) water = "Steam-to-carbon ratio 2.5–3.5";
  else if (isDac) water = "1–5 t H₂O / t CO₂";
  else if (isDigester) water = "Slurry dilution 8–12% TS";

  let feedstock = "See datasheet";
  if (isElectrolyzer) feedstock = "Demineralised water + DC power";
  else if (isCompressor) feedstock = "Suction gas at 10–30 bar";
  else if (isReformer) feedstock = "Natural gas / biogas + steam";
  else if (isReactor) feedstock = "H₂ + N₂ (NH₃) or H₂ + CO₂ (MeOH)";
  else if (isTank) feedstock = "Cryogenic or pressurised fluid";
  else if (isBoiler) feedstock = "Natural gas / off-gas / H₂";
  else if (isDac) feedstock = "Ambient air (~420 ppm CO₂)";
  else if (isCo2) feedstock = "Flue gas (4–15% CO₂)";
  else if (isFuelCell) feedstock = "Pure H₂ (99.97%+)";
  else if (isPurif) feedstock = "Raw H₂ stream (85–99%)";
  else if (isDigester) feedstock = "Organic waste / manure / sludge";
  else if (isPyrolysis) feedstock = "Dry biomass <15% moisture";
  else if (isTurbine) feedstock = "Low-grade heat 80–200 °C";

  const opexLow = Math.round(price * 0.02);
  const opexHigh = Math.round(price * 0.05);
  const opex = `€${opexLow.toLocaleString()}–€${opexHigh.toLocaleString()}/yr (2–5% of CAPEX)`;

  const installIncluded = entry.strategy === "economiesOfScale" || price > 500_000;
  const installNote = installIncluded
    ? "Turnkey installation included"
    : "Installation by owner, OEM commissioning support";

  const maintIncluded = entry.strategy === "bestEfficiency" || price > 800_000;
  const warrantyYears = entry.option.trl >= 9 ? 5 : entry.option.trl >= 7 ? 3 : 2;
  const warrantyExt = price > 200_000;

  let opTemp = "Ambient to 80 °C";
  let opPressure = "Atmospheric";
  if (isElectrolyzer) { opTemp = "60–90 °C (stack)"; opPressure = "1–30 bar"; }
  else if (isCompressor) { opTemp = "40–180 °C interstage"; opPressure = "30–900 bar outlet"; }
  else if (isReformer) { opTemp = "800–950 °C"; opPressure = "20–35 bar"; }
  else if (isReactor) { opTemp = "200–500 °C"; opPressure = "50–300 bar"; }
  else if (isBoiler) { opTemp = "450–560 °C"; opPressure = "40–120 bar"; }
  else if (isTurbine) { opTemp = "80–200 °C source"; opPressure = "5–30 bar"; }
  else if (isHeatExchanger) { opTemp = "Up to 400 °C"; opPressure = "Up to 100 bar"; }
  else if (isTank) { opTemp = "−253 °C (LH₂) to ambient"; opPressure = "1–700 bar"; }
  else if (isFuelCell) { opTemp = "60–80 °C (PEM)"; opPressure = "1–3 bar"; }
  else if (isDac) { opTemp = "80–120 °C (regen)"; opPressure = "Atmospheric"; }
  else if (isDigester) { opTemp = "35–55 °C (mesophilic)"; opPressure = "Atmospheric"; }
  else if (isPyrolysis) { opTemp = "400–700 °C"; opPressure = "Atmospheric to 5 bar"; }

  const designLife = entry.option.trl >= 8 ? "20–25 years" : "15–20 years";

  const certs = ["CE", "ATEX Zone 1"];
  if (isElectrolyzer || isFuelCell) certs.push("IEC 62282");
  if (isCompressor || isTank) certs.push("PED 2014/68/EU");
  if (price > 100_000) certs.push("ISO 9001");

  return {
    electricity, water, feedstock, opex, installIncluded, installNote,
    maintIncluded, warrantyYears, warrantyExt, opTemp, opPressure,
    designLife, certs,
  };
}

function InfoRow({ icon: Icon, label, value, highlight }: {
  icon: React.ElementType; label: string; value: string; highlight?: boolean;
}) {
  return (
    <div className="flex items-start gap-3 py-2">
      <Icon className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="text-[11px] text-muted-foreground">{label}</p>
        <p className={`text-xs font-medium ${highlight ? "text-primary" : "text-card-foreground"}`}>{value}</p>
      </div>
    </div>
  );
}

function BoolRow({ label, value, detail }: { label: string; value: boolean; detail: string }) {
  return (
    <div className="flex items-start gap-3 py-2">
      {value
        ? <CheckCircle2 className="h-4 w-4 text-success mt-0.5 shrink-0" />
        : <XCircle className="h-4 w-4 text-destructive/60 mt-0.5 shrink-0" />}
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium text-card-foreground">{label}</p>
        <p className="text-[11px] text-muted-foreground">{detail}</p>
      </div>
    </div>
  );
}

interface Props { entry: EquipmentEntry }

export default function EquipmentDetailBody({ entry }: Props) {
  const s = strategyLabels[entry.strategy] ?? { label: entry.strategy, cls: "bg-muted text-muted-foreground border-border" };
  const specs = deriveSpecs(entry);

  return (
    <div className="px-6 py-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-base font-bold text-card-foreground truncate">
            {entry.option.manufacturer}, {entry.option.model}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {entry.category} · {entry.option.country}
          </p>
        </div>
        <Badge variant="outline" className={`text-[10px] font-semibold shrink-0 ${s.cls}`}>
          {s.label}
        </Badge>
      </div>

      {/* Quick stats */}
      <div className="grid grid-cols-4 gap-2 mt-4">
        {[
          { icon: DollarSign, label: "Unit Price", val: entry.option.priceDisplay },
          { icon: Clock, label: "Lead Time", val: `${entry.option.leadTimeMonths} months` },
          { icon: Beaker, label: "TRL", val: `Level ${entry.option.trl}/9` },
          { icon: Gauge, label: "Efficiency", val: entry.option.efficiency.split("–")[0].trim() },
        ].map((q) => (
          <div key={q.label} className="rounded-lg border border-border bg-muted/30 p-3 text-center">
            <q.icon className="h-4 w-4 text-muted-foreground mx-auto mb-1" />
            <p className="text-[10px] text-muted-foreground">{q.label}</p>
            <p className="text-xs font-semibold text-card-foreground mt-0.5 font-mono">{q.val}</p>
          </div>
        ))}
      </div>

      <Separator className="my-4" />

      <div className="grid md:grid-cols-2 gap-x-8 gap-y-0">
        <div>
          <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
            Consumption & Capacity
          </h4>
          <InfoRow icon={Zap} label="Electricity Consumption" value={specs.electricity} />
          <InfoRow icon={Droplets} label="Water Consumption" value={specs.water} />
          <InfoRow icon={Fuel} label="Feedstock / Input" value={specs.feedstock} />
          <InfoRow icon={DollarSign} label="Annual Operating Cost (est.)" value={specs.opex} highlight />
          <InfoRow icon={Scale} label="Pricing Basis" value={entry.pricingUnit} />
          {entry.option.scaleThreshold && (
            <InfoRow icon={Package} label="Scale Threshold" value={entry.option.scaleThreshold} />
          )}

          <Separator className="my-3" />
          <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
            Operating Conditions
          </h4>
          <InfoRow icon={ThermometerSun} label="Operating Temperature" value={specs.opTemp} />
          <InfoRow icon={Gauge} label="Operating Pressure" value={specs.opPressure} />
          <InfoRow icon={Settings} label="Design Life" value={specs.designLife} />
          <InfoRow icon={Beaker} label="Efficiency Detail" value={entry.option.efficiency} />
        </div>

        <div>
          <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
            Installation & Logistics
          </h4>
          <BoolRow label="Installation Included" value={specs.installIncluded} detail={specs.installNote} />
          <InfoRow icon={Truck} label="Estimated Shipping" value={`${entry.option.leadTimeMonths} months (ex-works)`} />
          <InfoRow icon={MapPin} label="Manufacturing Origin" value={entry.option.country} />
          <InfoRow icon={Factory} label="Manufacturer" value={entry.option.manufacturer} />

          <Separator className="my-3" />
          <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
            Warranty & Maintenance
          </h4>
          <BoolRow
            label="Maintenance Contract Included"
            value={specs.maintIncluded}
            detail={specs.maintIncluded ? "Preventive & corrective maintenance bundled" : "Owner-managed, OEM spare parts available"}
          />
          <InfoRow icon={ShieldCheck} label="Standard Warranty" value={`${specs.warrantyYears} years`} />
          {specs.warrantyExt && (
            <InfoRow icon={ShieldCheck} label="Extended Warranty" value="Available, contact manufacturer" />
          )}

          <Separator className="my-3" />
          <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
            Certifications
          </h4>
          <div className="flex flex-wrap gap-1.5 mt-1">
            {specs.certs.map((c) => (
              <Badge key={c} variant="outline" className="text-[10px] bg-muted/40">{c}</Badge>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
