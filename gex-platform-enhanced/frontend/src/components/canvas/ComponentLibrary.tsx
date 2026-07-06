import { useState, useMemo, useEffect } from "react";
import { Search, ChevronDown, ChevronRight, Plus, Trash2, X, PanelLeftClose, PanelLeftOpen, Box, Circle, ArrowRightLeft, ShoppingCart } from "lucide-react";
import {
  equipmentDatabase, carrierDatabase, gateDatabase,
  getEquipmentCategories, getCarrierCategories,
  type EquipmentDef, type CarrierDef, type GateDef,
} from "./componentDatabase";
import { getComponentIcon } from "./iconRegistry";
import { INFRASTRUCTURE_HIDE_LABELS } from "@/lib/siteInfrastructure";
import { useAuth } from "@/contexts/AuthContext";
import { loadCustomLibrary, saveCustomLibrary } from "@/lib/customLibrary";
import { toast } from "@/hooks/use-toast";

export interface ComponentItem {
  type: "gate" | "carrier" | "equipment";
  label: string;
  gateType?: "input" | "output";
  dbId?: string;
}

interface Props {
  onCollapse: () => void;
  collapsed: boolean;
  onOpenProcurement?: () => void;
}

type Tab = "equipment" | "carriers" | "gates";

const tabConfig: { key: Tab; label: string; color: string; icon: typeof Box }[] = [
  { key: "equipment", label: "Equipment", color: "bg-primary", icon: Box },
  { key: "carriers", label: "Carriers", color: "bg-success", icon: Circle },
  { key: "gates", label: "Gates", color: "bg-warning", icon: ArrowRightLeft },
];

const ComponentLibrary = ({ onCollapse, collapsed, onOpenProcurement }: Props) => {
  const { user } = useAuth();
  const [search, setSearch] = useState("");
  const [activeTab, setActiveTab] = useState<Tab>("equipment");
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({});
  const [customEquipment, setCustomEquipment] = useState<EquipmentDef[]>([]);
  const [customCarriers, setCustomCarriers] = useState<CarrierDef[]>([]);
  const [customGates, setCustomGates] = useState<GateDef[]>([]);
  const [libraryLoaded, setLibraryLoaded] = useState(false);

  // Load the user's cloud-synced custom library on mount / user change so
  // additions made in one plant appear automatically across all plants.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const lib = await loadCustomLibrary(user?.id);
      if (cancelled) return;
      setCustomEquipment(lib.equipment);
      setCustomCarriers(lib.carriers);
      setCustomGates(lib.gates);
      setLibraryLoaded(true);
    })();
    return () => { cancelled = true; };
  }, [user?.id]);

  // Debounced persistence — push the merged library to cloud + localStorage
  // whenever any custom collection changes.
  useEffect(() => {
    if (!libraryLoaded) return;
    const t = setTimeout(() => {
      saveCustomLibrary(
        { equipment: customEquipment, carriers: customCarriers, gates: customGates },
        user?.id,
      );
    }, 500);
    return () => clearTimeout(t);
  }, [customEquipment, customCarriers, customGates, libraryLoaded, user?.id]);
  const [addingItem, setAddingItem] = useState<Tab | null>(null);
  const [newLabel, setNewLabel] = useState("");
  const [newCategory, setNewCategory] = useState("");
  const [newGateType, setNewGateType] = useState<"input" | "output">("input");

  const toggleSection = (cat: string) => {
    setOpenSections((prev) => ({ ...prev, [cat]: !prev[cat] }));
  };

  const onDragStart = (e: React.DragEvent, item: ComponentItem) => {
    e.dataTransfer.setData("application/reactflow", JSON.stringify(item));
    e.dataTransfer.effectAllowed = "move";
  };

  // Merge DB + custom items. Site-infrastructure equipment is handled in a
  // separate workspace (/canvas/:plantId/infrastructure) and never appears
  // on the process canvas palette.
  const allEquipment = useMemo(
    () => [...equipmentDatabase, ...customEquipment].filter((e) => !INFRASTRUCTURE_HIDE_LABELS.has(e.label)),
    [customEquipment],
  );
  const allCarriers = useMemo(() => [...carrierDatabase, ...customCarriers], [customCarriers]);
  const allGates = useMemo(() => [...gateDatabase, ...customGates], [customGates]);

  const q = search.toLowerCase();

  const handleAdd = () => {
    if (!newLabel.trim()) return;
    if (addingItem === "equipment") {
      if (INFRASTRUCTURE_HIDE_LABELS.has(newLabel.trim())) {
        toast({
          title: "Site infrastructure item",
          description: `"${newLabel.trim()}" belongs to the Site Infrastructure workspace, not the process canvas.`,
          variant: "destructive",
        });
        return;
      }
      setCustomEquipment((prev) => [...prev, { id: `CE${Date.now()}`, label: newLabel.trim(), category: newCategory || "Custom" }]);
    } else if (addingItem === "carriers") {
      setCustomCarriers((prev) => [...prev, { id: `CC${Date.now()}`, label: newLabel.trim(), carrierFunction: "custom", physicalStates: "", category: newCategory || "Custom" }]);
    } else if (addingItem === "gates") {
      setCustomGates((prev) => [...prev, { id: `CG${Date.now()}`, label: newLabel.trim(), gateType: newGateType }]);
    }
    setNewLabel("");
    setNewCategory("");
    setAddingItem(null);
  };

  const removeCustomEquipment = (id: string) => setCustomEquipment((p) => p.filter((e) => e.id !== id));
  const removeCustomCarrier = (id: string) => setCustomCarriers((p) => p.filter((c) => c.id !== id));
  const removeCustomGate = (id: string) => setCustomGates((p) => p.filter((g) => g.id !== id));

  const totalCount = activeTab === "equipment" ? allEquipment.length
    : activeTab === "carriers" ? allCarriers.length : allGates.length;

  /* ═══ Collapsed mini-rail ═══ */
  if (collapsed) {
    return (
      <div className="w-14 border-r border-border bg-card flex flex-col items-center shrink-0">
        <button
          onClick={onCollapse}
          className="w-full py-4 flex flex-col items-center gap-2 text-muted-foreground hover:text-foreground hover:bg-accent/50 transition-colors border-b border-border"
          title="Open Component Library"
        >
          <PanelLeftOpen className="h-5 w-5" />
          <span className="text-[9px] font-semibold uppercase tracking-wider [writing-mode:vertical-lr] rotate-180">
            Library
          </span>
        </button>
      </div>
    );
  }

  /* ═══ Expanded panel ═══ */

  const renderEquipment = () => {
    const categories = [...getEquipmentCategories(), ...(customEquipment.length ? ["Custom"] : [])];
    return categories.map((cat) => {
      const items = allEquipment.filter(
        (e) => e.category === cat && (!q || e.label.toLowerCase().includes(q))
      );
      if (items.length === 0) return null;
      const isOpen = openSections[cat] ?? false;

      return (
        <div key={cat}>
          <button onClick={() => toggleSection(cat)} className="flex w-full items-center gap-2 py-1.5 text-left">
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider flex-1">{cat}</span>
            <span className="text-[9px] text-muted-foreground/60">{items.length}</span>
            {isOpen ? <ChevronDown className="h-3 w-3 text-muted-foreground" /> : <ChevronRight className="h-3 w-3 text-muted-foreground" />}
          </button>
          {isOpen && (
            <div className="space-y-0.5 ml-1 mb-2">
              {items.map((item) => {
                const isCustom = item.id.startsWith("CE");
                const ItemIcon = getComponentIcon("equipment", item.label);
                return (
                  <div
                    key={item.id}
                    draggable
                    onDragStart={(e) => onDragStart(e, { type: "equipment", label: item.label, dbId: item.id })}
                    className="flex items-center gap-1.5 rounded-md border border-border bg-background px-2 py-1.5 text-[11px] font-medium text-card-foreground cursor-grab active:cursor-grabbing hover:bg-accent transition-colors border-l-2 border-l-primary group"
                  >
                    <ItemIcon className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                    <span className="flex-1 truncate">{item.label}</span>
                    <span className="text-[8px] text-muted-foreground/50 font-mono">{item.id}</span>
                    {isCustom && (
                      <button onClick={(e) => { e.stopPropagation(); removeCustomEquipment(item.id); }}
                        className="opacity-0 group-hover:opacity-100 text-destructive hover:text-destructive/80">
                        <Trash2 className="h-3 w-3" />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      );
    });
  };

  const renderCarriers = () => {
    const categories = [...getCarrierCategories(), ...(customCarriers.length ? ["Custom"] : [])];
    return categories.map((cat) => {
      const items = allCarriers.filter(
        (c) => c.category === cat && (!q || c.label.toLowerCase().includes(q))
      );
      if (items.length === 0) return null;
      const isOpen = openSections[`c-${cat}`] ?? false;

      return (
        <div key={cat}>
          <button onClick={() => toggleSection(`c-${cat}`)} className="flex w-full items-center gap-2 py-1.5 text-left">
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider flex-1">{cat}</span>
            <span className="text-[9px] text-muted-foreground/60">{items.length}</span>
            {isOpen ? <ChevronDown className="h-3 w-3 text-muted-foreground" /> : <ChevronRight className="h-3 w-3 text-muted-foreground" />}
          </button>
          {isOpen && (
            <div className="space-y-0.5 ml-1 mb-2">
              {items.map((item) => {
                const isCustom = item.id.startsWith("CC");
                const ItemIcon = getComponentIcon("carrier", item.label);
                return (
                  <div
                    key={item.id}
                    draggable
                    onDragStart={(e) => onDragStart(e, { type: "carrier", label: item.label, dbId: item.id })}
                    className="flex items-center gap-1.5 rounded-md border border-border bg-background px-2 py-1.5 text-[11px] font-medium text-card-foreground cursor-grab active:cursor-grabbing hover:bg-accent transition-colors border-l-2 border-l-success group"
                  >
                    <ItemIcon className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                    <span className="flex-1 truncate">{item.label}</span>
                    <span className="text-[8px] text-muted-foreground/40">{item.physicalStates}</span>
                    {isCustom && (
                      <button onClick={(e) => { e.stopPropagation(); removeCustomCarrier(item.id); }}
                        className="opacity-0 group-hover:opacity-100 text-destructive hover:text-destructive/80">
                        <Trash2 className="h-3 w-3" />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      );
    });
  };

  const renderGates = () => {
    const inputGates = allGates.filter((g) => g.gateType === "input" && (!q || g.label.toLowerCase().includes(q)));
    const outputGates = allGates.filter((g) => g.gateType === "output" && (!q || g.label.toLowerCase().includes(q)));

    const renderGroup = (title: string, items: GateDef[], sectionKey: string) => {
      if (items.length === 0) return null;
      const isOpen = openSections[sectionKey] ?? true;
      return (
        <div>
          <button onClick={() => toggleSection(sectionKey)} className="flex w-full items-center gap-2 py-1.5 text-left">
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider flex-1">{title}</span>
            <span className="text-[9px] text-muted-foreground/60">{items.length}</span>
            {isOpen ? <ChevronDown className="h-3 w-3 text-muted-foreground" /> : <ChevronRight className="h-3 w-3 text-muted-foreground" />}
          </button>
          {isOpen && (
            <div className="space-y-0.5 ml-1 mb-2">
              {items.map((item) => {
                const isCustom = item.id.startsWith("CG");
                const ItemIcon = getComponentIcon("gate", item.label);
                return (
                  <div
                    key={item.id}
                    draggable
                    onDragStart={(e) => onDragStart(e, { type: "gate", label: item.label, gateType: item.gateType, dbId: item.id })}
                    className="flex items-center gap-1.5 rounded-md border border-border bg-background px-2 py-1.5 text-[11px] font-medium text-card-foreground cursor-grab active:cursor-grabbing hover:bg-accent transition-colors border-l-2 border-l-warning group"
                  >
                    <ItemIcon className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                    <span className="flex-1 truncate">{item.label}</span>
                    {isCustom && (
                      <button onClick={(e) => { e.stopPropagation(); removeCustomGate(item.id); }}
                        className="opacity-0 group-hover:opacity-100 text-destructive hover:text-destructive/80">
                        <Trash2 className="h-3 w-3" />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      );
    };

    return (
      <>
        {renderGroup("Input Gates (Supply)", inputGates, "g-input")}
        {renderGroup("Output Gates (Offtake)", outputGates, "g-output")}
      </>
    );
  };

  return (
    <div className="w-72 border-r border-border bg-card flex flex-col h-full shrink-0 transition-all duration-200">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-card-foreground">Component Library</h3>
          <button
            onClick={onCollapse}
            className="h-6 w-6 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            title="Minimize Library"
          >
            <PanelLeftClose className="h-3.5 w-3.5" />
          </button>
        </div>
        <p className="text-[10px] text-muted-foreground">{totalCount} items · Drag to canvas</p>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border">
        {tabConfig.map((t) => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            className={`flex-1 py-2 text-[10px] font-semibold transition-colors relative ${
              activeTab === t.key ? "text-card-foreground" : "text-muted-foreground hover:text-card-foreground"
            }`}
          >
            <span className="flex items-center justify-center gap-1.5">
              <span className={`h-1.5 w-1.5 rounded-full ${t.color}`} />
              {t.label}
            </span>
            {activeTab === t.key && <div className="absolute bottom-0 left-2 right-2 h-0.5 bg-primary rounded-full" />}
          </button>
        ))}
      </div>

      {/* Search */}
      <div className="px-3 py-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <input
            type="text"
            placeholder={`Search ${activeTab}…`}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-8 w-full rounded-md border border-border bg-background pl-8 pr-3 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
      </div>

      {/* Add custom item */}
      <div className="px-3 pb-2">
        {addingItem === activeTab ? (
          <div className="rounded-md border border-primary/30 bg-primary/5 p-2 space-y-1.5">
            <input
              autoFocus
              placeholder="Component name"
              value={newLabel}
              onChange={(e) => setNewLabel(e.target.value)}
              className="h-7 w-full rounded border border-border bg-background px-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              onKeyDown={(e) => e.key === "Enter" && handleAdd()}
            />
            {activeTab !== "gates" && (
              <input
                placeholder="Category (optional)"
                value={newCategory}
                onChange={(e) => setNewCategory(e.target.value)}
                className="h-7 w-full rounded border border-border bg-background px-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              />
            )}
            {activeTab === "gates" && (
              <select
                value={newGateType}
                onChange={(e) => setNewGateType(e.target.value as "input" | "output")}
                className="h-7 w-full rounded border border-border bg-background px-2 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              >
                <option value="input">Input Gate (Supply)</option>
                <option value="output">Output Gate (Offtake)</option>
              </select>
            )}
            <div className="flex gap-1.5">
              <button onClick={handleAdd} className="flex-1 h-7 rounded bg-primary text-primary-foreground text-[10px] font-medium hover:bg-primary/90">Add</button>
              <button onClick={() => setAddingItem(null)} className="h-7 w-7 rounded border border-border flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-accent">
                <X className="h-3 w-3" />
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setAddingItem(activeTab)}
            className="w-full h-7 rounded-md border border-dashed border-border text-[10px] font-medium text-muted-foreground hover:text-foreground hover:border-primary/30 hover:bg-primary/5 transition-colors inline-flex items-center justify-center gap-1"
          >
            <Plus className="h-3 w-3" /> Add Custom {activeTab === "equipment" ? "Equipment" : activeTab === "carriers" ? "Carrier" : "Gate"}
          </button>
        )}
      </div>

      {/* Procurement Database shortcut, only on equipment tab */}
      {activeTab === "equipment" && onOpenProcurement && (
        <div className="px-3 pb-2">
          <button
            onClick={onOpenProcurement}
            className="w-full h-8 rounded-md border border-primary/30 bg-primary/5 text-[11px] font-medium text-primary hover:bg-primary/10 transition-colors inline-flex items-center justify-center gap-1.5"
          >
            <ShoppingCart className="h-3.5 w-3.5" />
            Browse Procurement Database
          </button>
        </div>
      )}

      {/* Item list */}
      <div className="flex-1 overflow-y-auto px-3 pb-3 space-y-0.5">
        {activeTab === "equipment" && renderEquipment()}
        {activeTab === "carriers" && renderCarriers()}
        {activeTab === "gates" && renderGates()}
      </div>
    </div>
  );
};

export default ComponentLibrary;
