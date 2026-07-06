/**
 * ComponentDetailDialog — clean component detail form with
 * top-level access to Ownership & Edit History panels.
 * @version 4
 */
import { useEffect, useMemo, useRef, useState } from "react";
import type { Node, Edge } from "@xyflow/react";
import {
  ArrowLeft,
  Activity,
  Briefcase,
  Clock,
  Database,
  DollarSign,
  Droplets,
  Factory,
  FlaskConical,
  Gauge,
  Layers,
  MapPin,
  MessageSquare,
  Package,
  Settings,
  ShieldCheck,
  Sigma,
  Sparkles,
  Thermometer,
  Timer,
  Users,
} from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

import {
  getCarrierFieldDefs,
  getEquipmentFieldDefs,
  getGateFieldDefs,
  type FieldDef,
} from "./fieldDictionary";
import SectionPanel from "./form/SectionPanel";
import FormFieldControl from "./form/FormFieldControl";
import { useEquipmentEngine } from "@/engine/hooks/useEquationEngine";
import {
  getArchetypeForLabel,
  getParamKeyForField,
} from "@/engine/registry/engineFieldMapping";
import OwnershipRolesPanel from "./OwnershipRolesPanel";
import { logComponentEvent } from "./OwnershipRolesPanel";
import AuditLogPanel from "./AuditLogPanel";
import SupplierPickerDialog, { type SupplierSelection } from "./SupplierPickerDialog";
import { applyProcurementToNode } from "@/lib/procurementSync";
import EquationsTab from "./EquationsTab";
import TeamAlignmentPanel from "./TeamAlignmentPanel";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  node: Node | null;
  onSave: (nodeId: string, data: Record<string, unknown>) => void;
  isCriticalPath?: boolean;
  plantAvailability?: number;
  scheduledOperatingHours?: number;
  /** Full canvas state — required for the Equations tab to enumerate sources */
  allNodes?: Node[];
  allEdges?: Edge[];
  /** Slug of the current plant (used to scope persisted equation configs) */
  plantSlug?: string;
}

function toKey(name: string): string {
  return name
    .replace(/[₂₃⁺⁻]/g, "")
    .replace(/[^a-zA-Z0-9 ]/g, "")
    .split(" ")
    .map((w, i) => (i === 0 ? w.toLowerCase() : w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()))
    .join("");
}

const availabilityFieldNames = new Set([
  "Plant Availability",
  "Scheduled Operating Hours",
]);

const costFieldNames = new Set([
  "Total Installed Capital Cost",
  "Capital Cost Reference Year",
  "Capital Cost Basis",
  "Annual Fixed Operating Cost",
]);

type ActivePanel = "details" | "ownership" | "editHistory" | "alignment";

type SectionKey =
  | "technology"
  | "performance"
  | "operatingConditions"
  | "materials"
  | "configuration"
  | "commercialReference"
  | "cost"
  | "availability";

/** Extra procurement-derived fields, slotted into themed sections. */
const EXTRA_PROCUREMENT_FIELDS: ReadonlyArray<{
  key: string;
  label: string;
  icon: typeof MapPin;
  placeholder: string;
  section: SectionKey;
  readOnly?: boolean;
}> = [
  { key: "country", label: "Country of Origin", icon: MapPin, placeholder: "e.g. Germany", section: "commercialReference" },
  { key: "strategy", label: "Sourcing Strategy", icon: Database, placeholder: "e.g. Best Price", section: "commercialReference", readOnly: true },
  { key: "leadTimeMonths", label: "Lead Time (months)", icon: Clock, placeholder: "e.g. 12", section: "commercialReference" },
  { key: "priceDisplay", label: "Unit Price", icon: Package, placeholder: "e.g. €500/kW", section: "cost" },
  { key: "efficiency", label: "Performance / Efficiency", icon: Gauge, placeholder: "e.g. 4.3 kWh/Nm³", section: "performance" },
  { key: "trl", label: "Technology Readiness Level", icon: ShieldCheck, placeholder: "e.g. 9", section: "technology" },
];

const SECTION_ORDER: SectionKey[] = [
  "technology",
  "performance",
  "operatingConditions",
  "materials",
  "configuration",
  "commercialReference",
  "cost",
  "availability",
];

const SECTION_META: Record<SectionKey, { label: string; icon: typeof Gauge }> = {
  technology: { label: "Technology", icon: Sparkles },
  performance: { label: "Performance", icon: Activity },
  operatingConditions: { label: "Operating Conditions", icon: Thermometer },
  materials: { label: "Materials", icon: FlaskConical },
  configuration: { label: "Configuration", icon: Layers },
  commercialReference: { label: "Commercial Reference", icon: Briefcase },
  cost: { label: "Cost", icon: DollarSign },
  availability: { label: "Availability", icon: Timer },
};

function classifyDictField(name: string): SectionKey {
  if (availabilityFieldNames.has(name)) return "availability";
  if (costFieldNames.has(name)) return "cost";
  const n = name.toLowerCase();
  if (/technology|readiness|\btrl\b|configuration class/.test(n)) return "technology";
  if (/catalyst|membrane|sorbent|solvent|\bmaterial\b|feedstock type/.test(n)) return "materials";
  if (/pressure|temperature|steam to|\boperating\b/.test(n)) return "operatingConditions";
  if (/capacity|efficiency|consumption|conversion|selectivity|yield|production|throughput|degradation|lifetime|recovery|emission/.test(n)) return "performance";
  if (/ratio/.test(n)) return "operatingConditions";
  return "configuration";
}

const ComponentDetailDialog = ({
  open,
  onOpenChange,
  node,
  onSave,
  isCriticalPath,
  plantAvailability,
  scheduledOperatingHours,
  allNodes = [],
  allEdges = [],
  plantSlug = "",
}: Props) => {
  const [formData, setFormData] = useState<Record<string, string>>({});
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    equations: false,
  });
  const [selectedUnits, setSelectedUnits] = useState<Record<string, string>>({});
  const [activePanel, setActivePanel] = useState<ActivePanel>("details");
  const [supplierPickerOpen, setSupplierPickerOpen] = useState(false);
  const initialDataRef = useRef<Record<string, string>>({});

  const nodeLabel = (node?.data?.label as string) || "";
  const nodeType = (node?.type as string) || "";
  const isEquipment = nodeType === "equipment";

  const archetypeId = useMemo(
    () => (isEquipment ? getArchetypeForLabel(nodeLabel) : null),
    [isEquipment, nodeLabel],
  );

  const engine = useEquipmentEngine(
    node?.id ?? "__none__",
    archetypeId ?? "__none__",
    isEquipment ? nodeLabel : undefined,
  );

  const engineActive = isEquipment && !!archetypeId;

  const fields = useMemo(() => {
    if (!node) return [];
    const label = node.data.label as string;
    if (nodeType === "equipment") return getEquipmentFieldDefs(label);
    if (nodeType === "carrier") return getCarrierFieldDefs(label);
    if (nodeType === "gate") return getGateFieldDefs(label);
    return [];
  }, [node, nodeType]);

  useEffect(() => {
    if (!node || !open) return;

    const data: Record<string, string> = {
      label: (node.data.label as string) || "",
      manufacturer: (node.data.manufacturer as string) || "",
      model: (node.data.model as string) || "",
      notes: (node.data.notes as string) || "",
    };

    // Procurement extra fields
    for (const pf of EXTRA_PROCUREMENT_FIELDS) {
      const raw = node.data[pf.key];
      data[pf.key] = raw == null ? "" : String(raw);
    }

    for (const f of fields) {
      const key = toKey(f.name);
      data[key] = (node.data[key] as string) || "";
    }

    // Auto-fill availability fields for critical path equipment
    if (isCriticalPath) {
      data[toKey("Plant Availability")] = plantAvailability != null ? String(plantAvailability) : "";
      data[toKey("Scheduled Operating Hours")] = scheduledOperatingHours != null ? String(scheduledOperatingHours) : "";
    }

    setFormData(data);
    setExpandedSections({ equations: false });
    setSelectedUnits({});
    setActivePanel("details");
    initialDataRef.current = { ...data };
  }, [node, open, fields, isCriticalPath, plantAvailability, scheduledOperatingHours]);

  const isCarrier = nodeType === "carrier";

  const sectionBuckets = useMemo(() => {
    const buckets: Record<SectionKey, FieldDef[]> = {
      technology: [],
      performance: [],
      operatingConditions: [],
      materials: [],
      configuration: [],
      commercialReference: [],
      cost: [],
      availability: [],
    };
    for (const f of fields) buckets[classifyDictField(f.name)].push(f);
    return buckets;
  }, [fields]);

  const procBySection = useMemo(() => {
    const map: Partial<Record<SectionKey, typeof EXTRA_PROCUREMENT_FIELDS[number][]>> = {};
    if (!isEquipment) return map;
    for (const pf of EXTRA_PROCUREMENT_FIELDS) {
      (map[pf.section] ||= []).push(pf);
    }
    return map;
  }, [isEquipment]);

  if (!node) return null;

  const getEngineInfo = (field: FieldDef) => {
    if (!engineActive) return undefined;
    const paramKey = getParamKeyForField(field.name);
    if (!paramKey) return undefined;

    const resolved = engine.parameters[paramKey];
    const meta = engine.getFieldMeta(paramKey);

    if (!resolved && !meta) return undefined;

    return {
      displayValue: resolved?.displayValue ?? "",
      source: resolved?.source ?? "",
      isDerived: resolved?.isDerived ?? false,
      isOverridden: resolved?.isOverridden ?? false,
      isEditable: resolved?.isEditable ?? true,
      allowedUnits: meta?.allowedUnits ?? [],
      selectedUnit: selectedUnits[paramKey] ?? resolved?.unit ?? meta?.canonicalUnit ?? field.unit ?? "",
      onUnitChange: (unit: string) => {
        setSelectedUnits((prev) => ({ ...prev, [paramKey]: unit }));
      },
      onToggleOverride: () => {
        engine.toggleOverride(paramKey);
      },
    };
  };

  const update = (key: string, val: string, field?: FieldDef) => {
    setFormData((prev) => ({ ...prev, [key]: val }));

    if (engineActive && field) {
      const paramKey = getParamKeyForField(field.name);
      if (paramKey && field.type === "number") {
        const numVal = val.trim() ? parseFloat(val) : null;
        const unit = selectedUnits[paramKey]
          ?? engine.parameters[paramKey]?.unit
          ?? field.unit
          ?? "";
        engine.updateField(paramKey, numVal, unit);
      }
    }
  };

  const handleSupplierSelect = (selection: SupplierSelection) => {
    // Build the canonical procurement object via the shared helper so the
    // node receives the full nested record on save (priceEur, plantScaleQty,
    // source: "database", …) — the Project Procurement page reads this.
    const synthetic = applyProcurementToNode(
      { id: node?.id ?? "__synthetic__", type: "equipment", position: { x: 0, y: 0 }, data: { label: nodeLabel } } as any,
      selection,
    );
    const procurementJson = JSON.stringify((synthetic.data as any).procurement ?? null);
    setFormData((prev) => ({
      ...prev,
      manufacturer: selection.manufacturer,
      model: selection.model,
      country: selection.country,
      priceDisplay: selection.priceDisplay,
      efficiency: selection.efficiency,
      leadTimeMonths: String(selection.leadTimeMonths),
      trl: String(selection.trl),
      strategy: selection.strategy,
      __procurementJson: procurementJson,
    }));
    if (node) {
      logComponentEvent(node.id, {
        category: "procurement",
        action: `Procurement updated — ${selection.manufacturer} ${selection.model}`,
        new_value: `${selection.manufacturer} ${selection.model} (${selection.country})`,
        details: `Strategy: ${selection.strategy} · Lead time: ${selection.leadTimeMonths} mo · TRL ${selection.trl} · ${selection.priceDisplay}`,
      });
    }
  };

  const handleSave = () => {
    if (node) {
      const initial = initialDataRef.current;
      const labelFor = (key: string): string => {
        if (key === "label") return "Name";
        if (key === "manufacturer") return "Manufacturer";
        if (key === "model") return "Model / Reference";
        if (key === "notes") return "Notes";
        const proc = EXTRA_PROCUREMENT_FIELDS.find((p) => p.key === key);
        if (proc) return proc.label;
        const dict = fields.find((f) => toKey(f.name) === key);
        return dict ? dict.name : key;
      };
      const skipKeys = new Set(["__procurementJson"]);
      const changed: Array<{ key: string; from: string; to: string }> = [];
      const allKeys = new Set([...Object.keys(initial), ...Object.keys(formData)]);
      for (const k of allKeys) {
        if (skipKeys.has(k)) continue;
        const from = (initial[k] ?? "").toString();
        const to = (formData[k] ?? "").toString();
        if (from !== to) changed.push({ key: k, from, to });
      }
      for (const c of changed) {
        logComponentEvent(node.id, {
          category: "field_edit",
          action: `${labelFor(c.key)} ${c.from && c.to ? "updated" : c.to ? "set" : "cleared"}`,
          old_value: c.from || undefined,
          new_value: c.to || undefined,
        });
      }
    }
    onSave(node.id, formData);
    onOpenChange(false);
  };

  const toggleSection = (section: string) => {
    setExpandedSections((prev) => ({ ...prev, [section]: !prev[section] }));
  };

  const nodeMeta = isEquipment
    ? { label: "Equipment", icon: Settings }
    : isCarrier
      ? { label: "Carrier", icon: Droplets }
      : { label: "Gate", icon: Factory };

  const NodeIcon = nodeMeta.icon;

  const hasAnyProcurement = isEquipment
    && (["manufacturer", "model", ...EXTRA_PROCUREMENT_FIELDS.map((f) => f.key)]
      .some((k) => (formData[k] || "").trim()));

  const countForSection = (key: SectionKey): number => {
    let total = sectionBuckets[key].length;
    if (key === "commercialReference" && isEquipment) total += 2; // manufacturer + model
    total += procBySection[key]?.length ?? 0;
    return total;
  };

  const filledForSection = (key: SectionKey): number => {
    let f = sectionBuckets[key].filter((fld) => (formData[toKey(fld.name)] || "").trim()).length;
    if (key === "commercialReference" && isEquipment) {
      f += ["manufacturer", "model"].filter((k) => (formData[k] || "").trim()).length;
    }
    f += (procBySection[key] ?? []).filter((pf) => (formData[pf.key] || "").trim()).length;
    return f;
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[88vh] p-0 overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-5 border-b border-border bg-card/80 backdrop-blur-sm">
          <DialogHeader>
            <div className="flex items-center justify-between">
              <DialogTitle className="text-base font-semibold flex items-center gap-2.5">
                {activePanel !== "details" && (
                  <button
                    onClick={() => setActivePanel("details")}
                    className="h-7 w-7 rounded-md bg-muted flex items-center justify-center hover:bg-accent transition-colors"
                  >
                    <ArrowLeft className="h-3.5 w-3.5 text-muted-foreground" />
                  </button>
                )}
                <span className="h-8 w-8 rounded-md bg-primary/10 text-primary flex items-center justify-center">
                  <NodeIcon className="h-4 w-4" />
                </span>
                <span className="truncate">
                  {activePanel === "details" && (formData.label || (node.data.label as string))}
                  {activePanel === "ownership" && "Ownership & Roles"}
                  {activePanel === "editHistory" && "History"}
                  {activePanel === "alignment" && "Team Alignment"}
                </span>
                {activePanel === "details" && (
                  <Badge variant="outline" className="text-[10px] shrink-0">
                    {nodeMeta.label}
                  </Badge>
                )}
              </DialogTitle>

              {activePanel === "details" && (
                <div className="flex items-center gap-1.5 shrink-0">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 text-[11px] gap-1.5 text-muted-foreground hover:text-foreground"
                    onClick={() => setActivePanel("alignment")}
                  >
                    <MessageSquare className="h-3 w-3" />
                    Team Alignment
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 text-[11px] gap-1.5 text-muted-foreground hover:text-foreground"
                    onClick={() => setActivePanel("ownership")}
                  >
                    <Users className="h-3 w-3" />
                    Ownership
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 text-[11px] gap-1.5 text-muted-foreground hover:text-foreground"
                    onClick={() => setActivePanel("editHistory")}
                  >
                    <Clock className="h-3 w-3" />
                    History
                  </Button>
                </div>
              )}
            </div>
          </DialogHeader>

          {activePanel === "details" && isEquipment && (
            <div className="mt-3 flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-[11px] gap-2 border-dashed border-primary/40 text-primary hover:bg-primary/5 hover:border-primary"
                onClick={() => setSupplierPickerOpen(true)}
              >
                <Database className="h-3.5 w-3.5" />
                {hasAnyProcurement ? "Update from Procurement Database" : "Fill from Procurement Database"}
              </Button>
              {hasAnyProcurement && (
                <Badge variant="outline" className="h-5 text-[9px] px-1.5 border-success/40 text-success bg-success-soft/40">
                  Procured
                </Badge>
              )}
            </div>
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-h-0 overflow-y-auto">
          {activePanel === "details" && (
            <div className="p-5 space-y-4">
              {SECTION_ORDER.map((key) => {
                const dictFields = sectionBuckets[key];
                const procFields = procBySection[key] ?? [];
                const showManuModel = key === "commercialReference" && isEquipment;
                const totalCount = countForSection(key);
                if (totalCount === 0) return null;
                const meta = SECTION_META[key];
                const labelText = key === "availability" && isCriticalPath
                  ? "Availability (Critical Path)"
                  : meta.label;
                return (
                  <SectionPanel
                    key={key}
                    id={key}
                    label={labelText}
                    icon={meta.icon}
                    count={totalCount}
                    filled={filledForSection(key)}
                    open={!!expandedSections[key]}
                    onToggle={toggleSection}
                  >
                    {key === "availability" && isCriticalPath && (
                      <p className="text-[10px] text-amber-600 dark:text-amber-400 font-medium mb-2 flex items-center gap-1.5">
                        <Gauge className="h-3 w-3" />
                        Inherited from Plant Settings, this equipment is on the critical path
                      </p>
                    )}

                    {showManuModel && (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                        <div className={`rounded-lg border p-2.5 space-y-1.5 ${
                          !formData.manufacturer?.trim() ? "border-warning/40 bg-warning-soft/40" : "border-success/40 bg-success-soft/40"
                        }`}>
                          <div className="flex items-center justify-between">
                            <Label className="text-xs font-medium">Manufacturer</Label>
                            <Badge variant="outline" className="h-4 text-[9px] px-1.5 border-warning text-warning">Required</Badge>
                          </div>
                          <Input
                            value={formData.manufacturer || ""}
                            onChange={(e) => update("manufacturer", e.target.value)}
                            placeholder="e.g. Siemens Energy"
                            className="h-10 text-xs bg-background"
                          />
                        </div>
                        <div className={`rounded-lg border p-2.5 space-y-1.5 ${
                          formData.model?.trim() ? "border-success/40 bg-success-soft/40" : "border-border bg-background"
                        }`}>
                          <Label className="text-xs font-medium">Model / Reference</Label>
                          <Input
                            value={formData.model || ""}
                            onChange={(e) => update("model", e.target.value)}
                            placeholder="e.g. PEM-500"
                            className="h-10 text-xs bg-background"
                          />
                        </div>
                      </div>
                    )}

                    {dictFields.length > 0 && (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {dictFields.map((field) => (
                          <FormFieldControl
                            key={field.name}
                            field={field}
                            value={formData[toKey(field.name)] || ""}
                            onChange={(value) => update(toKey(field.name), value, field)}
                            engineInfo={getEngineInfo(field)}
                            disabled={key === "availability" && isCriticalPath}
                          />
                        ))}
                      </div>
                    )}

                    {procFields.length > 0 && (
                      <div className={`grid grid-cols-1 md:grid-cols-2 gap-3 ${dictFields.length > 0 ? "mt-3" : ""}`}>
                        {procFields.map((pf) => {
                          const PfIcon = pf.icon;
                          const filled = (formData[pf.key] || "").trim();
                          return (
                            <div
                              key={pf.key}
                              className={`rounded-lg border p-2.5 space-y-1.5 ${
                                filled ? "border-success/40 bg-success-soft/40" : "border-border bg-background"
                              }`}
                            >
                              <Label className="text-xs font-medium flex items-center gap-1.5">
                                <PfIcon className="h-3 w-3 text-muted-foreground" />
                                {pf.label}
                                <span className="ml-auto text-[8px] uppercase tracking-wider text-muted-foreground/70">
                                  Procurement
                                </span>
                              </Label>
                              <Input
                                value={formData[pf.key] || ""}
                                onChange={(e) => update(pf.key, e.target.value)}
                                placeholder={pf.placeholder}
                                className="h-10 text-xs bg-background"
                                readOnly={pf.readOnly}
                              />
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </SectionPanel>
                );
              })}

              {/* 5. Equation Module, distinct dynamic panel, visually separated from static parameter sections */}
              {isEquipment && (
                <section className="rounded-xl border border-primary/30 bg-gradient-to-br from-primary/[0.04] via-card to-card overflow-hidden shadow-sm">
                  <button
                    type="button"
                    onClick={() => toggleSection("equations")}
                    className="w-full px-4 py-3 flex items-center gap-3 text-left hover:bg-primary/[0.04] transition-colors border-b border-primary/10"
                  >
                    <span className="h-8 w-8 rounded-md bg-primary/15 text-primary flex items-center justify-center shrink-0 ring-1 ring-primary/20">
                      <Sigma className="h-4 w-4" />
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-foreground">Equation Module</span>
                        <Badge variant="outline" className="h-4 text-[9px] px-1.5 border-primary/40 text-primary">
                          Dynamic
                        </Badge>
                      </div>
                      <p className="text-[10px] text-muted-foreground mt-0.5">
                        Bind formulas to live plant data, recomputes on every change
                      </p>
                    </div>
                    <span className="text-[10px] font-medium text-primary/80">
                      {expandedSections.equations ? "Collapse" : "Configure"}
                    </span>
                  </button>
                  {expandedSections.equations && (
                    <div className="px-4 py-4">
                      <EquationsTab
                        plantSlug={plantSlug}
                        nodeId={node.id}
                        equipmentLabel={nodeLabel}
                        nodes={allNodes}
                        edges={allEdges}
                        plantForm={formData}
                        plantFieldDefs={fields}
                      />
                    </div>
                  )}
                </section>
              )}

              {fields.length === 0 && (
                <div className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                  No field dictionary found for this node; open Team Alignment to discuss assumptions with the team.
                </div>
              )}

            </div>
          )}

          {activePanel === "ownership" && (
            <div className="p-5">
              <OwnershipRolesPanel componentId={node.id} />
            </div>
          )}

          {activePanel === "editHistory" && (
            <div className="p-5">
              <AuditLogPanel componentId={node.id} />
            </div>
          )}

          {activePanel === "alignment" && (
            <div className="p-5 h-full">
              <TeamAlignmentPanel
                componentId={node.id}
                componentLabel={(formData.label || (node.data.label as string)) ?? ""}
                fieldNames={fields.map((f) => f.name)}
              />
            </div>
          )}

        </div>

        {/* Footer */}
        {activePanel === "details" && (
          <div className="p-4 border-t border-border bg-card/80 backdrop-blur-sm flex gap-3">
            <Button variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button className="flex-1" onClick={handleSave}>
              Save Details
            </Button>
          </div>
        )}
      </DialogContent>

      {/* Supplier Picker sub-dialog */}
      {isEquipment && (
        <SupplierPickerDialog
          open={supplierPickerOpen}
          onOpenChange={setSupplierPickerOpen}
          equipmentLabel={nodeLabel}
          onSelect={handleSupplierSelect}
        />
      )}
    </Dialog>
  );
};

export default ComponentDetailDialog;
