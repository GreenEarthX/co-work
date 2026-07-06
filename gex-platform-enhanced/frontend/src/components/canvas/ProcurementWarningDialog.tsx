/**
 * ProcurementWarningDialog — Three-step guided procurement flow:
 *   Step 1: Marketplace — filterable supplier catalog per equipment
 *   Step 2: Strategy Comparison — quick recommendation + detailed matrix
 *   Step 3: CAPEX Summary — breakdown with dashboard navigation
 */
import { useState, useMemo, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import {
  CheckCircle2,
  Clock,
  DollarSign,
  ExternalLink,
  FileText,
  Globe,
  Package,
  Scale,
  Settings,
  Shield,
  Star,
} from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { Node } from "@xyflow/react";
import {
  type ProcurementStrategy,
  type EquipmentProcurement,
  type ManufacturerOption,
  getProcurementEntry,
} from "./procurementDatabase";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  incompleteNodes: Node[];
  allNodes: Node[];
  plantName: string;
  onAutoFill: (strategy: ProcurementStrategy) => void;
  onSkip: () => void;
}

type Step = "summary";

interface CatalogRow {
  equipmentLabel: string;
  pricingUnit: string;
  option: ManufacturerOption;
  nodeId: string;
  isLowest: boolean;
}

const strategies: ProcurementStrategy[] = ["bestPrice", "bestEfficiency", "economiesOfScale"];

const formatCapex = (v: number) => {
  if (v >= 1_000_000) return `€${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `€${(v / 1_000).toFixed(0)}k`;
  return `€${v}`;
};

const ProcurementWarningDialog = ({
  open,
  onOpenChange,
  incompleteNodes,
  allNodes: _allNodes,
  plantName: _plantName,
  onAutoFill: _onAutoFill,
  onSkip,
}: Props) => {
  const navigate = useNavigate();
  const { plantId } = useParams();

  const [, setStep] = useState<Step>("summary");
  const [, setDirection] = useState<"forward" | "back">("forward");
  const [animKey, setAnimKey] = useState(0);
  const [, setSelected] = useState<ProcurementStrategy | null>(null);
  const [appliedStrategy, setAppliedStrategy] = useState<ProcurementStrategy | null>(null);
  const [, setSearchQuery] = useState("");
  const [, setCountryFilter] = useState<string>("all");
  const [, setTrlFilter] = useState<string>("all");
  const [detailRow, setDetailRow] = useState<CatalogRow | null>(null);
  const [rfqItems, setRfqItems] = useState<Map<string, CatalogRow>>(new Map());

  const addToRfq = useCallback((row: CatalogRow) => {
    const key = `${row.nodeId}|${row.option.manufacturer}|${row.option.model}`;
    setRfqItems((prev) => {
      const next = new Map(prev);
      next.set(key, row);
      return next;
    });
  }, []);

  const isInRfq = useCallback((row: CatalogRow) => {
    const key = `${row.nodeId}|${row.option.manufacturer}|${row.option.model}`;
    return rfqItems.has(key);
  }, [rfqItems]);

  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) {
      setStep("summary");
      setDirection("forward");
      setAnimKey(0);
      setSelected(null);
      setAppliedStrategy(null);
      setSearchQuery("");
      setCountryFilter("all");
      setTrlFilter("all");
    }
    onOpenChange(isOpen);
  };

  // Build entries
  const entries = useMemo(() => {
    const result: { node: Node; entry: EquipmentProcurement }[] = [];
    for (const node of incompleteNodes) {
      const entry = getProcurementEntry(node.data.label as string);
      if (entry) result.push({ node, entry });
    }
    return result;
  }, [incompleteNodes]);

  // CAPEX totals (scaled to plant size)
  const totals: Record<ProcurementStrategy, number> = { bestPrice: 0, bestEfficiency: 0, economiesOfScale: 0 };
  for (const { entry } of entries) {
    const qty = entry.plantScaleQty ?? 1;
    for (const s of strategies) {
      totals[s] += entry[s].priceEur * qty;
    }
  }
  const lowestStrategy = strategies.reduce((a, b) => (totals[a] <= totals[b] ? a : b));
  // Use the lowest-cost strategy as default for CAPEX display
  const displayStrategy = appliedStrategy ?? lowestStrategy;

  return (
    <>
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-5xl h-[92vh] p-0 overflow-hidden flex flex-col">
        {/* Header */}
        <div className="px-6 pt-5 pb-3 border-b border-border/50 bg-card/80 backdrop-blur-sm">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold flex items-center gap-2.5">
              <span className="h-9 w-9 rounded-lg bg-primary/10 flex items-center justify-center">
                <DollarSign className="h-5 w-5 text-primary" />
              </span>
              CAPEX Summary
            </DialogTitle>
            <DialogDescription className="text-sm text-muted-foreground mt-1">
              {entries.length} equipment items with estimated market pricing.
            </DialogDescription>
          </DialogHeader>
        </div>

        <div key={animKey} className="flex-1 flex flex-col min-h-0">
          <div className="flex-1 flex flex-col min-h-0">
            <div className="px-6 py-4 border-b border-border/50">
              {/* Total CAPEX highlight */}
              <div className="rounded-xl border-2 border-primary/25 bg-primary/5 p-5 flex items-center gap-4">
                <span className="h-12 w-12 rounded-xl bg-card flex items-center justify-center shadow-sm">
                  <DollarSign className="h-6 w-6 text-primary" />
                </span>
                <div className="flex-1">
                  <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Total Estimated CAPEX</p>
                  <p className="text-xs text-muted-foreground mt-0.5">{entries.length} equipment items across the plant</p>
                </div>
                <div className="text-right">
                  <p className="text-2xl font-mono font-bold text-primary">
                    {formatCapex(totals[displayStrategy])}
                  </p>
                </div>
              </div>
            </div>

            <ScrollArea className="flex-1 min-h-0">
              <div className="px-6 py-4 space-y-4">
                {/* Line item breakdown */}
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">CAPEX Breakdown</p>
                  <div className="space-y-2">
                    {entries.map(({ node, entry }) => {
                      const opt = entry[displayStrategy];
                      const qty = entry.plantScaleQty ?? 1;
                      const scaledPrice = opt.priceEur * qty;
                      const pctOfTotal = totals[displayStrategy] > 0
                        ? (scaledPrice / totals[displayStrategy]) * 100
                        : 0;

                      return (
                        <div key={node.id} className="rounded-lg border border-border bg-card p-3 flex items-center gap-3">
                          <span className="h-8 w-8 rounded-md bg-primary/10 flex items-center justify-center shrink-0">
                            <Settings className="h-3.5 w-3.5 text-primary" />
                          </span>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <p className="text-sm font-medium truncate">{node.data.label as string}</p>
                            </div>
                            <p className="text-[10px] text-muted-foreground">
                              {opt.manufacturer} · {opt.model} · {opt.country}{qty > 1 ? ` (×${qty})` : ""}
                            </p>
                          </div>
                          <div className="text-right shrink-0">
                            <p className="text-sm font-mono font-bold text-primary">
                              {formatCapex(scaledPrice)}
                            </p>
                            <p className="text-[10px] text-muted-foreground">{pctOfTotal.toFixed(0)}% of total</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Quick insights */}
                <div className="rounded-xl border border-border bg-muted/30 p-4 space-y-3">
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Quick Insights</p>
                  <div className="grid grid-cols-3 gap-3">
                    <div className="rounded-lg bg-card border border-border p-3 text-center">
                      <p className="text-[10px] text-muted-foreground">Avg. Lead Time</p>
                      <p className="text-lg font-mono font-bold text-foreground">
                        {entries.length > 0
                          ? (entries.reduce((sum, { entry }) => sum + entry[displayStrategy].leadTimeMonths, 0) / entries.length).toFixed(0)
                          : 0}
                        <span className="text-xs font-normal text-muted-foreground ml-0.5">mo</span>
                      </p>
                    </div>
                    <div className="rounded-lg bg-card border border-border p-3 text-center">
                      <p className="text-[10px] text-muted-foreground">Avg. TRL</p>
                      <p className="text-lg font-mono font-bold text-foreground">
                        {entries.length > 0
                          ? (entries.reduce((sum, { entry }) => sum + entry[displayStrategy].trl, 0) / entries.length).toFixed(1)
                          : 0}
                      </p>
                    </div>
                    <div className="rounded-lg bg-card border border-border p-3 text-center">
                      <p className="text-[10px] text-muted-foreground">Suppliers</p>
                      <p className="text-lg font-mono font-bold text-foreground">
                        {new Set(entries.map(({ entry }) => entry[displayStrategy].manufacturer)).size}
                        <span className="text-xs font-normal text-muted-foreground ml-0.5">unique</span>
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </ScrollArea>

            {/* Footer */}
            <div className="px-6 py-4 border-t border-border bg-muted/20 flex items-center gap-3 shrink-0">
              <Button variant="outline" onClick={() => handleOpenChange(false)}>
                Continue Editing
              </Button>
              <Button variant="outline" onClick={onSkip}>
                Skip & Save
              </Button>
              <div className="flex-1" />
              <Button
                className="gap-2"
                onClick={() => {
                  handleOpenChange(false);
                  navigate(`/plant/${plantId || "rotterdam-rfnbo"}`);
                }}
              >
                View in Viability Dashboard
                <ExternalLink className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>

    {/* ═══════════ MODEL DETAIL SHEET ═══════════ */}
    <Sheet open={!!detailRow} onOpenChange={(o) => !o && setDetailRow(null)}>
      <SheetContent side="right" className="w-[420px] sm:max-w-[420px] p-0 flex flex-col">
        {detailRow && (() => {
          const opt = detailRow.option;
          const specRows: [string, string][] = [
            ["Manufacturer", opt.manufacturer],
            ["Model", opt.model],
            ["Country of Origin", opt.country],
            ["Unit Price", opt.priceDisplay],
            ["Pricing Basis", detailRow.pricingUnit],
            ["Efficiency", opt.efficiency],
            ["Technology Readiness", `TRL ${opt.trl}`],
            ["Lead Time", `${opt.leadTimeMonths} months`],
          ];
          if (opt.scaleThreshold) {
            specRows.push(["Scale Threshold", opt.scaleThreshold]);
          }

          // Generate synthetic technical specs based on equipment type
          const techSpecs: [string, string][] = [];
          const label = detailRow.equipmentLabel.toLowerCase();
          if (label.includes("electrolyzer") || label.includes("electrolysis")) {
            techSpecs.push(
              ["Technology", opt.model.includes("PEM") ? "PEM Electrolysis" : "Alkaline Electrolysis"],
              ["Operating Pressure", opt.model.includes("PEM") ? "30–80 bar" : "1–30 bar"],
              ["Operating Temperature", opt.model.includes("PEM") ? "50–80 °C" : "60–90 °C"],
              ["Stack Lifetime", "80,000–100,000 hours"],
              ["Water Consumption", "9–10 L/kg H₂"],
              ["Ramp Rate", opt.model.includes("PEM") ? "< 1 second (0–100%)" : "< 5 minutes (0–100%)"],
              ["Turndown Ratio", opt.model.includes("PEM") ? "5–100%" : "20–100%"],
              ["H₂ Purity (stack outlet)", "≥ 99.5%"],
            );
          } else if (label.includes("compressor")) {
            techSpecs.push(
              ["Type", opt.model.includes("Diaphragm") ? "Diaphragm" : "Reciprocating"],
              ["Discharge Pressure", opt.efficiency.includes("1000") ? "up to 1,000 bar" : "up to 500 bar"],
              ["Suction Pressure", "15–35 bar"],
              ["Flow Rate", "500–5,000 Nm³/h"],
              ["Number of Stages", opt.model.includes("6-stage") ? "6" : "2–4"],
              ["Cooling", "Water-cooled intercoolers"],
              ["Seal Type", "Hermetic / dry-running"],
              ["Noise Level", "< 85 dB(A) at 1 m"],
            );
          } else if (label.includes("tank") || label.includes("storage") || label.includes("buffer")) {
            techSpecs.push(
              ["Vessel Type", opt.model.includes("Cryo") ? "Cryogenic vacuum-insulated" : "Type IV composite"],
              ["Design Pressure", opt.efficiency.split("–")[0]?.trim() || "350–700 bar"],
              ["Material", opt.model.includes("Type IV") ? "Carbon fibre / HDPE liner" : "Stainless steel / Perlite"],
              ["Operating Temperature", opt.model.includes("Cryo") ? "-253 °C (LH₂)" : "Ambient"],
              ["Safety System", "PRV, burst disc, fire detection"],
              ["Certification", "PED 2014/68/EU, ASME VIII"],
            );
          } else if (label.includes("pump")) {
            techSpecs.push(
              ["Type", opt.model.includes("Centrifugal") ? "Multi-stage centrifugal" : "High-pressure centrifugal"],
              ["Max Discharge Pressure", opt.efficiency.includes("80 bar") ? "80 bar" : "25 bar"],
              ["Flow Range", "10–200 m³/h"],
              ["Impeller Material", "Duplex stainless steel"],
              ["Seal", "Mechanical double seal"],
              ["Motor Rating", "30–250 kW"],
            );
          } else if (label.includes("heat exchanger") || label.includes("cooler")) {
            techSpecs.push(
              ["Type", opt.model.includes("Plate") ? "Gasketed plate" : opt.model.includes("Brazed") ? "Brazed plate" : "Fusion-bonded plate"],
              ["Max Temperature", opt.efficiency.includes("550") ? "550 °C" : "200 °C"],
              ["Max Pressure", "40 bar"],
              ["Heat Transfer Area", "50–500 m²"],
              ["Material", "SS 316L / Titanium"],
              ["TEMA Designation", "BEM / AES"],
            );
          } else if (label.includes("turbine")) {
            techSpecs.push(
              ["Type", opt.model.includes("Aero") ? "Aeroderivative gas turbine" : "Industrial gas turbine"],
              ["Power Output", "6–50 MW"],
              ["H₂ Co-firing", opt.model.includes("H₂-ready") ? "Up to 100% H₂" : "Up to 30% H₂ blend"],
              ["Exhaust Temperature", "450–550 °C"],
              ["NOx Emissions", "< 25 ppm (DLN)"],
              ["Start-up Time", opt.model.includes("Aero") ? "< 10 minutes" : "< 30 minutes"],
            );
          } else if (label.includes("water treatment") || label.includes("reverse osmosis") || label.includes("demin")) {
            techSpecs.push(
              ["Process", opt.model.includes("RO") ? "Reverse Osmosis" : "UF + EDI"],
              ["Feed Water Quality", "< 2,000 ppm TDS"],
              ["Output Quality", opt.efficiency.includes("µS") ? "< 0.1 µS/cm" : "< 5 µS/cm"],
              ["Recovery Rate", opt.efficiency.split("–")[0]?.trim() || "95%"],
              ["Capacity", "50–200 m³/h"],
              ["Chemical Dosing", "Antiscalant, NaOH, HCl"],
            );
          } else {
            techSpecs.push(
              ["Operating Pressure", "Design-specific"],
              ["Operating Temperature", "Design-specific"],
              ["Material of Construction", "Carbon steel / SS 316L"],
              ["Design Code", "ASME / PED compliant"],
              ["Instrumentation", "Full P&ID package included"],
            );
          }

          return (
            <div className="flex flex-col h-full">
              <SheetHeader className="px-6 pt-6 pb-4">
                <div className="flex items-start gap-3">
                  <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                    <Package className="h-5 w-5 text-primary" />
                  </div>
                  <div className="min-w-0">
                    <SheetTitle className="text-sm font-bold leading-tight">
                      {opt.manufacturer}, {opt.model}
                    </SheetTitle>
                    <SheetDescription className="text-xs mt-1">
                      {detailRow.equipmentLabel} · {opt.country}
                    </SheetDescription>
                  </div>
                </div>
              </SheetHeader>

              <Separator />

              <div className="flex-1 min-h-0 overflow-y-auto">
                <div className="px-6 py-5 space-y-6">
                  {/* Price highlight */}
                  <div className="rounded-lg border border-border bg-muted/30 p-4 flex items-center justify-between">
                    <div>
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">Unit Price</p>
                      <p className="text-2xl font-bold text-foreground mt-0.5">{opt.priceDisplay}</p>
                      <p className="text-[10px] text-muted-foreground">{detailRow.pricingUnit}</p>
                    </div>
                    {detailRow.isLowest && (
                      <Badge className="bg-success/10 text-success border-success/30 text-[10px]">
                        <Star className="h-3 w-3 mr-1" /> Best Price
                      </Badge>
                    )}
                  </div>

                  {/* Commercial Specifications */}
                  <div>
                    <h4 className="text-xs font-semibold text-foreground mb-3 flex items-center gap-1.5">
                      <FileText className="h-3.5 w-3.5 text-muted-foreground" />
                      Commercial Specifications
                    </h4>
                    <div className="rounded-lg border border-border overflow-hidden">
                      {specRows.map(([key, val], i) => (
                        <div key={key} className={`flex justify-between items-center px-3 py-2 text-xs ${i % 2 === 0 ? "bg-card" : "bg-muted/20"}`}>
                          <span className="text-muted-foreground">{key}</span>
                          <span className="font-medium text-foreground text-right max-w-[55%]">{val}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Technical Specifications */}
                  <div>
                    <h4 className="text-xs font-semibold text-foreground mb-3 flex items-center gap-1.5">
                      <Settings className="h-3.5 w-3.5 text-muted-foreground" />
                      Technical Specifications
                    </h4>
                    <div className="rounded-lg border border-border overflow-hidden">
                      {techSpecs.map(([key, val], i) => (
                        <div key={key} className={`flex justify-between items-center px-3 py-2 text-xs ${i % 2 === 0 ? "bg-card" : "bg-muted/20"}`}>
                          <span className="text-muted-foreground">{key}</span>
                          <span className="font-medium text-foreground text-right max-w-[55%]">{val}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Compliance & Certifications */}
                  <div>
                    <h4 className="text-xs font-semibold text-foreground mb-3 flex items-center gap-1.5">
                      <Shield className="h-3.5 w-3.5 text-muted-foreground" />
                      Compliance & Certifications
                    </h4>
                    <div className="flex flex-wrap gap-1.5">
                      {["CE Marking", "ISO 9001", "PED 2014/68/EU", "ATEX Zone 1/2", "IECEx"].map((cert) => (
                        <Badge key={cert} variant="outline" className="text-[10px] font-normal">
                          {cert}
                        </Badge>
                      ))}
                      {opt.trl >= 9 && (
                        <Badge variant="outline" className="text-[10px] font-normal border-success/40 text-success">
                          Commercially Proven
                        </Badge>
                      )}
                    </div>
                  </div>

                  {/* Delivery info */}
                  <div className="rounded-lg border border-border bg-muted/30 p-4 space-y-2">
                    <div className="flex items-center gap-2 text-xs">
                      <Clock className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="text-muted-foreground">Estimated Lead Time:</span>
                      <span className="font-semibold text-foreground">{opt.leadTimeMonths} months</span>
                    </div>
                    <div className="flex items-center gap-2 text-xs">
                      <Globe className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="text-muted-foreground">Manufacturing Site:</span>
                      <span className="font-semibold text-foreground">{opt.country}</span>
                    </div>
                    {opt.scaleThreshold && (
                      <div className="flex items-center gap-2 text-xs">
                        <Scale className="h-3.5 w-3.5 text-muted-foreground" />
                        <span className="text-muted-foreground">Volume Discount:</span>
                        <span className="font-semibold text-foreground">{opt.scaleThreshold}</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Sticky RFQ footer */}
              <div className="border-t border-border bg-card/95 backdrop-blur-sm px-6 py-4 shrink-0">
                {isInRfq(detailRow) ? (
                  <div className="flex items-center gap-2 text-xs text-success">
                    <CheckCircle2 className="h-4 w-4" />
                    <span className="font-medium">Added to RFQ basket ({rfqItems.size} item{rfqItems.size !== 1 ? "s" : ""})</span>
                  </div>
                ) : (
                  <Button
                    className="w-full"
                    onClick={() => {
                      addToRfq(detailRow);
                    }}
                  >
                    <FileText className="h-4 w-4 mr-2" />
                    Request Quote
                  </Button>
                )}
              </div>
            </div>
          );
        })()}
      </SheetContent>
    </Sheet>
    </>
  );
};

export default ProcurementWarningDialog;
