/**
 * PlantBuilder — Plant configuration wizard.
 * Persists plant metadata to Lovable Cloud (Supabase plants table)
 * with localStorage as a write-through cache for instant synchronous reads.
 */
import AppNav from "@/components/AppNav";
import UserContextBar from "@/components/UserContextBar";
import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { loadFromStorage, saveToStorage } from "@/hooks/useLocalPersistence";
import SaveConfirmDialog from "@/components/canvas/SaveConfirmDialog";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useUnsavedChangesGuard } from "@/hooks/useUnsavedChangesGuard";
import { useAuth } from "@/contexts/AuthContext";
import { isBackendConfigured } from "@/lib/envGuard";
import { useActivePlantId } from "@/hooks/useProjectContext";

/** Lazy accessor – avoids evaluating the backend client at module-load time */
async function getSupabase() {
  const { supabase } = await import("@/lib/backendClient");
  return supabase;
}
import {
  MapPin,
  Plus,
  Search,
  MoreVertical,
  Users,
  Archive,
  Copy,
  Pencil,
  Trash2,
} from "lucide-react";
import { ChevronDown, ChevronRight, FolderOpen, Layers } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import NewPlantDialog, { type NewPlantCreatePayload } from "@/components/plant/NewPlantDialog";
import { seedInitialCanvas } from "@/lib/seedInitialCanvas";
import {
  publishPlantToEcosystem,
  getPlantPublication,
  unpublishPlantFromEcosystem,
} from "@/lib/ecosystem/userProjects";
import type { ProductionPathway, ProjectStatus } from "@/lib/ecosystem/types";
import { Globe } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { notifyPlantsChanged } from "@/lib/plantStore";

import {
  projectRegistry,
  statusStyles,
  nextIterationNumber,
  stripIterationSuffix,
  stripAnyEmDashSuffix,
  getCollectionDisplayName,
  formatPlantUpdated,
  type ProjectRecord,
  type PlantStatus,
} from "@/lib/projectRegistry";
import { FolderInput, FolderMinus, Check, X as XIcon } from "lucide-react";

const tabs = ["My Plants", "Shared Plants", "Archived"] as const;

/**
 * Strip marketing prefixes from a fuel label so cards show only the
 * canonical molecule name (e.g. "Green Hydrogen" -> "Hydrogen",
 * "e-Methanol" -> "Methanol", "Renewable Ammonia" -> "Ammonia").
 */
function simplifyFuelLabel(raw: string): string {
  if (!raw) return "–";
  return raw
    .split(/\s*\+\s*/)
    .map((part) =>
      part
        .replace(/\b(green|blue|grey|gray|brown|pink|turquoise|renewable|low[- ]carbon|sustainable|bio)\b/gi, "")
        .replace(/\be[-\s]?/gi, "")
        .replace(/\s+/g, " ")
        .trim(),
    )
    .filter(Boolean)
    .join(" + ") || raw;
}

type FuelType = "Green Hydrogen" | "e-Methanol" | "e-Ammonia" | "e-Kerosene" | string;
const fuelTypes: FuelType[] = ["Green Hydrogen", "e-Methanol", "e-Ammonia", "e-Kerosene"];
const statusOptions: { value: PlantStatus; label: string }[] = [
  { value: "concept", label: "Concept" },
  { value: "design", label: "Design" },
  { value: "feasibility", label: "Feasibility" },
  { value: "construction", label: "Construction" },
  { value: "operational", label: "Operational" },
];

/* ── Capacity unit helpers ── */
const CAPACITY_UNITS = [
  "kt H₂/year",
  "kt MeOH/year",
  "kt eFuel/year",
  "kt NH₃/year",
  "MW",
  "GWh/year",
  "t/day",
  "Nm³/h",
] as const;

function defaultCapacityUnit(fuelType: string): string {
  const f = (fuelType || "").toLowerCase();
  if (f.includes("methanol") || f.includes("meoh")) return "kt MeOH/year";
  if (f.includes("ammonia") || f.includes("nh3")) return "kt NH₃/year";
  if (f.includes("hydrogen") || f.includes("h2") || f.includes("h₂")) return "kt H₂/year";
  if (f.includes("kerosene") || f.includes("diesel") || f.includes("efuel") || f.includes("e-fuel")) return "kt eFuel/year";
  return "MW";
}

function parseCapacity(raw: string, fuelType: string): { value: string; unit: string } {
  const txt = (raw || "").trim();
  if (!txt) return { value: "", unit: defaultCapacityUnit(fuelType) };
  const m = txt.match(/^([\d.,]+)\s*(.*)$/);
  if (m) {
    const value = m[1];
    const unit = (m[2] || "").trim() || defaultCapacityUnit(fuelType);
    return { value, unit };
  }
  return { value: txt, unit: defaultCapacityUnit(fuelType) };
}

/** Optional fields that can be toggled on/off in the publication dialog. */
const OPTIONAL_FIELDS: { key: string; label: string; disabled?: boolean; hint?: string }[] = [
  { key: "productionPathway", label: "Production Pathway" },
  { key: "commissioningYear", label: "Commissioning Year" },
  { key: "website", label: "Website / Contact" },
  { key: "offtakers", label: "Offtake Partners" },
  { key: "certifications", label: "Certification Schemes" },
  { key: "technology", label: "Technology / Equipment", disabled: true, hint: "Coming soon, needs equipment normalization." },
];

/* ── Cloud persistence helpers ── */

async function loadPlantsFromCloud(userId: string): Promise<ProjectRecord[] | null> {
  try {
    if (!isBackendConfigured()) return null;
    const sb = await getSupabase();
    const { data, error } = await sb
      .from("plants")
      .select("slug, data, updated_at")
      .eq("user_id", userId);
    if (error || !data || data.length === 0) return null;
    return data.map((row: Record<string, unknown>) => {
      const rec = { ...(row.data as unknown as ProjectRecord) };
      // Row-level updated_at is the source of truth (trigger maintained).
      const rowTs = (row as any).updated_at as string | undefined;
      if (rowTs) rec.updatedAt = rowTs;
      // Drop legacy static "Just now" strings once we have a real timestamp.
      if (rec.updatedAt && (rec.lastEdited || "").trim().toLowerCase() === "just now") {
        delete (rec as any).lastEdited;
      }
      return rec;
    });
  } catch {
    return null;
  }
}

async function savePlantsToCloud(userId: string, plants: ProjectRecord[]) {
  try {
    if (!isBackendConfigured()) return;
    const sb = await getSupabase();
    const rows = plants.map((p) => ({
      user_id: userId,
      slug: p.id,
      data: JSON.parse(JSON.stringify(p)),
    }));
    await sb.from("plants").delete().eq("user_id", userId);
    if (rows.length > 0) {
      await sb.from("plants").insert(rows);
    }
  } catch (err) {
    console.error("[PlantBuilder] Cloud save failed:", err);
  }
}

/**
 * Per-plant upsert. Touches ONLY the given plant's row so other plants'
 * `updated_at` columns (and any consumers that key off them) are never
 * disturbed by an unrelated edit.
 */
async function upsertPlantToCloud(userId: string, plant: ProjectRecord) {
  try {
    if (!isBackendConfigured()) return;
    const sb = await getSupabase();
    await sb.from("plants").upsert(
      { user_id: userId, slug: plant.id, data: JSON.parse(JSON.stringify(plant)) },
      { onConflict: "user_id,slug" },
    );
  } catch (err) {
    console.error("[PlantBuilder] Cloud upsert failed:", err);
  }
}

async function deletePlantFromCloud(userId: string, slug: string) {
  try {
    if (!isBackendConfigured()) return;
    const sb = await getSupabase();
    await sb.from("plants").delete().eq("user_id", userId).eq("slug", slug);
  } catch (err) {
    console.error("[PlantBuilder] Cloud delete failed:", err);
  }
}

function syncToLocalCache(plants: ProjectRecord[]) {
  saveToStorage("plant_list", plants);
  notifyPlantsChanged();
}

const PlantBuilder = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const userId = user?.id || "anonymous";
  const activePlantId = useActivePlantId();
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<typeof tabs[number]>("My Plants");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [showNewPlant, setShowNewPlant] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  // Local plants list — starts from localStorage cache, then cloud overrides
  const [plants, setPlants] = useState<ProjectRecord[]>(() => {
    const saved = loadFromStorage<ProjectRecord[]>("plant_list");
    return saved || [...projectRegistry];
  });

  // Load from cloud on mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const cloudPlants = await loadPlantsFromCloud(userId);
      if (cancelled) return;
      if (cloudPlants && cloudPlants.length > 0) {
        // One-time client-side backfill: legacy rows stored `name` as
        // "${baseName} — ${variantLabel}". Strip the em-dash suffix so the
        // dashboard cards are clean.
        const backfilled: ProjectRecord[] = [];
        const cleaned = cloudPlants.map((p) => {
          const cleanName = stripAnyEmDashSuffix(p.name);
          if (cleanName && cleanName !== p.name) {
            const next = { ...p, name: cleanName };
            backfilled.push(next);
            return next;
          }
          return p;
        });
        setPlants(cleaned);
        syncToLocalCache(cleaned);
        if (backfilled.length > 0) {
          for (const row of backfilled) void upsertPlantToCloud(userId, row);
        }
      } else {
        // First time: seed cloud with defaults
        const defaults = [...projectRegistry];
        await savePlantsToCloud(userId, defaults);
        if (!cancelled) {
          setPlants(defaults);
          syncToLocalCache(defaults);
        }
      }
      setIsLoading(false);
    })();
    return () => { cancelled = true; };
  }, [userId]);

  // Track if plant list has been modified
  const [isDirty, setIsDirty] = useState(false);
  const [showSavePrompt, setShowSavePrompt] = useState(false);
  const saveAction = useRef<"duplicate" | "edit" | "general">("general");
  const pendingNavigation = useRef<string | null>(null);

  /**
   * Persist a targeted change. The caller provides only the plants that
   * actually changed (`upserts`) and/or the slugs that disappear
   * (`removes`); other plants are NEVER re-written, so their cloud
   * `updated_at` (and any UI sync) remains untouched.
   */
  const mutatePlants = useCallback((
    action: "duplicate" | "edit",
    opts: { upserts?: ProjectRecord[]; removes?: string[] },
  ) => {
    const upserts = opts.upserts ?? [];
    const removes = new Set(opts.removes ?? []);
    setPlants((prev) => {
      const byId = new Map(prev.map((p) => [p.id, p] as const));
      for (const u of upserts) byId.set(u.id, u);
      for (const slug of removes) byId.delete(slug);
      const next: ProjectRecord[] = [];
      // Preserve original order, then append truly new records.
      const seen = new Set<string>();
      for (const p of prev) {
        if (removes.has(p.id)) continue;
        const u = byId.get(p.id);
        if (u) { next.push(u); seen.add(p.id); }
      }
      for (const u of upserts) {
        if (!seen.has(u.id)) next.push(u);
      }
      syncToLocalCache(next);
      // Touch only the rows that actually changed.
      for (const u of upserts) void upsertPlantToCloud(userId, u);
      for (const slug of removes) void deletePlantFromCloud(userId, slug);
      return next;
    });
    saveAction.current = action;
    setIsDirty(false);
  }, [userId]);

  /** Stamp a plant as "edited now" without touching siblings. */
  const touch = useCallback((p: ProjectRecord): ProjectRecord => ({
    ...p,
    updatedAt: new Date().toISOString(),
  }), []);

  // Navigation guard — blocks leaving when dirty
  const { proceed, reset } = useUnsavedChangesGuard({
    isDirty,
    onBlock: useCallback((url: string) => {
      pendingNavigation.current = url;
      saveAction.current = "general";
      setShowSavePrompt(true);
    }, []),
  });

  // Edit dialog state
  const [editPlant, setEditPlant] = useState<ProjectRecord | null>(null);
  const [editForm, setEditForm] = useState({
    name: "",
    location: "",
    country: "",
    capacity: "",
    fuelType: "" as FuelType,
    status: "concept" as PlantStatus,
    variantLabel: "",
    /** "" = standalone (new auto group); "__NEW__" = create new named group; else existing groupId */
    collectionChoice: "",
    newCollectionName: "",
  });

  // Inline collection rename state (header of a multi-iteration collection)
  const [renamingGroupId, setRenamingGroupId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  // Per-collection collapsed state (dashboard UX — visibility/access enhancement)
  const [collapsedCollections, setCollapsedCollections] = useState<Set<string>>(new Set());
  const toggleCollectionCollapsed = (gid: string) => {
    setCollapsedCollections((prev) => {
      const next = new Set(prev);
      if (next.has(gid)) next.delete(gid); else next.add(gid);
      return next;
    });
  };

  // Ecosystem-Map publication dialog state
  const [ecoPlant, setEcoPlant] = useState<ProjectRecord | null>(null);
  const [ecoForm, setEcoForm] = useState({
    publish: true,
    owner: "",
    capacityValue: "",
    capacityUnit: "",
    productionPathway: "" as ProductionPathway | "",
    status: "planned" as ProjectStatus,
    country: "",
    commissioningYear: "",
    website: "",
    offtakers: "",
    certifications: "",
    visibleFields: [] as string[],
  });
  const [ecoCurrentKind, setEcoCurrentKind] = useState<"added" | "enriched" | "none">("none");

  // Delete confirmation dialog state
  const [deleteTarget, setDeleteTarget] = useState<ProjectRecord | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  // Auto-open dialog with pre-filled values from Project Siting
  const prefill = useMemo(() => {
    if (searchParams.get("autoOpen") !== "1") return undefined;
    return {
      name: searchParams.get("name") || undefined,
      location: searchParams.get("location") || undefined,
      country: searchParams.get("country") || undefined,
      capacity: searchParams.get("capacity") || undefined,
      fuelType: (searchParams.get("fuelType") as any) || undefined,
    };
  }, [searchParams]);

  useEffect(() => {
    if (prefill) {
      setShowNewPlant(true);
      const next = new URLSearchParams(searchParams);
      next.delete("autoOpen");
      next.delete("name");
      next.delete("location");
      next.delete("country");
      next.delete("capacity");
      next.delete("fuelType");
      setSearchParams(next, { replace: true });
    }
  }, [prefill, setSearchParams, searchParams]);

  const handleArchive = useCallback((plant: ProjectRecord) => {
    mutatePlants("edit", { upserts: [touch({ ...plant, archived: !plant.archived })] });
  }, [mutatePlants, touch]);

  /** Open the destructive-confirm dialog for the chosen plant. */
  const handleDelete = useCallback((plant: ProjectRecord) => {
    setDeleteTarget(plant);
  }, []);

  /** Permanently delete the chosen plant: removes its card, the cloud row, and its canvas JSON. */
  const confirmDelete = useCallback(async () => {
    const plant = deleteTarget;
    if (!plant) return;
    setIsDeleting(true);
    // Remove the card immediately; only this slug's row is deleted from the cloud.
    mutatePlants("edit", { removes: [plant.id] });
    try {
      if (isBackendConfigured()) {
        const sb = await getSupabase();
        // (Row already deleted above via mutatePlants → deletePlantFromCloud.)
        // 1) Remove this exact plant's canvas JSON.
        await sb.storage.from("plant-data").remove([`${plant.id}.json`]);
        // 2) Remove all of this plant's version snapshots (paginated to clear >100).
        let pageOffset = 0;
        // eslint-disable-next-line no-constant-condition
        while (true) {
          const { data: versionFiles } = await sb.storage
            .from("plant-data")
            .list(`versions/${plant.id}`, { limit: 100, offset: pageOffset });
          if (!versionFiles || versionFiles.length === 0) break;
          await sb.storage
            .from("plant-data")
            .remove(versionFiles.map((f: { name: string }) => `versions/${plant.id}/${f.name}`));
          if (versionFiles.length < 100) break;
          pageOffset += 100;
        }
      }
      toast.success(`"${plant.name}" was permanently deleted.`);
    } catch (err) {
      console.error("[delete] Failed to remove cloud canvas data:", err);
      toast.error("Plant card was removed, but cloud cleanup failed. Please retry.");
    } finally {
      setIsDeleting(false);
      setDeleteTarget(null);
    }
  }, [deleteTarget, mutatePlants, userId]);

  const filtered = plants.filter((p) => {
    if (activeTab === "Archived" && !p.archived) return false;
    if (activeTab !== "Archived" && p.archived) return false;
    if (search && !p.name.toLowerCase().includes(search.toLowerCase())) return false;
    if (statusFilter !== "all" && p.status !== statusFilter) return false;
    return true;
  });

  const handleOpen = (plant: ProjectRecord) => {
    navigate(`/canvas/${plant.id}`);
  };

  /**
   * Duplicate = create a new iteration inside the same collection
   * (shared `projectGroupId`) seeded from the LATEST saved canvas of the
   * source plant. The new iteration is otherwise fully isolated — its own
   * slug, its own user-scoped canvas storage, its own equations/finance.
   */
  const handleDuplicate = useCallback(async (plant: ProjectRecord) => {
    const groupId = plant.projectGroupId || plant.id;
    const iterN = nextIterationNumber(groupId, plants);
    // Ensure the slug is unique even if a previous iteration was deleted
    // and recreated with the same number elsewhere.
    let newId = `${groupId}-iter-${iterN}`;
    let collisionBump = iterN;
    while (plants.some((p) => p.id === newId)) {
      collisionBump += 1;
      newId = `${groupId}-iter-${collisionBump}`;
    }
    const variantLabel = `Iteration ${collisionBump}`;
    const baseName = stripIterationSuffix(plant.name);
    const duplicate: ProjectRecord = {
      ...plant,
      id: newId,
      projectGroupId: groupId,
      variantLabel,
      name: `${baseName} — ${variantLabel}`,
      updatedAt: new Date().toISOString(),
    };
    mutatePlants("duplicate", { upserts: [duplicate] });

    try {
      if (!isBackendConfigured()) throw new Error("no backend");
      const sb = await getSupabase();
      // 1) Prefer the user's latest saved canvas (scoped path).
      // 2) Fall back to the unscoped public seed for first-time users
      //    who have never saved.
      const candidates = [
        userId ? `users/${userId}/${plant.id}.json` : null,
        `${plant.id}.json`,
      ].filter(Boolean) as string[];

      let sourceJson: string | null = null;
      for (const path of candidates) {
        const { data: urlData } = sb.storage.from("plant-data").getPublicUrl(path);
        try {
          const resp = await fetch(`${urlData.publicUrl}?t=${Date.now()}`, { cache: "no-store" });
          if (resp.ok) {
            sourceJson = await resp.text();
            console.log(`[duplicate] Seeded ${newId} from ${path}`);
            break;
          }
        } catch { /* try next */ }
      }

      if (sourceJson) {
        const blob = new Blob([sourceJson], { type: "application/json" });
        const destPath = userId ? `users/${userId}/${newId}.json` : `${newId}.json`;
        await sb.storage
          .from("plant-data")
          .upload(destPath, blob, { upsert: true, cacheControl: "0" });
      }
      toast.success(`Created ${variantLabel} of ${baseName}`);
    } catch (err) {
      console.error("[duplicate] Failed to seed iteration canvas:", err);
      toast.error("Iteration created, but canvas seed failed.");
    }
  }, [plants, mutatePlants, userId]);

  /** Open edit dialog for a plant */
  const handleEditOpen = useCallback((plant: ProjectRecord) => {
    setEditPlant(plant);
    setEditForm({
      name: plant.name,
      location: plant.location,
      country: plant.country,
      capacity: plant.capacity,
      fuelType: plant.fuelType,
      status: plant.status,
      variantLabel: plant.variantLabel || "",
      collectionChoice: plant.projectGroupId || plant.id,
      newCollectionName: "",
    });
  }, []);

  /** Save edited plant info (and optional collection re-assignment). */
  const handleEditSave = useCallback(() => {
    if (!editPlant) return;
    // Resolve target collection
    let nextGroupId = editPlant.projectGroupId || editPlant.id;
    let nextCollectionName: string | undefined = editPlant.collectionName;
    if (editForm.collectionChoice === "__NEW__") {
      const name = editForm.newCollectionName.trim();
      nextGroupId = `${editPlant.id}-grp-${Date.now()}`;
      nextCollectionName = name || undefined;
    } else if (editForm.collectionChoice === "__STANDALONE__") {
      nextGroupId = `${editPlant.id}-grp-${Date.now()}`;
      nextCollectionName = undefined;
    } else if (editForm.collectionChoice && editForm.collectionChoice !== (editPlant.projectGroupId || editPlant.id)) {
      nextGroupId = editForm.collectionChoice;
      // Inherit collection name from any existing member
      const sibling = plants.find((p) => p.projectGroupId === nextGroupId && (p.collectionName || "").trim());
      nextCollectionName = sibling?.collectionName;
    }
    const updated: ProjectRecord = touch({
      ...editPlant,
      name: editForm.name.trim() || editPlant.name,
      location: editForm.location.trim() || editPlant.location,
      country: editForm.country.trim() || editPlant.country,
      capacity: editForm.capacity.trim() || editPlant.capacity,
      fuelType: editForm.fuelType || editPlant.fuelType,
      status: editForm.status,
      variantLabel: editForm.variantLabel.trim() || editPlant.variantLabel,
      projectGroupId: nextGroupId,
      collectionName: nextCollectionName,
    });
    mutatePlants("edit", { upserts: [updated] });
    setEditPlant(null);
  }, [editPlant, editForm, plants, mutatePlants, touch]);

  /**
   * Remove a plant from its current collection: assigns it a fresh unique
   * group id and clears the iteration suffix from its display name. Only
   * this plant's row is touched; siblings remain untouched.
   */
  const handleRemoveFromCollection = useCallback((plant: ProjectRecord) => {
    const newGroupId = `${plant.id}-grp-${Date.now()}`;
    const updated: ProjectRecord = touch({
      ...plant,
      projectGroupId: newGroupId,
      collectionName: undefined,
      variantLabel: "Plant variation #1",
      name: stripAnyEmDashSuffix(plant.name) || plant.name,
    });
    mutatePlants("edit", { upserts: [updated] });
    toast.success(`"${updated.name}" removed from its collection.`);
  }, [mutatePlants, touch]);

  /** Rename a collection: writes `collectionName` to every member of the group. */
  const handleRenameCollection = useCallback((groupId: string, newName: string) => {
    const name = newName.trim();
    const members = plants.filter((p) => (p.projectGroupId || p.id) === groupId);
    if (members.length === 0) return;
    const upserts = members.map((m) => touch({ ...m, collectionName: name || undefined }));
    mutatePlants("edit", { upserts });
    setRenamingGroupId(null);
    toast.success(name ? `Collection renamed to "${name}".` : "Collection name cleared.");
  }, [plants, mutatePlants, touch]);

  /** Open the Ecosystem Map publication dialog for a plant. */
  const handleEcoOpen = useCallback((plant: ProjectRecord) => {
    const cur = getPlantPublication({
      slug: plant.id,
      name: plant.name,
      lat: plant.lat,
      lng: plant.lng,
      country: plant.country,
      fuelType: plant.fuelType,
      capacity: plant.capacity,
    });
    setEcoCurrentKind(cur.kind);
    const seed = cur.enrichment ?? cur.added;
    const rawCap = (cur.enrichment?.capacity ?? cur.added?.capacity ?? plant.capacity) || "";
    const parsed = (cur.enrichment?.capacityValue && cur.enrichment?.capacityUnit)
      ? { value: cur.enrichment.capacityValue, unit: cur.enrichment.capacityUnit }
      : parseCapacity(rawCap, plant.fuelType);
    setEcoForm({
      publish: cur.kind !== "none",
      owner: (cur.added?.owner ?? cur.enrichment?.owner ?? user?.company ?? "") || "",
      capacityValue: parsed.value,
      capacityUnit: parsed.unit,
      productionPathway: (seed?.productionPathway ?? "") as ProductionPathway | "",
      status: (cur.enrichment?.status as ProjectStatus) ?? (plant.status as ProjectStatus) ?? "planned",
      country: (cur.enrichment?.country ?? plant.country) || "",
      commissioningYear: cur.enrichment?.commissioningYear ?? (plant.codYear ? String(plant.codYear) : ""),
      website: cur.enrichment?.website ?? "",
      offtakers: cur.enrichment?.offtakers ?? "",
      certifications: cur.enrichment?.certifications ?? "",
      visibleFields: cur.enrichment?.visibleFields ?? ["productionPathway"],
    });
    setEcoPlant(plant);
  }, [user]);

  /** Save the Ecosystem Map publication settings. */
  const handleEcoSave = useCallback(() => {
    if (!ecoPlant) return;
    const base = {
      slug: ecoPlant.id,
      name: ecoPlant.name,
      lat: ecoPlant.lat,
      lng: ecoPlant.lng,
      country: ecoForm.country || ecoPlant.country,
      fuelType: ecoPlant.fuelType,
      capacity: ecoForm.capacityValue
        ? `${ecoForm.capacityValue}${ecoForm.capacityUnit ? ` ${ecoForm.capacityUnit}` : ""}`
        : ecoPlant.capacity,
      capacityValue: ecoForm.capacityValue || undefined,
      capacityUnit: ecoForm.capacityUnit || undefined,
      owner: ecoForm.owner || undefined,
      pathway: ecoForm.productionPathway || undefined,
      maturityStage: ecoForm.status,
      commissioningYear: ecoForm.commissioningYear || undefined,
      website: ecoForm.website || undefined,
      offtakers: ecoForm.offtakers || undefined,
      certifications: ecoForm.certifications || undefined,
      visibleFields: ecoForm.visibleFields,
    };
    if (!ecoForm.publish) {
      unpublishPlantFromEcosystem(base);
      toast.success("Plant removed from the Ecosystem Map.");
      setEcoPlant(null);
      return;
    }
    // Enforce: at most ONE published variation per collection. Map markers
    // represent a real-world project, not a design iteration. Before we
    // publish this variation, unpublish every sibling iteration in the
    // same collection (same projectGroupId).
    const groupId = ecoPlant.projectGroupId || ecoPlant.id;
    let unpublishedSiblings = 0;
    for (const sib of plants) {
      if (sib.id === ecoPlant.id) continue;
      const sibGroup = sib.projectGroupId || sib.id;
      if (sibGroup !== groupId) continue;
      const sibState = getPlantPublication({
        slug: sib.id,
        name: sib.name,
        lat: sib.lat,
        lng: sib.lng,
        country: sib.country,
        fuelType: sib.fuelType,
        capacity: sib.capacity,
      });
      if (sibState.kind !== "none") {
        unpublishPlantFromEcosystem({
          slug: sib.id,
          name: sib.name,
          lat: sib.lat,
          lng: sib.lng,
          country: sib.country,
          fuelType: sib.fuelType,
          capacity: sib.capacity,
        });
        unpublishedSiblings += 1;
      }
    }
    const result = publishPlantToEcosystem(base);
    if (result.kind === "added") {
      toast.success("Ecosystem Map updated (new marker).", { description: result.reason });
    } else if (result.kind === "enriched") {
      toast.success(`Enriched via ${result.rule ?? "match"} rule.`, { description: result.reason });
    } else {
      toast.message("Skipped, nothing to publish.", { description: result.reason });
    }
    if (unpublishedSiblings > 0) {
      toast.message(
        `Replaced ${unpublishedSiblings} other variation${unpublishedSiblings > 1 ? "s" : ""} on the map.`,
        { description: "Only one variation per plant can be published to the public Ecosystem Map." },
      );
    }
    setEcoPlant(null);
  }, [ecoPlant, ecoForm, plants]);

  /** Map a free-text maturity stage to the closest PlantStatus card badge. */
  const mapMaturityToStatus = (stage: string): PlantStatus => {
    const s = stage.toLowerCase();
    if (s.includes("operating") || s.includes("commission")) return "operational";
    if (s.includes("construction")) return "construction";
    if (s.includes("feasibility") || s.includes("feed") || s.includes("permit") || s.includes("fid")) return "feasibility";
    if (s.includes("design")) return "design";
    return "concept";
  };

  /** Called by NewPlantDialog after the form is submitted. Creates a card
   *  and persists it to the cloud BEFORE navigation, so the plant survives reloads. */
  const handleCreatePlant = useCallback(async (payload: NewPlantCreatePayload): Promise<string> => {
    // Build a ProjectRecord from the form. Use a deterministic, unique slug.
    let baseSlug = payload.slug || `plant-${Date.now()}`;
    let uniqueSlug = baseSlug;
    let n = 2;
    while (plants.some((p) => p.id === uniqueSlug)) {
      uniqueSlug = `${baseSlug}-${n++}`;
    }
    const codYear = parseInt(payload.expectedCod, 10);
    const newPlant: ProjectRecord = {
      id: uniqueSlug,
      projectGroupId: uniqueSlug,
      variantLabel: "Plant variation #1",
      name: payload.name || "Untitled Plant",
      subtitle: payload.fuelType || "–",
      location: payload.location || "–",
      country: (payload.country || "").toLowerCase(),
      status: mapMaturityToStatus(payload.maturityStage || ""),
      fuelType: payload.fuelType || "–",
      capacity: payload.capacity || "–",
      capacityMW: 0,
      codYear: Number.isFinite(codYear) ? codYear : new Date().getFullYear() + 3,
      updatedAt: new Date().toISOString(),
      owned: true,
      lat: Number.isFinite(payload.latitude as number) ? (payload.latitude as number) : 0,
      lng: Number.isFinite(payload.longitude as number) ? (payload.longitude as number) : 0,
      brandHsl: "174 60% 40%",
    };
    const next = [...plants, newPlant];
    setPlants(next);
    syncToLocalCache(next);
    // Only insert the newly created row; do NOT touch siblings.
    await upsertPlantToCloud(userId, newPlant);
    // Seed the initial canvas with one carrier per product wired to the
    // Offtake Market gate so the canvas isn't empty on first open.
    await seedInitialCanvas(uniqueSlug, payload.products, 8760, userId);

    // Publish the new plant to the Ecosystem Map (only when the user opted in).
    // - Matches an existing verified project by name or proximity -> enriches it
    //   with non-sensitive fields (capacity, pathway, status, owner).
    // - Otherwise (and when coords were supplied) adds a new map marker.
    if (payload.publishToEcosystem === false) {
      return uniqueSlug;
    }
    try {
      const result = publishPlantToEcosystem({
        slug: uniqueSlug,
        name: newPlant.name,
        lat: newPlant.lat,
        lng: newPlant.lng,
        country: payload.country,
        fuelType: payload.fuelType,
        capacity: payload.capacity,
        owner: payload.companyName,
        pathway: payload.primaryPathway,
        maturityStage: payload.maturityStage,
      });
      if (result.kind === "added") {
        toast.success("Plant published to the Ecosystem Map.", { description: result.reason });
      } else if (result.kind === "enriched") {
        toast.success(`Linked via ${result.rule ?? "match"} rule.`, { description: result.reason });
      } else if (result.reason) {
        toast.message("Plant not published.", { description: result.reason });
      }
    } catch (err) {
      console.warn("[PlantBuilder] Ecosystem publish failed:", err);
    }

    return uniqueSlug;
  }, [plants, userId]);

  const inputClass =
    "w-full h-9 rounded-lg border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring";

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <AppNav rightContent={<UserContextBar />} />

      {/* Page content */}
      <div className="mx-auto max-w-7xl px-6 py-6 space-y-6">
        {/* Title row */}
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold text-foreground">Plant Builder</h2>
            <p className="text-sm text-muted-foreground">Manage your plants, shared models, and templates.</p>
          </div>
        </div>

        {/* Tabs + filters */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex rounded-lg border border-border bg-muted p-0.5 gap-0.5">
            {tabs.map((tab) => {
              const count = tab === "My Plants" ? plants.filter((p) => !p.archived).length : tab === "Archived" ? plants.filter((p) => p.archived).length : 0;
              return (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all whitespace-nowrap ${
                    activeTab === tab
                      ? "bg-card text-card-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {tab} {count > 0 && `(${count})`}
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search plants"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="h-9 w-52 rounded-lg border border-border bg-card pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              />
            </div>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="h-9 rounded-lg border border-border bg-card px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            >
              <option value="all">All statuses</option>
              <option value="concept">Concept</option>
              <option value="design">Design</option>
              <option value="feasibility">Feasibility</option>
              <option value="construction">Construction</option>
              <option value="operational">Operational</option>
            </select>
          </div>
        </div>

        {/* Loading state */}
        {isLoading && (
          <div className="rounded-lg border border-border bg-card p-12 text-center">
            <p className="text-sm text-muted-foreground">Loading plants…</p>
          </div>
        )}

        {/* Plant cards — grouped by collection (projectGroupId) */}
        {!isLoading && activeTab === "My Plants" && (() => {
          // Preserve insertion order of collections by first-seen index.
          const order: string[] = [];
          const groupsMap = new Map<string, ProjectRecord[]>();
          for (const p of filtered) {
            const gid = p.projectGroupId || p.id;
            if (!groupsMap.has(gid)) { groupsMap.set(gid, []); order.push(gid); }
            groupsMap.get(gid)!.push(p);
          }
          // Sort each group by creation order (slug asc), then we use
          // updatedAt to surface "most recently edited" inside the list.
          for (const arr of groupsMap.values()) {
            arr.sort((a, b) => a.id.localeCompare(b.id));
          }

          const ecoStatusFor = (plant: ProjectRecord) =>
            getPlantPublication({
              slug: plant.id,
              name: plant.name,
              lat: plant.lat,
              lng: plant.lng,
              country: plant.country,
              fuelType: plant.fuelType,
              capacity: plant.capacity,
            });

          const mostRecentlyEdited = (members: ProjectRecord[]) =>
            [...members].sort((a, b) => {
              const ta = Date.parse(a.updatedAt || "") || 0;
              const tb = Date.parse(b.updatedAt || "") || 0;
              return tb - ta;
            })[0];

          const renderSingleCard = (plant: ProjectRecord) => {
              const status = statusStyles[plant.status];
              const isActive = plant.id === activePlantId;
              const hasCoords = Number.isFinite(plant.lat) && Number.isFinite(plant.lng) && (plant.lat !== 0 || plant.lng !== 0);
              const cleanFuel = simplifyFuelLabel(plant.fuelType);
              const ecoPub = ecoStatusFor(plant);
              const displayCapacity = plant.capacity && plant.capacity.trim() && plant.capacity !== "–" ? plant.capacity : "";
              const ruleLabel = ecoPub.rule ? ` (${ecoPub.rule})` : "";
              const ecoBadge =
                ecoPub.kind === "added"
                  ? {
                      label: "Map: Added",
                      cls: "bg-emerald-500/10 text-emerald-600 border-emerald-500/30",
                      title: ecoPub.reason ?? "Published as a new marker on the Ecosystem Map.",
                    }
                  : ecoPub.kind === "enriched"
                  ? {
                      label: `Map: Enriched${ruleLabel}`,
                      cls: "bg-sky-500/10 text-sky-600 border-sky-500/30",
                      title: ecoPub.reason ?? "Linked to an existing verified project, non-sensitive fields enriched.",
                    }
                  : {
                      label: "Map: Skipped",
                      cls: "bg-muted text-muted-foreground border-border",
                      title: ecoPub.reason ?? (hasCoords
                        ? "Not published. Open the Ecosystem Map dialog to publish this plant."
                        : "Not published, missing coordinates."),
                    };
              // Title = collection display name (clean, no em dash). The
              // variation label is the small tag above.
              const cardTitle = getCollectionDisplayName([plant]);
              return (
                <div
                  key={plant.id}
                  className={`rounded-lg border bg-card p-5 space-y-3 transition-shadow hover:shadow-md ${
                    isActive ? "border-primary ring-1 ring-primary/20" : "border-border"
                  }`}
                >
                  <span className="inline-block text-[10px] font-semibold uppercase tracking-wide text-primary/80">
                    {plant.variantLabel || "Plant variation"}
                  </span>
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="text-sm font-semibold text-card-foreground leading-tight">{cardTitle}</h3>
                      <span className="text-[11px] text-muted-foreground">{plant.location}</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`text-[10px] font-semibold rounded px-2 py-0.5 ${status.bg} ${status.text}`}>
                      {status.label}
                    </span>
                    {cleanFuel && cleanFuel !== "–" && (
                      <>
                        <span className="text-[10px] text-muted-foreground">·</span>
                        <span className="text-[10px] text-muted-foreground">{cleanFuel}</span>
                      </>
                    )}
                    {displayCapacity && (
                      <>
                        <span className="text-[10px] text-muted-foreground">·</span>
                        <span className="text-[10px] font-mono text-muted-foreground">{displayCapacity}</span>
                      </>
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={() => handleEcoOpen(plant)}
                    title={ecoBadge.title}
                    className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-medium transition-colors hover:opacity-80 ${ecoBadge.cls}`}
                  >
                    <Globe className="h-2.5 w-2.5" />
                    {ecoBadge.label}
                  </button>

                  <p className="text-[10px] text-muted-foreground">Last edited {formatPlantUpdated(plant)}</p>

                  <div className="flex items-center gap-2 pt-1 border-t border-border">
                    <button
                      onClick={() => handleOpen(plant)}
                      className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90"
                    >
                      Open
                    </button>
                    <button className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
                      <Users className="h-3 w-3" />
                      Share
                    </button>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <button className="ml-auto inline-flex items-center justify-center rounded-md border border-border h-7 w-7 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
                          <MoreVertical className="h-3.5 w-3.5" />
                        </button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem className="text-xs" onClick={() => handleEditOpen(plant)}>
                          <Pencil className="h-3 w-3 mr-2" /> Edit Info
                        </DropdownMenuItem>
                        <DropdownMenuItem className="text-xs" onClick={() => handleEcoOpen(plant)}>
                          <Globe className="h-3 w-3 mr-2" /> Ecosystem Map…
                        </DropdownMenuItem>
                        <DropdownMenuItem className="text-xs" onClick={() => handleDuplicate(plant)}>
                          <Copy className="h-3 w-3 mr-2" /> New variation
                        </DropdownMenuItem>
                        <DropdownMenuItem className="text-xs" onClick={() => handleEditOpen(plant)}>
                          <FolderInput className="h-3 w-3 mr-2" /> Move to collection…
                        </DropdownMenuItem>
                        {(plant.projectGroupId && plant.projectGroupId !== plant.id) && (
                          <DropdownMenuItem className="text-xs" onClick={() => handleRemoveFromCollection(plant)}>
                            <FolderMinus className="h-3 w-3 mr-2" /> Remove from collection
                          </DropdownMenuItem>
                        )}
                        <DropdownMenuItem className="text-xs" onClick={() => handleArchive(plant)}>
                          <Archive className="h-3 w-3 mr-2" /> {plant.archived ? "Unarchive" : "Archive"}
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          className="text-xs text-destructive focus:text-destructive"
                          onClick={() => handleDelete(plant)}
                        >
                          <Trash2 className="h-3 w-3 mr-2" /> Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>
              );
          };

          /**
           * Collection header — full-width band that groups variation cards
           * belonging to the same projectGroupId. Header supports inline
           * rename + "New variation" + ⋯ menu. The actual variation cards
           * are rendered with renderSingleCard so the per-card UI stays
           * identical to the standalone case.
           */
          const renderCollectionSection = (gid: string, members: ProjectRecord[]) => {
            const baseName = getCollectionDisplayName(members);
            const latest = mostRecentlyEdited(members);
            const isRenaming = renamingGroupId === gid;
            const isCollapsed = collapsedCollections.has(gid);
            // Summary intel for at-a-glance visibility
            const publishedMember = members.find((m) => {
              const s = ecoStatusFor(m);
              return s.kind === "added" || s.kind === "enriched";
            });
            const statusCounts = members.reduce<Record<string, number>>((acc, m) => {
              const lbl = statusStyles[m.status]?.label || String(m.status);
              acc[lbl] = (acc[lbl] || 0) + 1;
              return acc;
            }, {});
            const fuelSet = Array.from(new Set(members.map((m) => simplifyFuelLabel(m.fuelType)).filter((f) => f && f !== "–")));
            return (
              <section
                key={gid}
                className="col-span-full rounded-lg border border-border/60 bg-muted/20 border-l-[3px] border-l-primary/60 p-4 space-y-3"
              >
                {/* Collection header */}
                <div className="flex items-center gap-2 flex-wrap">
                  <button
                    type="button"
                    onClick={() => toggleCollectionCollapsed(gid)}
                    aria-label={isCollapsed ? "Expand collection" : "Collapse collection"}
                    className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-accent"
                  >
                    {isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  </button>
                  <FolderOpen className="h-4 w-4 text-primary shrink-0" />
                  <div className="flex-1 min-w-0">
                    {isRenaming ? (
                      <div className="flex items-center gap-1.5 max-w-md">
                        <input
                          autoFocus
                          value={renameValue}
                          onChange={(e) => setRenameValue(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") handleRenameCollection(gid, renameValue);
                            if (e.key === "Escape") setRenamingGroupId(null);
                          }}
                          className="h-8 w-full rounded-md border border-border bg-background px-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                          maxLength={80}
                        />
                        <button
                          type="button"
                          onClick={() => handleRenameCollection(gid, renameValue)}
                          className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border bg-card text-muted-foreground hover:text-foreground hover:bg-accent"
                          title="Save"
                        >
                          <Check className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => setRenamingGroupId(null)}
                          className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border bg-card text-muted-foreground hover:text-foreground hover:bg-accent"
                          title="Cancel"
                        >
                          <XIcon className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => toggleCollectionCollapsed(gid)}
                        className="flex items-center gap-2 min-w-0 text-left group"
                        title={isCollapsed ? "Expand collection" : "Collapse collection"}
                      >
                        <h3 className="text-sm font-semibold text-foreground truncate group-hover:text-primary transition-colors">{baseName}</h3>
                        <span className="shrink-0 inline-flex items-center gap-1 text-[10px] font-medium text-muted-foreground rounded-full border border-border/60 bg-card px-2 py-0.5">
                          <Layers className="h-2.5 w-2.5" />
                          {members.length} variation{members.length === 1 ? "" : "s"}
                        </span>
                        {publishedMember ? (
                          <span
                            className="shrink-0 inline-flex items-center gap-1 text-[10px] font-medium rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-600 px-2 py-0.5"
                            title={`Published variation on the Ecosystem Map: ${publishedMember.variantLabel || "—"}`}
                          >
                            <Globe className="h-2.5 w-2.5" />
                            On map: {publishedMember.variantLabel || "variation"}
                          </span>
                        ) : (
                          <span className="shrink-0 text-[10px] font-medium text-muted-foreground rounded-full border border-border/60 bg-card px-2 py-0.5">
                            Not on map
                          </span>
                        )}
                      </button>
                    )}
                    {!isRenaming && (
                      <div className="mt-1 flex items-center gap-2 flex-wrap text-[10px] text-muted-foreground">
                        {Object.entries(statusCounts).map(([lbl, n]) => (
                          <span key={lbl} className="inline-flex items-center gap-1">
                            <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50" />
                            {n} {lbl}
                          </span>
                        ))}
                        {fuelSet.length > 0 && (
                          <span className="truncate">· {fuelSet.join(", ")}</span>
                        )}
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => handleDuplicate(latest)}
                    className="inline-flex items-center gap-1 rounded-md border border-border bg-card px-2.5 py-1 text-xs font-medium text-muted-foreground hover:text-primary hover:border-primary/40"
                  >
                    <Plus className="h-3 w-3" /> New variation
                  </button>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-border bg-card text-muted-foreground hover:text-foreground hover:bg-accent">
                        <MoreVertical className="h-3.5 w-3.5" />
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem className="text-xs" onClick={() => { setRenamingGroupId(gid); setRenameValue(baseName); }}>
                        <Pencil className="h-3 w-3 mr-2" /> Rename collection
                      </DropdownMenuItem>
                      <DropdownMenuItem className="text-xs" onClick={() => handleDuplicate(latest)}>
                        <Copy className="h-3 w-3 mr-2" /> New variation from latest
                      </DropdownMenuItem>
                      <DropdownMenuItem className="text-xs" onClick={() => toggleCollectionCollapsed(gid)}>
                        {isCollapsed ? <ChevronDown className="h-3 w-3 mr-2" /> : <ChevronRight className="h-3 w-3 mr-2" />}
                        {isCollapsed ? "Expand" : "Collapse"}
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>

                {/* Member variation cards (hidden when collapsed) */}
                {!isCollapsed && (
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 items-start">
                    {members.map((m) => renderSingleCard(m))}
                  </div>
                )}
                {isCollapsed && (
                  <div className="flex items-center gap-2 flex-wrap pl-9">
                    {members.map((m) => {
                      const isPub = publishedMember?.id === m.id;
                      return (
                        <button
                          key={m.id}
                          type="button"
                          onClick={() => handleOpen(m)}
                          className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] font-medium transition-colors ${
                            isPub
                              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 hover:bg-emerald-500/15"
                              : "border-border bg-card text-muted-foreground hover:text-foreground hover:bg-accent"
                          }`}
                          title={`Open ${m.variantLabel || "variation"}`}
                        >
                          {isPub && <Globe className="h-2.5 w-2.5" />}
                          {m.variantLabel || "Variation"}
                        </button>
                      );
                    })}
                  </div>
                )}
              </section>
            );
          };

          return (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 items-start">
              {order.map((gid) => {
                const members = groupsMap.get(gid)!;
                if (members.length === 1) return renderSingleCard(members[0]);
                return renderCollectionSection(gid, members);
              })}
              {/* New plant card — always available */}
              <button
                onClick={() => setShowNewPlant(true)}
                className="rounded-lg border-2 border-dashed border-border bg-card/50 p-5 flex flex-col items-center justify-center gap-2 text-muted-foreground transition-colors hover:border-primary hover:text-primary min-h-[200px]"
              >
                <Plus className="h-8 w-8" />
                <span className="text-sm font-medium">Create New Plant</span>
                <span className="text-[11px]">Start from scratch or use a template</span>
              </button>
            </div>
          );
        })()}

        {!isLoading && activeTab === "Archived" && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.length === 0 ? (
              <div className="col-span-full rounded-lg border border-border bg-card p-12 text-center">
                <p className="text-sm text-muted-foreground">No archived plants yet.</p>
              </div>
            ) : filtered.map((plant) => {
              const status = statusStyles[plant.status];
              return (
                <div key={plant.id} className="rounded-lg border border-border bg-card p-5 space-y-3 opacity-70">
                  <div>
                    <h3 className="text-sm font-semibold text-card-foreground leading-tight">{plant.name}</h3>
                    <span className="text-[11px] text-muted-foreground">{plant.location}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-[10px] font-semibold rounded px-2 py-0.5 ${status.bg} ${status.text}`}>{status.label}</span>
                    <span className="text-[10px] text-muted-foreground">{simplifyFuelLabel(plant.fuelType)}</span>
                  </div>
                  <div className="flex justify-end pt-1 border-t border-border">
                    <button
                      onClick={() => handleArchive(plant)}
                      className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
                    >
                      <Archive className="h-3 w-3" /> Unarchive
                    </button>
                    <button
                      onClick={() => handleDelete(plant)}
                      className="ml-2 inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium text-destructive hover:bg-destructive/10"
                    >
                      <Trash2 className="h-3 w-3" /> Delete
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {!isLoading && activeTab === "Shared Plants" && (
          <div className="rounded-lg border border-border bg-card p-12 text-center">
            <p className="text-sm text-muted-foreground">No shared plants yet.</p>
          </div>
        )}
      </div>

      <NewPlantDialog
        open={showNewPlant}
        onOpenChange={setShowNewPlant}
        initialValues={prefill}
        onCreate={handleCreatePlant}
      />

      {/* Edit Plant Dialog */}
      <Dialog open={!!editPlant} onOpenChange={(open) => { if (!open) setEditPlant(null); }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-base">Edit Plant Information</DialogTitle>
            <DialogDescription className="text-xs">
              Update the details for this plant project.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 pt-2">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-foreground">Plant Name</label>
              <input
                className={inputClass}
                value={editForm.name}
                onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))}
                maxLength={100}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-foreground">
                  <MapPin className="inline h-3 w-3 mr-1" />
                  Location
                </label>
                <input
                  className={inputClass}
                  value={editForm.location}
                  onChange={(e) => setEditForm((f) => ({ ...f, location: e.target.value }))}
                  maxLength={100}
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-foreground">Country</label>
                <input
                  className={inputClass}
                  value={editForm.country}
                  onChange={(e) => setEditForm((f) => ({ ...f, country: e.target.value }))}
                  maxLength={60}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-foreground">Fuel / Molecule Type</label>
              <select
                className={inputClass}
                value={editForm.fuelType}
                onChange={(e) => setEditForm((f) => ({ ...f, fuelType: e.target.value }))}
              >
                {fuelTypes.map((ft) => (
                  <option key={ft} value={ft}>{ft}</option>
                ))}
                {!fuelTypes.includes(editForm.fuelType) && (
                  <option value={editForm.fuelType}>{editForm.fuelType}</option>
                )}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-foreground">Target Capacity</label>
                <input
                  className={inputClass}
                  value={editForm.capacity}
                  onChange={(e) => setEditForm((f) => ({ ...f, capacity: e.target.value }))}
                  maxLength={50}
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-foreground">Project Stage</label>
                <select
                  className={inputClass}
                  value={editForm.status}
                  onChange={(e) => setEditForm((f) => ({ ...f, status: e.target.value as PlantStatus }))}
                >
                  {statusOptions.map((s) => (
                    <option key={s.value} value={s.value}>{s.label}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Collection assignment */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-foreground">Collection</label>
                <select
                  className={inputClass}
                  value={editForm.collectionChoice}
                  onChange={(e) => setEditForm((f) => ({ ...f, collectionChoice: e.target.value }))}
                >
                  {(() => {
                    // Unique groupIds present, with display name
                    const seen = new Map<string, string>();
                    for (const p of plants) {
                      const gid = p.projectGroupId || p.id;
                      if (!seen.has(gid)) {
                        const members = plants.filter((q) => (q.projectGroupId || q.id) === gid);
                        seen.set(gid, getCollectionDisplayName(members));
                      }
                    }
                    const opts = Array.from(seen.entries());
                    return (
                      <>
                        {opts.map(([gid, label]) => (
                          <option key={gid} value={gid}>{label}</option>
                        ))}
                        <option value="__STANDALONE__">— Standalone (no collection) —</option>
                        <option value="__NEW__">+ Create new collection…</option>
                      </>
                    );
                  })()}
                </select>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-foreground">Variant Label</label>
                <input
                  className={inputClass}
                  value={editForm.variantLabel}
                  onChange={(e) => setEditForm((f) => ({ ...f, variantLabel: e.target.value }))}
                  maxLength={60}
                  placeholder="e.g. PEM Configuration"
                />
              </div>
            </div>
            {editForm.collectionChoice === "__NEW__" && (
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-foreground">New collection name</label>
                <input
                  className={inputClass}
                  value={editForm.newCollectionName}
                  onChange={(e) => setEditForm((f) => ({ ...f, newCollectionName: e.target.value }))}
                  maxLength={80}
                  placeholder="e.g. Rotterdam Hub"
                />
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setEditPlant(null)}
                className="rounded-lg border border-border px-4 py-2 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleEditSave}
                className="rounded-lg bg-primary px-4 py-2 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                Save Changes
              </button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Ecosystem Map publication dialog */}
      <Dialog open={!!ecoPlant} onOpenChange={(open) => { if (!open) setEcoPlant(null); }}>
        <DialogContent className="sm:max-w-md max-h-[90vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="text-base flex items-center gap-2">
              <Globe className="h-4 w-4 text-primary" />
              Ecosystem Map Publication
            </DialogTitle>
            <DialogDescription className="text-xs">
              Edit the non-sensitive fields shared with the public Ecosystem Map.
              Sensitive data (financials, addresses, internal roles) is never published.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 pt-2 overflow-y-auto pr-1 -mr-1 flex-1 min-h-0">
            {/* Read-only project context, sourced from the plant record */}
            {ecoPlant && (
              <div className="rounded-md border border-border bg-muted/30 p-3 space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-semibold text-foreground truncate">{ecoPlant.name}</p>
                  <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
                    {simplifyFuelLabel(ecoPlant.fuelType)}
                  </span>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  {ecoPlant.location}{ecoPlant.country ? ` · ${ecoPlant.country.toUpperCase()}` : ""}
                </p>
              </div>
            )}

            <div className="flex items-start justify-between gap-4 rounded-md border border-border bg-card/50 p-3">
              <div className="space-y-0.5">
                <label htmlFor="eco-publish" className="text-sm font-medium text-foreground">
                  Published to Ecosystem Map
                </label>
                <p className="text-xs text-muted-foreground">
                  {ecoCurrentKind === "added" && "This plant is currently shown as its own marker."}
                  {ecoCurrentKind === "enriched" && "This plant is currently enriching a verified project."}
                  {ecoCurrentKind === "none" && "This plant is not currently shared with the map."}
                </p>
              </div>
              <Switch
                id="eco-publish"
                checked={ecoForm.publish}
                onCheckedChange={(v) => setEcoForm((f) => ({ ...f, publish: v }))}
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-foreground">Owner / Developer</label>
              <input
                className={inputClass}
                value={ecoForm.owner}
                
                onChange={(e) => setEcoForm((f) => ({ ...f, owner: e.target.value }))}
                maxLength={120}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-foreground">Capacity</label>
                <div className="flex gap-1.5">
                  <input
                    className={`${inputClass} flex-1`}
                    type="text"
                    inputMode="decimal"
                    value={ecoForm.capacityValue}
                    
                    onChange={(e) => setEcoForm((f) => ({ ...f, capacityValue: e.target.value }))}
                    placeholder="e.g. 10"
                    maxLength={20}
                  />
                  <select
                    className={`${inputClass} w-[140px]`}
                    value={ecoForm.capacityUnit}
                    
                    onChange={(e) => setEcoForm((f) => ({ ...f, capacityUnit: e.target.value }))}
                  >
                    {CAPACITY_UNITS.map((u) => (
                      <option key={u} value={u}>{u}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-foreground">Country</label>
                <input
                  className={inputClass}
                  value={ecoForm.country}
                  
                  onChange={(e) => setEcoForm((f) => ({ ...f, country: e.target.value }))}
                  maxLength={60}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-foreground">Project Status</label>
                <select
                  className={inputClass}
                  value={ecoForm.status}
                  
                  onChange={(e) => setEcoForm((f) => ({ ...f, status: e.target.value as ProjectStatus }))}
                >
                  <option value="concept">Concept</option>
                  <option value="planned">Planned</option>
                  <option value="construction">Construction</option>
                  <option value="operational">Operational</option>
                  <option value="cancelled">Cancelled</option>
                </select>
                <p className="text-[10px] text-muted-foreground">Mirrors this plant's lifecycle status.</p>
              </div>
            </div>

            {/* Extendible, additional fields the user can opt to expose */}
            <details className="rounded-md border border-border bg-card/50" open={ecoForm.visibleFields.length > 0}>
              <summary className="cursor-pointer px-3 py-2 text-xs font-semibold text-foreground select-none">
                Additional details ({ecoForm.visibleFields.length} shown)
              </summary>
              <div className="border-t border-border p-3 space-y-3">
                <p className="text-[10px] text-muted-foreground">
                  Toggle which extra fields appear on the public Ecosystem Map detail panel.
                </p>
                <div className="grid grid-cols-2 gap-2">
                  {OPTIONAL_FIELDS.map((opt) => {
                    const checked = ecoForm.visibleFields.includes(opt.key);
                    return (
                      <label
                        key={opt.key}
                        className={`flex items-center gap-2 rounded-md border border-border bg-background px-2.5 py-1.5 text-[11px] ${opt.disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer hover:bg-accent"}`}
                        title={opt.hint}
                      >
                        <input
                          type="checkbox"
                          className="h-3.5 w-3.5"
                          checked={checked}
                          disabled={opt.disabled || !ecoForm.publish}
                          onChange={(e) => setEcoForm((f) => ({
                            ...f,
                            visibleFields: e.target.checked
                              ? [...f.visibleFields, opt.key]
                              : f.visibleFields.filter((k) => k !== opt.key),
                          }))}
                        />
                        <span className="truncate">{opt.label}</span>
                      </label>
                    );
                  })}
                </div>

                {/* Editors for fields the user toggled on */}
                <div className="space-y-2 pt-1">
                  {ecoForm.visibleFields.includes("productionPathway") && (
                    <div className="space-y-1">
                      <label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Production Pathway</label>
                      <select
                        className={inputClass}
                        value={ecoForm.productionPathway}
                        
                        onChange={(e) => setEcoForm((f) => ({ ...f, productionPathway: e.target.value as ProductionPathway | "" }))}
                      >
                        <option value="">– Not specified –</option>
                        <option value="Synthetic Pathway">Synthetic Pathway</option>
                        <option value="Biogenic Pathway">Biogenic Pathway</option>
                        <option value="Thermochemical Pathway">Thermochemical Pathway</option>
                        <option value="Hybrid Pathway">Hybrid Pathway</option>
                        <option value="Physical Recovery Pathway">Physical Recovery Pathway</option>
                      </select>
                    </div>
                  )}
                  {ecoForm.visibleFields.includes("commissioningYear") && (
                    <div className="space-y-1">
                      <label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Commissioning Year</label>
                      <input
                        className={inputClass}
                        type="number"
                        value={ecoForm.commissioningYear}
                        
                        onChange={(e) => setEcoForm((f) => ({ ...f, commissioningYear: e.target.value }))}
                      />
                    </div>
                  )}
                  {ecoForm.visibleFields.includes("website") && (
                    <div className="space-y-1">
                      <label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Website / Contact</label>
                      <input
                        className={inputClass}
                        type="url"
                        placeholder="https://…"
                        value={ecoForm.website}
                        
                        onChange={(e) => setEcoForm((f) => ({ ...f, website: e.target.value }))}
                      />
                    </div>
                  )}
                  {ecoForm.visibleFields.includes("offtakers") && (
                    <div className="space-y-1">
                      <label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Offtake Partners</label>
                      <input
                        className={inputClass}
                        placeholder="Comma-separated"
                        value={ecoForm.offtakers}
                        
                        onChange={(e) => setEcoForm((f) => ({ ...f, offtakers: e.target.value }))}
                      />
                    </div>
                  )}
                  {ecoForm.visibleFields.includes("certifications") && (
                    <div className="space-y-1">
                      <label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Certification Schemes</label>
                      <input
                        className={inputClass}
                        placeholder="e.g. ISCC EU, REDcert"
                        value={ecoForm.certifications}
                        
                        onChange={(e) => setEcoForm((f) => ({ ...f, certifications: e.target.value }))}
                      />
                    </div>
                  )}
                </div>
              </div>
            </details>

          </div>
          <div className="flex justify-end gap-2 pt-3 border-t border-border mt-2">
            <button
              onClick={() => setEcoPlant(null)}
              className="rounded-lg border border-border px-4 py-2 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleEcoSave}
              className="rounded-lg bg-primary px-4 py-2 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              {ecoForm.publish ? "Save & Publish" : "Unpublish"}
            </button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Permanent-delete confirmation */}
      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => { if (!open && !isDeleting) setDeleteTarget(null); }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Permanently delete this plant?</AlertDialogTitle>
            <AlertDialogDescription>
              You are about to permanently delete{" "}
              <strong className="text-foreground">{deleteTarget?.name}</strong>.
              The following items will be removed:
            </AlertDialogDescription>
          </AlertDialogHeader>
          <ul className="rounded-md border border-border bg-muted/40 p-3 space-y-1.5 text-xs text-foreground">
            {[
              "Plant card from your Plant Builder list",
              "Plant canvas layout and topology",
              "All equipment nodes and their equations",
              "All carrier nodes (fuels, utilities, by-products)",
              "All gate nodes (offtake, supply, interface)",
              "All edges and flow values between nodes",
              "Plant settings (operating hours, identifiers, display)",
              "All saved version snapshots and history",
            ].map((item) => (
              <li key={item} className="flex items-start gap-2">
                <span className="mt-1 inline-block h-1.5 w-1.5 rounded-full bg-destructive shrink-0" aria-hidden="true" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
          <p className="text-xs font-semibold text-destructive">
            This action cannot be undone. The data cannot be retrieved.
          </p>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={isDeleting}
              onClick={(e) => { e.preventDefault(); confirmDelete(); }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeleting ? "Deleting…" : "Delete permanently"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Save confirmation prompt */}
      <SaveConfirmDialog
        open={showSavePrompt}
        context="plant list changes"
        onSave={() => {
          syncToLocalCache(plants);
          savePlantsToCloud(userId, plants);
          setIsDirty(false);
          setShowSavePrompt(false);
          proceed();
          if (pendingNavigation.current) {
            const url = pendingNavigation.current;
            pendingNavigation.current = null;
            navigate(url);
          }
        }}
        onDiscard={() => {
          const saved = loadFromStorage<ProjectRecord[]>("plant_list");
          setPlants(saved || [...projectRegistry]);
          setIsDirty(false);
          setShowSavePrompt(false);
          proceed();
          if (pendingNavigation.current) {
            const url = pendingNavigation.current;
            pendingNavigation.current = null;
            navigate(url);
          }
        }}
        onCancel={() => {
          setShowSavePrompt(false);
          pendingNavigation.current = null;
          reset();
        }}
      />
    </div>
  );
};

export default PlantBuilder;
