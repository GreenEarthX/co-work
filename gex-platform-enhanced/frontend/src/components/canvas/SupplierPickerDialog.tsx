/**
 * SupplierPickerDialog — Procurement database browser.
 *
 * Two-step flow:
 *   1. Browse: flat list of all models, filterable/sortable. Click a row to inspect.
 *   2. Detail: full specification sheet for the selected model, with Apply button.
 */
import { useEffect, useMemo, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/Select";
import { getCatalogForLabel, type CatalogEntry } from "@/lib/equipmentCatalog";
import EquipmentDetailBody from "@/components/supplier/EquipmentDetailBody";
import {
  ArrowLeft,
  Check,
  Factory,
  Globe,
  MapPin,
  Clock,
  Gauge,
  DollarSign,
  Scale,
  Search,
  Cpu,
  LayoutGrid,
  Table2,
  Zap,
  Shield,
} from "lucide-react";

export interface SupplierSelection {
  manufacturer: string;
  model: string;
  country: string;
  priceDisplay: string;
  efficiency: string;
  leadTimeMonths: number;
  trl: number;
  scaleThreshold?: string;
  strategy: string;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  equipmentLabel: string;
  onSelect: (selection: SupplierSelection) => void;
  onAddToCanvas?: (selection: SupplierSelection) => void;
}

/* Flat row shape — re-exported alias of the shared catalog entry. */
type FlatModel = CatalogEntry;

/* ── Region mapping ── */

const COUNTRY_TO_REGION: Record<string, string> = {
  Germany: "Europe", France: "Europe", Norway: "Europe", Sweden: "Europe",
  Switzerland: "Europe", Denmark: "Europe", Netherlands: "Europe", Belgium: "Europe",
  Finland: "Europe", UK: "Europe",
  USA: "North America", Canada: "North America",
  China: "Asia Pacific", Japan: "Asia Pacific", India: "Asia Pacific",
};

function getRegion(country: string): string {
  return COUNTRY_TO_REGION[country] ?? "Other";
}

/* ── Sort types ── */

type SortKey = "price" | "leadTime" | "trl" | "name";

const SORT_OPTIONS: { value: SortKey; label: string; tooltip: string; icon: typeof DollarSign }[] = [
  { value: "price", label: "Price ↑", tooltip: "Cheapest first", icon: DollarSign },
  { value: "leadTime", label: "Lead Time ↑", tooltip: "Fastest delivery first", icon: Clock },
  { value: "trl", label: "TRL ↓", tooltip: "Highest readiness first", icon: Gauge },
  { value: "name", label: "A→Z", tooltip: "Alphabetical by manufacturer", icon: Factory },
];

function sortModels(models: FlatModel[], sort: SortKey): FlatModel[] {
  const sorted = [...models];
  switch (sort) {
    case "price": return sorted.sort((a, b) => a.priceEur - b.priceEur);
    case "leadTime": return sorted.sort((a, b) => a.leadTimeMonths - b.leadTimeMonths);
    case "trl": return sorted.sort((a, b) => b.trl - a.trl);
    case "name": return sorted.sort((a, b) => a.manufacturer.localeCompare(b.manufacturer));
    default: return sorted;
  }
}

/* ── Component ── */

type ViewState = "browse" | "detail";

const SupplierPickerDialog = ({ open, onOpenChange, equipmentLabel, onSelect }: Props) => {
  const [view, setView] = useState<ViewState>("browse");
  const [selectedModel, setSelectedModel] = useState<FlatModel | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("price");
  const [searchQuery, setSearchQuery] = useState("");
  const [regionFilter, setRegionFilter] = useState<string>("all");
  const [technologyFilter, setTechnologyFilter] = useState<string>("all");
  const [viewMode, setViewMode] = useState<"cards" | "table">("cards");
  const PAGE_SIZE = 30;
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const allModels = useMemo(() => getCatalogForLabel(equipmentLabel), [equipmentLabel]);

  const regions = useMemo(() => {
    const set = new Set(allModels.map((m) => getRegion(m.country)));
    return Array.from(set).sort();
  }, [allModels]);

  const equipmentTypes = useMemo(() => {
    const set = new Set(allModels.map((m) => m.equipmentType));
    return Array.from(set).sort();
  }, [allModels]);

  const filteredModels = useMemo(() => {
    let models = allModels;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      models = models.filter(
        (m) =>
          m.manufacturer.toLowerCase().includes(q) ||
          m.model.toLowerCase().includes(q) ||
          m.country.toLowerCase().includes(q),
      );
    }
    if (regionFilter !== "all") {
      models = models.filter((m) => getRegion(m.country) === regionFilter);
    }
    if (technologyFilter !== "all") {
      models = models.filter((m) => m.equipmentType === technologyFilter);
    }
    return sortModels(models, sortKey);
  }, [allModels, searchQuery, regionFilter, technologyFilter, sortKey]);

  // Reset pagination whenever filters/sort/view change
  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [searchQuery, regionFilter, technologyFilter, sortKey, viewMode, equipmentLabel, open]);

  const visibleModels = useMemo(
    () => filteredModels.slice(0, visibleCount),
    [filteredModels, visibleCount],
  );

  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) {
      setView("browse");
      setSelectedModel(null);
      setSearchQuery("");
      setRegionFilter("all");
      setTechnologyFilter("all");
    }
    onOpenChange(isOpen);
  };

  const handleInspect = (model: FlatModel) => {
    setSelectedModel(model);
    setView("detail");
  };

  const handleBack = () => {
    setView("browse");
    setSelectedModel(null);
  };

  const handleApply = () => {
    if (!selectedModel) return;
    onSelect({
      manufacturer: selectedModel.manufacturer,
      model: selectedModel.model,
      country: selectedModel.country,
      priceDisplay: selectedModel.priceDisplay,
      efficiency: selectedModel.efficiency,
      leadTimeMonths: selectedModel.leadTimeMonths,
      trl: selectedModel.trl,
      scaleThreshold: selectedModel.scaleThreshold,
      strategy: selectedModel.strategyOrigin,
    });
    handleOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-3xl max-h-[85vh] p-0 overflow-hidden flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-border bg-card/80 backdrop-blur-sm">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold flex items-center gap-2">
              {view === "detail" && (
                <button
                  onClick={handleBack}
                  className="h-7 w-7 rounded-md border border-border flex items-center justify-center hover:bg-muted transition-colors shrink-0"
                >
                  <ArrowLeft className="h-3.5 w-3.5" />
                </button>
              )}
              {view === "browse" ? equipmentLabel : selectedModel?.model ?? equipmentLabel}
            </DialogTitle>
          </DialogHeader>
          {view === "detail" && selectedModel ? (
            <p className="text-[11px] text-muted-foreground mt-1">
              {selectedModel.manufacturer} · {selectedModel.country}
            </p>
          ) : (
            <p className="text-[11px] text-muted-foreground mt-1">Select a supplier to apply to this equipment</p>
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-h-0 overflow-y-auto">
          {view === "browse" && (
            <>
              {/* Filter bar */}
              <div className="px-5 py-3 border-b border-border bg-muted/20 space-y-3">
                <div className="flex items-center gap-2">
                  <div className="relative flex-1">
                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                    <Input
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="Search manufacturer, model, or country…"
                      className="h-8 pl-8 text-xs"
                    />
                  </div>
                  {equipmentTypes.length > 1 && (
                    <Select value={technologyFilter} onValueChange={setTechnologyFilter}>
                      <SelectTrigger className="h-8 w-[170px] text-xs" title="Filter within suppliers shown for this equipment">
                        <Cpu className="h-3 w-3 mr-1.5 text-muted-foreground" />
                        <SelectValue placeholder="Equipment type" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all" className="text-xs">All equipment types</SelectItem>
                        {equipmentTypes.map((t) => (
                          <SelectItem key={t} value={t} className="text-xs">{t}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                  <Select value={regionFilter} onValueChange={setRegionFilter}>
                    <SelectTrigger className="h-8 w-[140px] text-xs">
                      <Globe className="h-3 w-3 mr-1.5 text-muted-foreground" />
                      <SelectValue placeholder="All Regions" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all" className="text-xs">All Regions</SelectItem>
                      {regions.map((r) => (
                        <SelectItem key={r} value={r} className="text-xs">{r}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground shrink-0">Sort</span>
                    <div className="flex gap-1 flex-wrap">
                      {SORT_OPTIONS.map((o) => {
                        const Icon = o.icon;
                        const isActive = sortKey === o.value;
                        return (
                          <button
                            key={o.value}
                            onClick={() => setSortKey(o.value)}
                            title={o.tooltip}
                            className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-medium transition-all ${
                              isActive
                                ? "border-primary bg-primary/10 text-primary"
                                : "border-border bg-card text-muted-foreground hover:text-foreground"
                            }`}
                          >
                            <Icon className="h-3 w-3" />
                            {o.label}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-muted-foreground tabular-nums">
                      {filteredModels.length} of {allModels.length} suppliers
                    </span>
                    <div className="flex items-center gap-0.5 rounded-md border border-border p-0.5">
                      <button
                        onClick={() => setViewMode("cards")}
                        className={`inline-flex items-center justify-center h-6 w-6 rounded transition-colors ${
                          viewMode === "cards" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        <LayoutGrid className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => setViewMode("table")}
                        className={`inline-flex items-center justify-center h-6 w-6 rounded transition-colors ${
                          viewMode === "table" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        <Table2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Browse list */}
              <div className="p-4">
                {filteredModels.length === 0 ? (
                  <div className="text-center py-12">
                    <p className="text-sm text-muted-foreground">No models match your filters.</p>
                  </div>
                ) : viewMode === "cards" ? (
                  <div className="grid gap-2.5 sm:grid-cols-2">
                    {visibleModels.map((m, i) => (
                      <button
                        key={`${m.manufacturer}-${m.model}-${m.strategyOrigin}-${i}`}
                        onClick={() => handleInspect(m)}
                        className="w-full text-left rounded-xl border border-border bg-card hover:border-primary/60 hover:bg-accent/30 hover:shadow-md transition-all p-4 space-y-2.5 group cursor-pointer"
                        title="Open full specification sheet"
                      >
                        {/* Header */}
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="text-xs font-semibold text-foreground group-hover:text-primary transition-colors truncate">{m.manufacturer}</p>
                            <p className="text-[11px] text-muted-foreground truncate">{m.model}</p>
                          </div>
                          <Badge variant="outline" className="text-[9px] h-5 px-1.5 text-primary border-primary/30 shrink-0">
                            {m.strategyOrigin}
                          </Badge>
                        </div>

                        {/* Category & Country */}
                        <div className="flex items-center gap-3 flex-wrap">
                          <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground">
                            <Factory className="h-3 w-3" />{m.equipmentType}
                          </span>
                          <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground">
                            <MapPin className="h-3 w-3" />{m.country}
                          </span>
                        </div>

                        {/* Specs grid */}
                        <div className="grid grid-cols-3 gap-2">
                          <div className="rounded-lg bg-muted/50 p-2 text-center">
                            <DollarSign className="h-3 w-3 text-muted-foreground mx-auto mb-0.5" />
                            <p className="text-[10px] font-semibold text-foreground font-mono">{m.priceDisplay}</p>
                            <p className="text-[8px] text-muted-foreground">{m.pricingUnit}</p>
                          </div>
                          <div className="rounded-lg bg-muted/50 p-2 text-center">
                            <Clock className="h-3 w-3 text-muted-foreground mx-auto mb-0.5" />
                            <p className="text-[10px] font-semibold text-foreground font-mono">{m.leadTimeMonths}mo</p>
                            <p className="text-[8px] text-muted-foreground">Lead time</p>
                          </div>
                          <div className="rounded-lg bg-muted/50 p-2 text-center">
                            <Gauge className="h-3 w-3 text-muted-foreground mx-auto mb-0.5" />
                            <p className="text-[10px] font-semibold text-foreground font-mono">TRL {m.trl}</p>
                            <p className="text-[8px] text-muted-foreground">Readiness</p>
                          </div>
                        </div>

                        {/* Efficiency */}
                        <p className="text-[10px] text-muted-foreground leading-relaxed">
                          <span className="font-medium text-foreground">Efficiency:</span> {m.efficiency}
                        </p>

                        {/* Scale threshold */}
                        {m.scaleThreshold && (
                          <p className="text-[10px] text-primary/80 bg-primary/5 rounded px-2 py-1">
                            <Scale className="h-3 w-3 inline mr-1" />{m.scaleThreshold}
                          </p>
                        )}

                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-xl border border-border overflow-x-auto">
                    <table className="min-w-[800px] w-full text-xs">
                      <thead>
                        <tr className="bg-muted/60">
                          <th className="text-left py-2.5 px-3 font-semibold text-muted-foreground">Manufacturer</th>
                          <th className="text-left py-2.5 px-3 font-semibold text-muted-foreground">Model</th>
                          <th className="text-right py-2.5 px-3 font-semibold text-muted-foreground">Price</th>
                          <th className="text-left py-2.5 px-3 font-semibold text-muted-foreground">Efficiency</th>
                          <th className="text-center py-2.5 px-3 font-semibold text-muted-foreground">TRL</th>
                          <th className="text-center py-2.5 px-3 font-semibold text-muted-foreground">Lead</th>
                          <th className="text-center py-2.5 px-3 font-semibold text-muted-foreground">Strategy</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visibleModels.map((m, idx) => (
                          <tr
                            key={`${m.manufacturer}-${m.model}-${m.strategyOrigin}-${idx}`}
                            onClick={() => handleInspect(m)}
                            className={`border-t border-border/40 cursor-pointer hover:bg-accent/40 transition-colors ${idx % 2 === 0 ? "bg-card" : "bg-muted/20"}`}
                          >
                            <td className="py-2 px-3">
                              <p className="font-medium text-foreground">{m.manufacturer}</p>
                              <p className="text-[10px] text-muted-foreground">{m.country}</p>
                            </td>
                            <td className="py-2 px-3 text-foreground/80">{m.model}</td>
                            <td className="py-2 px-3 text-right">
                              <p className="font-mono font-bold text-foreground">{m.priceDisplay}</p>
                              <p className="text-[9px] text-muted-foreground">{m.pricingUnit}</p>
                            </td>
                            <td className="py-2 px-3 text-[10px] text-foreground/80 max-w-[140px] truncate">{m.efficiency}</td>
                            <td className="py-2 px-3 text-center font-mono text-[11px]">{m.trl}</td>
                            <td className="py-2 px-3 text-center text-[10px] text-muted-foreground">{m.leadTimeMonths}mo</td>
                            <td className="py-2 px-3 text-center whitespace-nowrap">
                              <Badge variant="outline" className="text-[9px] h-5 px-1.5 whitespace-nowrap">{m.strategyOrigin}</Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {visibleCount < filteredModels.length && (
                  <div className="pt-3 flex justify-center">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}
                      className="text-xs"
                    >
                      Load more ({filteredModels.length - visibleCount} remaining)
                    </Button>
                  </div>
                )}
              </div>
            </>
          )}

          {view === "detail" && selectedModel && (
            <div className="flex flex-col">
              <EquipmentDetailBody
                entry={{
                  category: selectedModel.categoryLabel || selectedModel.equipmentType,
                  strategy: selectedModel.strategyKey,
                  pricingUnit: selectedModel.pricingUnit,
                  option: {
                    manufacturer: selectedModel.manufacturer,
                    model: selectedModel.model,
                    country: selectedModel.country,
                    priceEur: selectedModel.priceEur,
                    priceDisplay: selectedModel.priceDisplay,
                    efficiency: selectedModel.efficiency,
                    scaleThreshold: selectedModel.scaleThreshold,
                    leadTimeMonths: selectedModel.leadTimeMonths,
                    trl: selectedModel.trl,
                  },
                }}
              />
              <div className="border-t border-border bg-card/80 backdrop-blur-sm px-6 py-3 flex items-center justify-between sticky bottom-0">
                <div>
                  <p className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Selected supplier</p>
                  <p className="text-sm font-semibold text-foreground">{selectedModel.manufacturer} · {selectedModel.model} · {selectedModel.priceDisplay}</p>
                </div>
                <Button onClick={handleApply} className="gap-2 px-6">
                  <Check className="h-4 w-4" />
                  Apply to Equipment
                </Button>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};

/* ── Detail View ── */

export function ModelDetailView({
  model,
  onApply,
  applyLabel = "Apply to Equipment",
  hideApply = false,
}: {
  model: FlatModel;
  onApply?: () => void;
  applyLabel?: string;
  hideApply?: boolean;
}) {
  const specs: { label: string; value: string; icon: typeof Factory }[] = [
    { label: "Manufacturer", value: model.manufacturer, icon: Factory },
    { label: "Country of Origin", value: model.country, icon: MapPin },
    { label: "Equipment Type", value: model.equipmentType, icon: Cpu },
    { label: "Pricing Strategy", value: model.strategyOrigin, icon: DollarSign },
    { label: "Unit Price", value: `${model.priceDisplay} (${model.pricingUnit})`, icon: DollarSign },
    { label: "Efficiency", value: model.efficiency, icon: Zap },
    { label: "Technology Readiness Level", value: `TRL ${model.trl}`, icon: Shield },
    { label: "Lead Time", value: `${model.leadTimeMonths} months`, icon: Clock },
  ];

  if (model.scaleThreshold) {
    specs.push({ label: "Scale Threshold", value: model.scaleThreshold, icon: Scale });
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 p-6 space-y-5">
        {/* Model name + badge */}
        <div>
          <h3 className="text-lg font-bold text-foreground">{model.model}</h3>
          <div className="flex items-center gap-2 mt-1.5">
            <Badge variant="outline" className="text-[10px] h-5 px-2 text-primary border-primary/30">
              <Cpu className="h-3 w-3 mr-1" />
              {model.equipmentType}
            </Badge>
            <Badge variant="secondary" className="text-[10px] h-5 px-2">
              {model.strategyOrigin}
            </Badge>
          </div>
        </div>

        {/* Spec grid */}
        <div className="grid grid-cols-2 gap-x-6 gap-y-4">
          {specs.map((s) => {
            const Icon = s.icon;
            return (
              <div key={s.label} className="flex items-start gap-3">
                <div className="h-8 w-8 rounded-lg bg-muted flex items-center justify-center shrink-0 mt-0.5">
                  <Icon className="h-4 w-4 text-muted-foreground" />
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">{s.label}</p>
                  <p className="text-sm font-medium text-foreground mt-0.5">{s.value}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Sticky Apply footer */}
      {!hideApply && (
      <div className="border-t border-border bg-card/80 backdrop-blur-sm px-6 py-4 flex items-center justify-between">
        <div>
          <p className="text-xs text-muted-foreground">Selected model</p>
          <p className="text-sm font-semibold text-foreground">{model.model} · {model.priceDisplay}</p>
        </div>
        <Button onClick={onApply} className="gap-2 px-6">
          <Check className="h-4 w-4" />
          {applyLabel}
        </Button>
      </div>
      )}
    </div>
  );
}

export default SupplierPickerDialog;
