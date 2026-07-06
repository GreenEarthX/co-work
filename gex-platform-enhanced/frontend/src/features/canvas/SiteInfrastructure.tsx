/**
 * SiteInfrastructure — Workspace for non-process equipment, construction
 * and site costs. Accessible from the system boundary on the plant canvas
 * via /canvas/:plantId/infrastructure.
 */
import { useEffect, useMemo, useState, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft, Building2, HardHat, MapPin, Loader2, Check,
  Zap, ShieldAlert, Wrench, Package, Plus, Trash2, Pencil, Search,
  AlertTriangle, FileText,
} from "lucide-react";
import AppNav from "@/components/AppNav";
import UserContextBar from "@/components/UserContextBar";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/Badge";
import { Switch } from "@/components/ui/switch";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { getProjectOrDefault } from "@/lib/projectRegistry";
import {
  defaultInfrastructure,
  loadInfrastructure,
  saveInfrastructure,
  computeInfraTotals,
  formatEur,
  INFRASTRUCTURE_SECTIONS,
  INFRASTRUCTURE_EQUIPMENT,
  type InfrastructureData,
  type InfraEquipmentItem,
} from "@/lib/siteInfrastructure";
import SupplierPickerDialog, { type SupplierSelection } from "@/components/canvas/SupplierPickerDialog";
import InfraItemDetailsDialog from "@/components/canvas/InfraItemDetailsDialog";
import ConstructionForm from "@/components/canvas/ConstructionForm";
import EurNumberInput from "@/components/ui/EurNumberInput";

const SECTION_ICON: Record<string, typeof Zap> = {
  "Power & Electrical": Zap,
  "Fire & Gas Safety": ShieldAlert,
  "Utilities & Auxiliaries": Wrench,
  "Storage & Handling": Package,
};

const TAB_SCOPE: Record<string, string> = {
  site:        "Site & Land — costs incurred outside the fence or before construction starts (land, surveys, permits, utility tie-in, owner's costs).",
  construction: "Construction (EPC) — the build itself inside the fence: civil works, mechanical bulks, electrical & instrumentation, indirect engineering services.",
  equipment:   "Site Equipment — physical assets installed inside the fence (power, fire & gas safety, utilities, storage). Process equipment lives on the Canvas.",
};

export default function SiteInfrastructure() {
  const { plantId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const plant = getProjectOrDefault(plantId);

  const [data, setData] = useState<InfrastructureData>(() => defaultInfrastructure());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<"site" | "construction" | "equipment">("site");
  const [equipmentSearch, setEquipmentSearch] = useState("");
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [pickerForItemId, setPickerForItemId] = useState<string | null>(null);
  const [addPickerOpen, setAddPickerOpen] = useState(false);
  const [detailsForItemId, setDetailsForItemId] = useState<string | null>(null);

  useEffect(() => {
    if (!plantId) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      const loaded = await loadInfrastructure(plantId, user?.id);
      if (!cancelled) {
        setData(loaded);
        setLoading(false);
        setDirty(false);
      }
    })();
    return () => { cancelled = true; };
  }, [plantId, user?.id]);

  const totals = useMemo(() => computeInfraTotals(data), [data]);

  const updateItem = useCallback((id: string, patch: Partial<InfraEquipmentItem>) => {
    setData((prev) => ({
      ...prev,
      items: prev.items.map((i) => (i.id === id ? { ...i, ...patch } : i)),
    }));
    setDirty(true);
  }, []);

  const handleSupplierSelect = useCallback((selection: SupplierSelection) => {
    if (!pickerForItemId) return;
    setData((prev) => ({
      ...prev,
      items: prev.items.map((i) => {
        if (i.id !== pickerForItemId) return i;
        // priceDisplay may be "€ 1,234,000" — best effort parse to number
        const numeric = Number(String(selection.priceDisplay).replace(/[^0-9.]/g, ""));
        return {
          ...i,
          claimed: true,
          unitCostEur: Number.isFinite(numeric) && numeric > 0 ? numeric : i.unitCostEur,
          procurement: {
            manufacturer: selection.manufacturer,
            model: selection.model,
            country: selection.country,
            priceEur: Number.isFinite(numeric) ? numeric : 0,
            priceDisplay: selection.priceDisplay,
            efficiency: selection.efficiency,
            leadTimeMonths: selection.leadTimeMonths,
            trl: selection.trl,
            scaleThreshold: selection.scaleThreshold,
            strategy: selection.strategy,
            plantScaleQty: 1,
            source: "database",
            updatedAt: new Date().toISOString(),
          },
        };
      }),
    }));
    setDirty(true);
    setPickerForItemId(null);
    toast.success("Supplier applied");
  }, [pickerForItemId]);

  const handleSave = useCallback(async () => {
    if (!plantId) return;
    setSaving(true);
    const res = await saveInfrastructure(plantId, data, user?.id);
    setSaving(false);
    if (res.ok) {
      setDirty(false);
      setSavedAt(Date.now());
    } else {
      toast.error(res.error ?? "Failed to save");
    }
  }, [plantId, data, user?.id]);

  // Debounced auto-save so changes persist without a manual click.
  useEffect(() => {
    if (!dirty || loading || !plantId) return;
    const t = setTimeout(() => { handleSave(); }, 800);
    return () => clearTimeout(t);
  }, [data, dirty, loading, plantId, handleSave]);

  const groupedItems = useMemo(() => {
    const out: Record<string, InfraEquipmentItem[]> = {};
    for (const section of INFRASTRUCTURE_SECTIONS) out[section] = [];
    for (const item of data.items) {
      (out[item.section] ??= []).push(item);
    }
    return out;
  }, [data.items]);

  const activeItemForPicker = data.items.find((i) => i.id === pickerForItemId);

  const addEquipment = useCallback((spec: { equipmentId: string; label: string; section: string }) => {
    const newId = `${spec.equipmentId}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`;
    setData((prev) => ({
      ...prev,
      items: [
        ...prev.items,
        {
          id: newId,
          equipmentId: spec.equipmentId,
          label: spec.label,
          section: spec.section,
          claimed: true,
          quantity: 1,
          unitCostEur: 0,
        },
      ],
    }));
    setDirty(true);
    setAddPickerOpen(false);
    setDetailsForItemId(newId);
  }, []);

  // Soft validation: claimed items missing cost / manufacturer.
  const validationIssues = useMemo(() => {
    return data.items
      .filter((i) => i.claimed && !i.notApplicable)
      .filter((i) => (i.unitCostEur || 0) === 0 || !i.procurement?.manufacturer);
  }, [data.items]);

  const filteredAddItems = useMemo(() => {
    const q = equipmentSearch.trim().toLowerCase();
    if (!q) return INFRASTRUCTURE_EQUIPMENT;
    return INFRASTRUCTURE_EQUIPMENT.filter(
      (i) => i.label.toLowerCase().includes(q) || i.equipmentId.toLowerCase().includes(q),
    );
  }, [equipmentSearch]);

  // Per-section subtotal helper for the Equipment tab.
  const sectionSubtotal = useCallback((items: InfraEquipmentItem[]) => {
    return items
      .filter((i) => i.claimed && !i.notApplicable)
      .reduce((s, i) => s + (i.quantity || 0) * (i.unitCostEur || 0), 0);
  }, []);

  const saveStatusLabel = saving
    ? "Saving…"
    : dirty
      ? "Unsaved changes"
      : savedAt
        ? `Saved · ${Math.max(1, Math.round((Date.now() - savedAt) / 1000))}s ago`
        : "Saved";

  return (
    <div className="min-h-screen bg-background">
      <AppNav />
      <UserContextBar />
      <div className="border-b border-border bg-card/40 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-6 pt-2 pb-4">
          <button
            type="button"
            onClick={() => navigate(`/canvas/${plantId}`)}
            className="inline-flex items-center gap-1 text-xs text-foreground/70 hover:text-foreground transition-colors"
            aria-label="Back to plant canvas"
          >
            <ArrowLeft className="h-3 w-3" />
            Back to Canvas
          </button>
          <div className="mt-1 flex items-end justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground uppercase tracking-[0.14em]">
                <Building2 className="h-3 w-3" />
                Site Infrastructure
              </div>
              <h1 className="mt-0.5 text-xl font-semibold text-foreground tracking-tight truncate">
                {plant?.name ?? plantId}
              </h1>
            </div>
            <div className="flex items-center gap-2 shrink-0 text-xs text-muted-foreground" aria-live="polite">
              {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {!saving && !dirty && <Check className="h-3.5 w-3.5 text-success" />}
              <span className="tabular-nums">{saveStatusLabel}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6">
        {loading ? (
          <div className="flex items-center justify-center py-20 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading site infrastructure…
          </div>
        ) : (
          <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as typeof activeTab)} className="w-full">
            <TabsList className="grid grid-cols-3 w-full">
              <TabsTrigger value="site" className="gap-2">
                <MapPin className="h-4 w-4" /> Site &amp; Land
              </TabsTrigger>
              <TabsTrigger value="construction" className="gap-2">
                <HardHat className="h-4 w-4" /> Construction (EPC)
              </TabsTrigger>
              <TabsTrigger value="equipment" className="gap-2">
                <Building2 className="h-4 w-4" /> Site Equipment
              </TabsTrigger>
            </TabsList>

            {/* Scope banner — explicitly disambiguates what belongs in the active tab */}
            <div className="mt-3 rounded-md border border-border bg-muted/40 px-3 py-2 text-[11px] text-muted-foreground flex items-start gap-2">
              <FileText className="h-3.5 w-3.5 mt-0.5 shrink-0" />
              <span>{TAB_SCOPE[activeTab]}</span>
            </div>

            {/* ── Equipment ── */}
            <TabsContent value="equipment" className="mt-5 space-y-5">
              {data.items.some((i) => i.claimed) && (
                <div className="flex items-center justify-between gap-3">
                  <div className="text-[11px] text-muted-foreground">
                    {data.items.filter((i) => i.claimed && !i.notApplicable).length} active ·{" "}
                    {data.items.filter((i) => i.notApplicable).length} N/A
                  </div>
                  <Button onClick={() => setAddPickerOpen(true)} size="sm" className="gap-2">
                    <Plus className="h-4 w-4" /> Add equipment
                  </Button>
                </div>
              )}

              {validationIssues.length > 0 && (
                <div className="rounded-md border border-warning/40 bg-warning-soft/50 px-3 py-2 text-xs text-foreground flex items-start gap-2">
                  <AlertTriangle className="h-4 w-4 text-warning mt-0.5 shrink-0" />
                  <div className="flex-1">
                    <div className="font-medium">
                      {validationIssues.length} item{validationIssues.length === 1 ? "" : "s"} need details
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      Missing manufacturer or unit cost. Click an item to configure, or mark it Not Applicable.
                    </div>
                  </div>
                </div>
              )}

              {!data.items.some((i) => i.claimed) ? (
                <div className="rounded-xl border border-dashed border-border bg-muted/30 px-6 py-14 text-center space-y-3">
                  <Building2 className="h-10 w-10 text-muted-foreground/40 mx-auto mb-4" />
                  <p className="text-sm text-foreground">No site equipment claimed yet</p>
                  <p className="text-[11px] text-muted-foreground max-w-md mx-auto">
                    Add the non-process units that live inside the fence: power & electrical, fire &amp; gas safety,
                    utilities, storage. Process units belong on the plant canvas.
                  </p>
                  <Button variant="outline" onClick={() => setAddPickerOpen(true)} className="gap-2 bg-card">
                    <Plus className="h-4 w-4" /> Add equipment
                  </Button>
                </div>
              ) : (
                INFRASTRUCTURE_SECTIONS.map((section) => {
                  const claimedItems = (groupedItems[section] ?? []).filter((i) => i.claimed);
                  if (claimedItems.length === 0) return null;
                  const Icon = SECTION_ICON[section] ?? Building2;
                  const subtotal = sectionSubtotal(claimedItems);
                  return (
                    <section key={section} className="rounded-xl border border-border bg-card overflow-hidden shadow-sm">
                      <header className="flex items-center gap-2 px-4 py-3 border-b border-border bg-muted/40">
                        <span className="h-7 w-7 rounded-md bg-card border border-border flex items-center justify-center">
                          <Icon className="h-3.5 w-3.5 text-muted-foreground" />
                        </span>
                        <h2 className="text-sm font-semibold text-foreground flex-1">{section}</h2>
                        <Badge variant="outline" className="text-[10px] font-mono bg-card">
                          {claimedItems.length} item{claimedItems.length === 1 ? "" : "s"}
                        </Badge>
                        <span className="text-xs text-muted-foreground tabular-nums">
                          Subtotal <span className="font-semibold text-foreground ml-1">{formatEur(subtotal)}</span>
                        </span>
                      </header>
                      <div className="divide-y divide-border">
                        {claimedItems.map((item) => (
                          <div key={item.id} className={`px-4 py-3 flex items-center gap-4 ${item.notApplicable ? "opacity-60" : ""}`}>
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="text-sm font-medium text-foreground truncate">{item.label}</span>
                                <span className="text-[10px] font-mono text-muted-foreground">{item.equipmentId}</span>
                                {item.procurement?.source === "database" && (
                                  <Badge variant="outline" className="h-4 px-1.5 text-[9px] gap-1 bg-card">
                                    <Check className="h-2.5 w-2.5 text-success" /> DB
                                  </Badge>
                                )}
                                {item.notApplicable && (
                                  <Badge variant="outline" className="h-4 px-1.5 text-[9px] bg-muted text-muted-foreground">N/A</Badge>
                                )}
                              </div>
                              <div className="text-[11px] text-muted-foreground mt-0.5 truncate">
                                {item.procurement?.manufacturer
                                  ? `${item.procurement.manufacturer} · ${item.procurement.model}${item.procurement.country ? ` · ${item.procurement.country}` : ""}`
                                  : <span className="italic text-warning">Details not configured</span>}
                              </div>
                            </div>
                            <div className="hidden md:flex flex-col items-end shrink-0 min-w-[120px]">
                              <span className="text-[10px] uppercase tracking-wide text-muted-foreground">Line total</span>
                              <span className="text-sm font-semibold text-foreground tabular-nums">
                                {item.notApplicable ? "—" : formatEur((item.quantity || 0) * (item.unitCostEur || 0))}
                              </span>
                              <span className="text-[10px] text-muted-foreground tabular-nums">
                                {item.quantity || 0} × {formatEur(item.unitCostEur || 0)}
                              </span>
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                              <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground cursor-pointer select-none">
                                <Switch
                                  checked={!!item.notApplicable}
                                  onCheckedChange={(v) => updateItem(item.id, { notApplicable: v })}
                                  aria-label={`Mark ${item.label} as not applicable`}
                                />
                                N/A
                              </label>
                              <Button variant="outline" size="sm" className="h-9 gap-1.5 text-xs" onClick={() => setDetailsForItemId(item.id)}>
                                <Pencil className="h-3 w-3" /> Edit details
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-9 w-9 text-muted-foreground hover:text-destructive"
                                onClick={() => setPendingDeleteId(item.id)}
                                aria-label={`Remove ${item.label} from infrastructure list`}
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </Button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </section>
                  );
                })
              )}

              {/* Equipment contingency */}
              {data.items.some((i) => i.claimed) && (
                <div className="rounded-xl border border-border bg-card shadow-sm p-5 max-w-3xl">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
                    <div>
                      <Label htmlFor="eq-contingency" className="text-xs">Equipment contingency (%)</Label>
                      <EurNumberInput
                        id="eq-contingency"
                        noSymbol
                        value={data.equipmentContingencyPct || 0}
                        min={0}
                        max={100}
                        inputClassName="bg-muted/40 border-border h-9 mt-1"
                        onChange={(n) => { setData({ ...data, equipmentContingencyPct: n }); setDirty(true); }}
                      />
                    </div>
                    <div className="text-sm">
                      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Base subtotal</div>
                      <div className="font-semibold tabular-nums">{formatEur(totals.equipmentBaseEur)}</div>
                    </div>
                    <div className="text-sm">
                      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Contingency amount</div>
                      <div className="font-semibold tabular-nums">{formatEur(totals.equipmentContingencyEur)}</div>
                    </div>
                  </div>
                </div>
              )}
            </TabsContent>

            {/* ── Construction ── */}
            <TabsContent value="construction" className="mt-5">
              <ConstructionForm
                construction={data.construction}
                onChange={(patch) => { setData({ ...data, construction: { ...data.construction, ...patch } }); setDirty(true); }}
                totalEur={totals.constructionEur}
              />
            </TabsContent>

            {/* ── Site ── */}
            <TabsContent value="site" className="mt-5">
              <SiteForm
                data={data}
                onSitePatch={(patch) => { setData({ ...data, site: { ...data.site, ...patch } }); setDirty(true); }}
                totals={totals}
              />
            </TabsContent>
          </Tabs>
        )}
      </div>

      {/* Sticky totals footer */}
      {!loading && (
        <div
          className="sticky bottom-0 border-t border-border bg-card/95 backdrop-blur-sm z-30"
          aria-live="polite"
          aria-atomic="true"
        >
          <div className="max-w-7xl mx-auto px-6 py-3 grid grid-cols-4 gap-6 items-center">
            <TotalSegment label="Site" base={totals.siteBaseEur} contingency={totals.siteContingencyEur} total={totals.siteEur} />
            <TotalSegment label="Construction" base={totals.constructionBaseEur} contingency={totals.constructionContingencyEur} total={totals.constructionEur} />
            <TotalSegment label="Equipment" base={totals.equipmentBaseEur} contingency={totals.equipmentContingencyEur} total={totals.equipmentEur} />
            <div className="text-right">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Grand total · {data.currency ?? "EUR"} · ref. {data.referenceYear ?? new Date().getFullYear()}
              </div>
              <div className="text-lg font-bold text-primary tabular-nums">{formatEur(totals.grandTotalEur)}</div>
            </div>
          </div>
        </div>
      )}

      <SupplierPickerDialog
        open={!!pickerForItemId}
        onOpenChange={(o) => { if (!o) setPickerForItemId(null); }}
        equipmentLabel={activeItemForPicker?.label ?? ""}
        onSelect={handleSupplierSelect}
      />

      {/* Add equipment dialog — pick items to bring into the list */}
      <Dialog open={addPickerOpen} onOpenChange={setAddPickerOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Add infrastructure equipment</DialogTitle>
            <DialogDescription>
              Pick items to add to your site infrastructure list. You can configure cost details after adding.
            </DialogDescription>
          </DialogHeader>
          <div className="relative">
            <Search aria-hidden="true" className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              aria-label="Search equipment"
              placeholder="Search equipment…"
              value={equipmentSearch}
              onChange={(e) => setEquipmentSearch(e.target.value)}
              className="pl-8 h-9 bg-muted/40 border-border"
            />
          </div>
          <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-1">
            {INFRASTRUCTURE_SECTIONS.map((section) => {
                const items = filteredAddItems.filter((i) => i.section === section);
                if (items.length === 0) return null;
                const Icon = SECTION_ICON[section] ?? Building2;
                return (
                  <div key={section}>
                    <div className="flex items-center gap-2 mb-2 px-1">
                      <Icon className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{section}</span>
                    </div>
                    <div className="grid gap-2">
                      {items.map((item) => (
                        <button
                          key={item.equipmentId}
                          type="button"
                          onClick={() => addEquipment(item)}
                          className="flex items-center gap-3 p-3 rounded-lg border border-border bg-background hover:border-primary/50 hover:bg-accent/40 transition-colors text-left"
                        >
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium text-foreground">{item.label}</div>
                            <div className="text-[11px] font-mono text-muted-foreground">{item.equipmentId}</div>
                          </div>
                          <Plus className="h-4 w-4 text-primary shrink-0" />
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            {filteredAddItems.length === 0 && (
              <div className="text-center text-xs text-muted-foreground py-8">
                No equipment matches “{equipmentSearch}”.
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Confirm remove */}
      <AlertDialog
        open={!!pendingDeleteId}
        onOpenChange={(o) => { if (!o) setPendingDeleteId(null); }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove this equipment item?</AlertDialogTitle>
            <AlertDialogDescription>
              {(() => {
                const it = data.items.find((i) => i.id === pendingDeleteId);
                return it
                  ? `“${it.label}” will be removed from this plant's infrastructure list. Cost, manufacturer and notes will be lost.`
                  : "This row will be removed from this plant's infrastructure list.";
              })()}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (!pendingDeleteId) return;
                setData((prev) => ({ ...prev, items: prev.items.filter((i) => i.id !== pendingDeleteId) }));
                setDirty(true);
                setPendingDeleteId(null);
              }}
            >
              Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <InfraItemDetailsDialog
        open={!!detailsForItemId}
        onOpenChange={(o) => { if (!o) setDetailsForItemId(null); }}
        item={data.items.find((i) => i.id === detailsForItemId) ?? null}
        onSave={(patch) => {
          if (!detailsForItemId) return;
          updateItem(detailsForItemId, patch);
        }}
        onOpenProcurement={() => {
          if (!detailsForItemId) return;
          setPickerForItemId(detailsForItemId);
        }}
      />
    </div>
  );
}

/* ── Sticky footer segment ── */
function TotalSegment({ label, base, contingency, total }: { label: string; base: number; contingency: number; total: number }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="text-sm font-semibold tabular-nums">{formatEur(total)}</div>
      {contingency > 0 && (
        <div className="text-[9px] text-muted-foreground tabular-nums">
          base {formatEur(base)} + cont. {formatEur(contingency)}
        </div>
      )}
    </div>
  );
}

/* ── Site & Land form ── */
function SiteForm({
  data,
  onSitePatch,
  totals,
}: {
  data: InfrastructureData;
  onSitePatch: (patch: Partial<InfrastructureData["site"]>) => void;
  totals: ReturnType<typeof computeInfraTotals>;
}) {
  const groups: Array<{
    title: string;
    fields: Array<{ key: keyof InfrastructureData["site"]; label: string; help?: string; noSymbol?: boolean; step?: number; max?: number }>;
  }> = [
    {
      title: "Land",
      fields: [
        { key: "landAreaHa",          label: "Land area (hectares)", noSymbol: true, step: 0.1, help: "Total plot area; drives setbacks, paving and earthworks volumes." },
        { key: "landAcquisitionEur",  label: "Land acquisition",     help: "Purchase price, long lease prepayment, brokerage and transfer taxes." },
      ],
    },
    {
      title: "Surveys & studies",
      fields: [
        { key: "geotechSurveyEur", label: "Geotechnical survey", help: "Boreholes, soil reports — sized before foundation design." },
        { key: "topoSurveyEur",    label: "Topographic survey",  help: "Levels, contours, drainage plan." },
        { key: "eiaStudyEur",      label: "Environmental Impact Assessment", help: "Baseline ecology, air quality, noise studies required for permits." },
      ],
    },
    {
      title: "Permits, preparation & tie-in (outside the fence)",
      fields: [
        { key: "permittingEur",          label: "Permits & authorisations", help: "Construction permit, environmental permit, water abstraction licence." },
        { key: "demolitionEur",          label: "Demolition of existing structures", help: "Removal of any buildings or hardstandings already on the plot." },
        { key: "sitePreparationEur",     label: "Site preparation & earthworks", help: "Clearing, levelling, drainage, perimeter fencing prior to EPC handover." },
        { key: "utilitiesConnectionEur", label: "Utilities connection (grid hookup)", help: "Grid tie-in, water main, gas pipe — *outside the fence*. Internal substation lives on the Construction tab." },
      ],
    },
    {
      title: "Owner's costs",
      fields: [
        { key: "ownersCostsEur",     label: "Owner's costs", help: "Legal, insurance, financing fees, taxes, owner's team during build." },
        { key: "sparesInventoryEur", label: "Spares inventory & first fill", help: "Initial spare-parts stock, catalysts, lubricants, consumables." },
      ],
    },
  ];

  return (
    <div className="space-y-5 max-w-5xl">
      {groups.map((group) => {
        const subtotal = group.fields.reduce((s, f) => s + (Number(data.site[f.key]) || 0), 0);
        return (
          <section key={group.title} className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
            <header className="flex items-center justify-between gap-2 px-5 py-3 border-b border-border bg-muted/40">
              <h3 className="text-sm font-semibold text-foreground">{group.title}</h3>
              {group.title !== "Land" && (
                <span className="text-xs text-muted-foreground tabular-nums">
                  Subtotal <span className="font-semibold text-foreground ml-1">{formatEur(subtotal)}</span>
                </span>
              )}
            </header>
            <div className="p-5 grid grid-cols-1 md:grid-cols-2 gap-x-5 gap-y-4">
              {group.fields.map((f) => (
                <SiteField
                  key={f.key as string}
                  fieldKey={f.key as string}
                  label={f.label}
                  help={f.help}
                  noSymbol={f.noSymbol}
                  step={f.step}
                  max={f.max}
                  value={Number(data.site[f.key]) || 0}
                  onChange={(n) => onSitePatch({ [f.key]: n } as Partial<InfrastructureData["site"]>)}
                />
              ))}
            </div>
          </section>
        );
      })}

      <section className="rounded-xl border border-border bg-card shadow-sm p-5 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
          <div>
            <Label htmlFor="site-contingency" className="text-xs">Site contingency (%)</Label>
            <EurNumberInput
              id="site-contingency"
              noSymbol
              value={data.site.contingencyPct || 0}
              min={0}
              max={100}
              inputClassName="bg-muted/40 border-border h-9 mt-1"
              onChange={(n) => onSitePatch({ contingencyPct: n })}
            />
          </div>
          <div className="text-sm">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Base subtotal</div>
            <div className="font-semibold tabular-nums">{formatEur(totals.siteBaseEur)}</div>
          </div>
          <div className="text-sm">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Contingency amount</div>
            <div className="font-semibold tabular-nums">{formatEur(totals.siteContingencyEur)}</div>
          </div>
        </div>
        <div>
          <Label htmlFor="site-notes" className="text-xs">Notes</Label>
          <Textarea
            id="site-notes"
            value={data.site.notes ?? ""}
            onChange={(e) => onSitePatch({ notes: e.target.value })}
            className="min-h-[70px] bg-muted/40 border-border mt-1"
            placeholder="Assumptions, exclusions, sourcing notes…"
          />
        </div>
        <div className="pt-3 border-t border-border flex items-center justify-between">
          <span className="text-sm text-muted-foreground">Site total (incl. contingency)</span>
          <span className="text-xl font-bold text-primary tabular-nums">{formatEur(totals.siteEur)}</span>
        </div>
      </section>
    </div>
  );
}

function SiteField({
  fieldKey, label, help, noSymbol, step, max, value, onChange,
}: {
  fieldKey: string;
  label: string;
  help?: string;
  noSymbol?: boolean;
  step?: number;
  max?: number;
  value: number;
  onChange: (n: number) => void;
}) {
  const inputId = `sf-${fieldKey}`;
  const helpId = `sf-${fieldKey}-help`;
  return (
    <div>
      <Label htmlFor={inputId} className="text-xs">
        {label}{noSymbol ? "" : " "}<span className="text-muted-foreground font-normal">{noSymbol ? "" : "(EUR)"}</span>
      </Label>
      <EurNumberInput
        id={inputId}
        value={value}
        min={0}
        max={max}
        step={step ?? 1000}
        noSymbol={noSymbol}
        inputClassName="bg-muted/40 border-border h-9 mt-1"
        ariaDescribedBy={help ? helpId : undefined}
        onChange={onChange}
      />
      {help && (
        <p id={helpId} className="text-[10px] text-muted-foreground mt-1 leading-snug">
          {help}
        </p>
      )}
    </div>
  );
}
