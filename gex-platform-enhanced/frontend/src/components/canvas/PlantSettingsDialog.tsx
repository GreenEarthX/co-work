/**
 * PlantSettingsDialog — unified Plant Settings popup.
 *
 * Replaces the previous side sheet. Four top-level tabs (rendered as a
 * vertical list on the left, content on the right):
 *   1. Project Form     — read/edit the project metadata captured at creation.
 *   2. Plant Parameters — annual hours, availability, critical-path picker.
 *   3. History          — version snapshots (restore previous saved states).
 *   4. Plant Display    — IDs on/off, ID debug, layout orientation, legend recolor (RGB).
 *
 * Each tab uses an internal navigation section to organize its sub-features.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { PrecisionColorPicker } from "@/components/canvas/PrecisionColorPicker";
import {
  Settings2, FileText, Sliders, History as HistoryIcon, Eye,
  Route, Plus, X, Hash, Bug, ArrowRightLeft, ArrowDownUp, Palette,
  RotateCcw, Loader2, RefreshCw, TextCursor, ListOrdered, AlertTriangle,
  Trash2,
} from "lucide-react";
import { engineInstance } from "@/engine/EquationEngine";
import type { Node } from "@xyflow/react";
import { toast } from "sonner";
import type { CanvasData, VersionEntry } from "@/hooks/useCanvasData";
import { type ProjectRecord } from "@/lib/projectRegistry";
import type { LabelNormalizationPrefs } from "@/hooks/useLabelNormalizationPrefs";
import { normalizeLabel } from "./nodeIdSystem";
import {
  getAllCarrierOverrides,
  setCarrierColorOverride,
  resetCarrierOverrides,
  hexToRgb,
  subscribeCarrierOverrides,
  parseColor,
} from "@/lib/carrierColorOverrides";
import { ColorPresetRow } from "@/components/canvas/ColorPresetRow";
import { HexInputField } from "@/components/canvas/HexInputField";
import { getColorFromResource } from "./portSystem";

type TabKey = "project" | "parameters" | "identifiers" | "display" | "history";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  // Project context
  project: ProjectRecord;
  // Parameters
  hoursYear: number;
  onHoursYearChange: (val: number) => void;
  plantAvailability: number;
  onPlantAvailabilityChange: (val: number) => void;
  criticalPathMode?: boolean;
  onToggleCriticalPathMode?: () => void;
  criticalPathNodeIds: Set<string>;
  onCriticalPathChange: (ids: Set<string>) => void;
  equipmentNodes: Node[];
  carrierNodes: Node[];
  // History
  listVersions: () => Promise<VersionEntry[]>;
  restoreVersion: (path: string) => Promise<CanvasData | null>;
  onRestored: (data: CanvasData) => void;
  // Display toggles
  showNodeIds: boolean;
  onShowNodeIdsChange: (next: boolean) => void;
  debugNodeIds: boolean;
  onDebugNodeIdsChange: (next: boolean) => void;
  layoutOrientation: "horizontal" | "vertical";
  onLayoutOrientationChange: (next: "horizontal" | "vertical") => void;
  compactNodes: boolean;
  onCompactNodesChange: (next: boolean) => void;
  straightEdges: boolean;
  onStraightEdgesChange: (next: boolean) => void;
  // Label normalization (for duplicate-detection on E#/C#/G# badges)
  labelNormPrefs: LabelNormalizationPrefs;
  onLabelNormPrefChange: <K extends keyof LabelNormalizationPrefs>(key: K, value: LabelNormalizationPrefs[K]) => void;
  onResetLabelNormPrefs: () => void;
  // Traceability — current + retired display IDs
  allNodes: Node[];
  retiredDisplayIds: string[];
}

/**
 * Tab catalog grouped into three logical clusters so Plant Settings reads as
 * a real configuration hub rather than a flat list:
 *   • Configuration — what the plant *is*    (project metadata, operating params)
 *   • Canvas        — how the plant *looks*  (identifiers, visual display)
 *   • Lifecycle     — how the plant *evolves* (history snapshots)
 */
interface TabSection { id: string; label: string }
interface TabSpec {
  key: TabKey;
  label: string;
  icon: typeof Settings2;
  sub: string;
  sections: TabSection[];
}

const TABS: TabSpec[] = [
  {
    key: "project", label: "Project Form", icon: FileText,
    sub: "",
    sections: [
      { id: "identity", label: "Project Identity" },
      { id: "pathway", label: "Pathway & Configuration" },
      { id: "location", label: "Location" },
      { id: "maturity", label: "Project Maturity" },
      { id: "products", label: "Products" },
    ],
  },
  {
    key: "parameters", label: "Plant Parameters", icon: Sliders,
    sub: "",
    sections: [
      { id: "hours", label: "Operating Hours" },
      { id: "critical-path", label: "Critical Path" },
    ],
  },
  {
    key: "identifiers", label: "Identifiers", icon: Hash,
    sub: "",
    sections: [
      { id: "badges", label: "Identifier Badges" },
      { id: "normalization", label: "Label Normalization" },
      { id: "normalization-preview", label: "Normalization Preview" },
      { id: "traceability", label: "ID Traceability" },
    ],
  },
  {
    key: "display", label: "Plant Display", icon: Eye,
    sub: "",
    sections: [
      { id: "layout", label: "Canvas Layout" },
      { id: "legend", label: "Legend Recolor" },
    ],
  },
  {
    key: "history", label: "History", icon: HistoryIcon,
    sub: "",
    sections: [
      { id: "snapshots", label: "Snapshots" },
    ],
  },
];

export function PlantSettingsDialog(props: Props) {
  const { open, onOpenChange } = props;
  const [tab, setTab] = useState<TabKey>("project");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl w-[min(1040px,96vw)] p-0 overflow-hidden">
        <DialogHeader className="px-5 pt-5 pb-3 border-b border-border">
          <DialogTitle className="flex items-center gap-2 text-base">
            <Settings2 className="h-4 w-4 text-primary" />
            Plant Settings
          </DialogTitle>
          <DialogDescription className="sr-only">Plant settings</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-[220px_1fr] min-h-[560px]">
          {/* LEFT, vertical tab list */}
          <nav className="border-r border-border bg-muted/30 py-3 px-2 space-y-0.5 overflow-y-auto" aria-label="Plant settings sections">
            {TABS.map((t) => {
              const Icon = t.icon;
              const active = tab === t.key;
              return (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  aria-current={active ? "page" : undefined}
                  className={`w-full text-left flex items-start gap-2 rounded-md px-2.5 py-2 text-xs transition-colors ${
                    active
                      ? "bg-primary/10 text-primary border border-primary/30"
                      : "text-muted-foreground hover:bg-accent hover:text-foreground border border-transparent"
                  }`}
                >
                  <Icon className={`h-3.5 w-3.5 mt-0.5 shrink-0 ${active ? "text-primary" : ""}`} />
                  <span className="flex flex-col leading-tight min-w-0">
                    <span className="font-semibold">{t.label}</span>
                    {t.sub && <span className="text-[10px] opacity-80 font-normal truncate">{t.sub}</span>}
                  </span>
                </button>
              );
            })}
          </nav>

          {/* RIGHT, tab content */}
          <div className="flex flex-col min-h-0">
            <div className="max-h-[70vh] overflow-y-auto">
              <div className="p-5">
                {tab === "project"     && <ProjectFormTab project={props.project} />}
                {tab === "parameters"  && <ParametersTab {...props} />}
                {tab === "identifiers" && <IdentifiersTab {...props} />}
                {tab === "display"     && <DisplayTab {...props} />}
                {tab === "history"     && <HistoryTab {...props} />}
              </div>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/* ─────────────────────────── TAB 1 — Project Form ────────────────────────── */

/**
 * ProjectFormTab mirrors EXACTLY the New Plant creation form
 * (see src/components/plant/NewPlantDialog.tsx), so users can edit every
 * field captured at creation time. Data is persisted to the same
 * `gex_plant_setup_${slug}` / `gex_plant_profile_${slug}` localStorage keys
 * that NewPlantDialog writes, so ProjectProfilePanel picks the changes up.
 */

const ROLES = ["Project Developer", "Plant Owner", "EPC Contractor", "Investor", "Offtaker", "Advisor", "Other"];
const PRIMARY_PATHWAYS = ["Synthetic Pathway", "Biogenic Pathway", "Thermochemical Pathway", "Hybrid Pathway", "Physical Recovery Pathway", "Other"];
const PLANT_CONFIGS = ["New Build", "Retrofit", "Expansion", "Mixed"];
const SITE_ENVIRONMENTS = ["Coastal", "Inland", "Industrial Cluster", "Port Terminal", "Urban", "Rural", "Other"];
const MATURITY_STAGES = ["Concept", "Pre Feasibility", "Feasibility", "Pre FEED", "FEED", "Permitting", "Pre FID", "FID", "Construction", "Commissioning", "Operating"];
const CERTIFICATION_PHASES = ["Not Started", "Eligibility Scoping", "Data Collection", "Pre Assessment", "Documentation Prepared", "Auditor Engagement", "Certification Submitted", "Certified", "Surveillance"];
const FUEL_TYPES = ["Hydrogen", "Ammonia", "Methanol", "Methane", "Diesel", "Kerosene", "Naphtha", "Butane", "Propane", "Ethanol", "Gasoline"];
const CAPACITY_UNITS = ["Ton per Year", "Ton per Day", "Kilogram per Hour", "Normal Cubic Meter per Hour"];

interface ProductBlock {
  id: string;
  fuelType: string;
  capacity: string;
  capacityUnit: string;
}

interface ProjectFormState {
  // A. Identity
  projectName: string;
  plantName: string;
  companyName: string;
  projectLifetime: string;
  roleInProject: string;
  // B. Pathway
  primaryPathway: string;
  plantConfiguration: string;
  // C. Location
  country: string;
  region: string;
  city: string;
  address: string;
  postalCode: string;
  latitude: string;
  longitude: string;
  siteEnvironment: string;
  // D. Maturity
  maturityStage: string;
  stageReferenceYear: string;
  certificationPhase: string;
  expectedCod: string;
  // Products
  products: ProductBlock[];
}

function makeProduct(): ProductBlock {
  return {
    id: (typeof crypto !== "undefined" && crypto.randomUUID?.()) || `p-${Date.now()}-${Math.random()}`,
    fuelType: "",
    capacity: "",
    capacityUnit: "Ton per Year",
  };
}

function buildInitialFormFromProject(project: ProjectRecord): ProjectFormState {
  const [city, country] = project.location.split(",").map((s) => s.trim());
  return {
    projectName: project.name,
    plantName: project.name,
    companyName: "",
    projectLifetime: "",
    roleInProject: "",
    primaryPathway: "",
    plantConfiguration: "",
    country: country || project.country || "",
    region: "",
    city: city || "",
    address: "",
    postalCode: "",
    latitude: project.lat ? String(project.lat) : "",
    longitude: project.lng ? String(project.lng) : "",
    siteEnvironment: "",
    maturityStage: "",
    stageReferenceYear: String(new Date().getFullYear()),
    certificationPhase: "",
    expectedCod: project.codYear ? String(project.codYear) : "",
    products: [{ ...makeProduct(), fuelType: project.fuelType, capacity: project.capacity }],
  };
}

function ProjectFormTab({ project }: { project: ProjectRecord }) {
  const slug = project.id;

  // Load existing setup from localStorage (written by NewPlantDialog) or
  // synthesize one from the ProjectRecord so the form is always populated.
  const DRAFT_KEY = `gex_plant_setup_draft_${slug}`;
  const SAVED_KEY = `gex_plant_setup_${slug}`;

  // Build {savedState, restoredFromDraft}: prefer the autosave draft if it
  // differs from the last saved snapshot, so a refresh / nav-away / crash
  // never loses in-flight edits.
  const initialBundle = useMemo(() => {
    const fallback = buildInitialFormFromProject(project);
    let saved: ProjectFormState = fallback;
    try {
      const rawSaved = localStorage.getItem(SAVED_KEY);
      if (rawSaved) {
        const parsed = JSON.parse(rawSaved) as Partial<ProjectFormState>;
        saved = {
          ...fallback,
          ...parsed,
          products: Array.isArray(parsed.products) && parsed.products.length > 0
            ? parsed.products
            : fallback.products,
        };
      }
    } catch { /* ignore */ }
    let draft: ProjectFormState | null = null;
    let draftAt: number | null = null;
    try {
      const rawDraft = localStorage.getItem(DRAFT_KEY);
      if (rawDraft) {
        const parsed = JSON.parse(rawDraft) as { form?: Partial<ProjectFormState>; at?: number };
        if (parsed?.form) {
          draft = {
            ...saved,
            ...parsed.form,
            products: Array.isArray(parsed.form.products) && parsed.form.products.length > 0
              ? parsed.form.products
              : saved.products,
          };
          draftAt = typeof parsed.at === "number" ? parsed.at : null;
        }
      }
    } catch { /* ignore */ }
    const draftDiffers = draft && JSON.stringify(draft) !== JSON.stringify(saved);
    return {
      saved,
      initial: draftDiffers ? (draft as ProjectFormState) : saved,
      restoredFromDraft: !!draftDiffers,
      draftAt,
    };
  }, [project, slug, SAVED_KEY, DRAFT_KEY]);

  const [form, setForm] = useState<ProjectFormState>(initialBundle.initial);
  const [savedSnapshot, setSavedSnapshot] = useState<string>(() => JSON.stringify(initialBundle.saved));
  const [draftSavedAt, setDraftSavedAt] = useState<number | null>(initialBundle.draftAt);
  const [restoredFromDraft, setRestoredFromDraft] = useState<boolean>(initialBundle.restoredFromDraft);
  // Re-seed the form ONLY when the active project (slug) actually changes.
  // Re-running on every `initialBundle` identity (which flips on each parent
  // re-render because `project` is a fresh object) would wipe out in-flight
  // typing before the 600ms autosave-draft debounce can persist it.
  const lastSlugRef = useRef<string>(slug);
  useEffect(() => {
    if (lastSlugRef.current === slug) return;
    lastSlugRef.current = slug;
    setForm(initialBundle.initial);
    setSavedSnapshot(JSON.stringify(initialBundle.saved));
    setDraftSavedAt(initialBundle.draftAt);
    setRestoredFromDraft(initialBundle.restoredFromDraft);
  }, [slug, initialBundle]);

  // Debounced autosave: write a draft snapshot whenever the form differs
  // from the last saved version. Cleared on Save / Reset.
  useEffect(() => {
    const serialized = JSON.stringify(form);
    if (serialized === savedSnapshot) return;
    const handle = window.setTimeout(() => {
      try {
        const at = Date.now();
        localStorage.setItem(DRAFT_KEY, JSON.stringify({ form, at }));
        setDraftSavedAt(at);
      } catch { /* ignore quota errors */ }
    }, 600);
    return () => window.clearTimeout(handle);
  }, [form, savedSnapshot, DRAFT_KEY]);

  // Best-effort flush before the tab unloads, so very recent edits aren't
  // lost between the last debounce tick and a refresh.
  useEffect(() => {
    const flush = () => {
      const serialized = JSON.stringify(form);
      if (serialized === savedSnapshot) return;
      try { localStorage.setItem(DRAFT_KEY, JSON.stringify({ form, at: Date.now() })); } catch { /* ignore */ }
    };
    window.addEventListener("beforeunload", flush);
    return () => window.removeEventListener("beforeunload", flush);
  }, [form, savedSnapshot, DRAFT_KEY]);

  const clearDraft = () => {
    try { localStorage.removeItem(DRAFT_KEY); } catch { /* ignore */ }
    setDraftSavedAt(null);
    setRestoredFromDraft(false);
  };

  const dirty = JSON.stringify(form) !== savedSnapshot;

  const set = <K extends keyof ProjectFormState>(k: K, v: ProjectFormState[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const updateProduct = (id: string, patch: Partial<ProductBlock>) =>
    setForm((f) => ({ ...f, products: f.products.map((p) => (p.id === id ? { ...p, ...patch } : p)) }));
  const addProduct = () => setForm((f) => ({ ...f, products: [...f.products, makeProduct()] }));
  const removeProduct = (id: string) =>
    setForm((f) => ({ ...f, products: f.products.filter((p) => p.id !== id) }));

  const handleSave = () => {
    setSubmitAttempted(true);
    if (hasBlockingErrors) {
      toast.error("Please fix the highlighted fields before saving.");
      return;
    }
    const profile: Record<string, string> = {
      companyName: form.companyName,
      plantName: form.plantName || form.projectName,
      location: [form.city, form.country].filter(Boolean).join(", "),
      country: form.country,
      fuelType: form.products.map((p) => p.fuelType).filter(Boolean).join(" + ") || "–",
      primaryPathway: form.primaryPathway || "–",
      plantConfiguration: form.plantConfiguration || "–",
      productionCapacity: form.products
        .filter((p) => p.capacity)
        .map((p) => `${p.capacity} ${p.capacityUnit}`)
        .join("; ") || "–",
      expectedCod: form.expectedCod || "–",
      maturityStage: form.maturityStage || "–",
      siteEnvironment: form.siteEnvironment || "–",
      roleInProject: form.roleInProject || "–",
      projectLifetime: form.projectLifetime ? `${form.projectLifetime} years` : "–",
    };
    try {
      localStorage.setItem(`gex_plant_profile_${slug}`, JSON.stringify(profile));
      localStorage.setItem(SAVED_KEY, JSON.stringify(form));
      setSavedSnapshot(JSON.stringify(form));
      clearDraft();
      toast.success("Project form saved.");
    } catch {
      toast.error("Could not save project form.");
    }
  };

  // ── Validation ──
  type FormErrors = {
    projectName?: string;
    companyName?: string;
    country?: string;
    maturityStage?: string;
    projectLifetime?: string;
    stageReferenceYear?: string;
    latitude?: string;
    longitude?: string;
    expectedCod?: string;
    products: Record<string, { fuelType?: string; capacity?: string }>;
  };
  const errors = useMemo<FormErrors>(() => {
    const e: FormErrors = { products: {} };
    if (!form.projectName.trim()) e.projectName = "Project name is required.";
    if (!form.companyName.trim()) e.companyName = "Company name is required.";
    if (!form.country.trim()) e.country = "Country is required.";
    if (!form.maturityStage.trim()) e.maturityStage = "Select a maturity stage.";
    if (form.projectLifetime) {
      const n = Number(form.projectLifetime);
      if (!Number.isFinite(n) || n < 0 || n > 100) e.projectLifetime = "Enter a value between 0 and 100.";
    }
    if (form.stageReferenceYear) {
      const n = Number(form.stageReferenceYear);
      if (!Number.isInteger(n) || n < 1900 || n > 2100) e.stageReferenceYear = "Enter a year between 1900 and 2100.";
    }
    if (form.latitude) {
      const n = Number(form.latitude);
      if (!Number.isFinite(n) || n < -90 || n > 90) e.latitude = "Latitude must be between -90 and 90.";
    }
    if (form.longitude) {
      const n = Number(form.longitude);
      if (!Number.isFinite(n) || n < -180 || n > 180) e.longitude = "Longitude must be between -180 and 180.";
    }
    if (form.expectedCod && !/^(\d{4}|\d{4}-\d{2}-\d{2})$/.test(form.expectedCod.trim())) {
      e.expectedCod = "Use YYYY or YYYY-MM-DD.";
    }
    for (const p of form.products) {
      const pe: { fuelType?: string; capacity?: string } = {};
      if (!p.fuelType.trim()) pe.fuelType = "Select a fuel type.";
      if (p.capacity) {
        const n = Number(p.capacity);
        if (!Number.isFinite(n) || n < 0) pe.capacity = "Enter a positive number.";
      }
      if (pe.fuelType || pe.capacity) e.products[p.id] = pe;
    }
    return e;
  }, [form]);

  const [submitAttempted, setSubmitAttempted] = useState(false);
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const markTouched = (k: string) => setTouched((t) => (t[k] ? t : { ...t, [k]: true }));
  const showErr = (k: string) => submitAttempted || !!touched[k];
  const err = (k: keyof FormErrors): string | null => {
    if (k === "products") return null;
    return showErr(k) ? (errors[k] as string | undefined) ?? null : null;
  };
  const productErr = (pid: string, k: "fuelType" | "capacity"): string | null => {
    const tk = `product.${pid}.${k}`;
    if (!showErr(tk)) return null;
    return errors.products[pid]?.[k] ?? null;
  };
  const hasBlockingErrors =
    !!errors.projectName || !!errors.companyName || !!errors.country || !!errors.maturityStage ||
    !!errors.projectLifetime || !!errors.stageReferenceYear || !!errors.latitude || !!errors.longitude ||
    !!errors.expectedCod || Object.keys(errors.products).length > 0;

  const inputCls = "w-full h-9 rounded-md border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring";

  // ── Per-section completion (mandatory vs optional) so each Section
  // header can show its own inline progress bar. No global stepper.
  const progress = useMemo(() => {
    const has = (v: unknown) => !!(typeof v === "string" ? v.trim() : v);
    const count = (vals: unknown[]) => vals.filter(has).length;
    const make = (req: unknown[], opt: unknown[]) => ({
      requiredFilled: count(req),
      requiredTotal:  req.length,
      optionalFilled: count(opt),
      optionalTotal:  opt.length,
    });
    return {
      identity: make(
        [form.projectName, form.companyName],
        [form.plantName, form.projectLifetime, form.roleInProject],
      ),
      pathway: make(
        [],
        [form.primaryPathway, form.plantConfiguration],
      ),
      location: make(
        [form.country],
        [form.region, form.city, form.postalCode, form.address, form.latitude, form.longitude, form.siteEnvironment],
      ),
      maturity: make(
        [form.maturityStage],
        [form.stageReferenceYear, form.certificationPhase, form.expectedCod],
      ),
      products: {
        requiredFilled: form.products.filter((p) => has(p.fuelType)).length,
        requiredTotal:  form.products.length,
        optionalFilled: form.products.filter((p) => has(p.capacity)).length,
        optionalTotal:  form.products.length,
      },
    } as const;
  }, [form]);

  return (
    <div className="space-y-0">
      <div className="pb-3 sm:pb-6">
        <Section id="identity" step={1} title="Project Details" progress={progress.identity}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Project Name" required error={err("projectName")}>
              <input className={inputCls} value={form.projectName} maxLength={120}
                onBlur={() => markTouched("projectName")}
                onChange={(e) => set("projectName", e.target.value)} />
            </Field>
            <Field label="Plant Name">
              <input className={inputCls} value={form.plantName} maxLength={120}
                onChange={(e) => set("plantName", e.target.value)} />
            </Field>
            <Field label="Company Name" required error={err("companyName")}>
              <input className={inputCls} value={form.companyName} maxLength={120}
                onBlur={() => markTouched("companyName")}
                onChange={(e) => set("companyName", e.target.value)} />
            </Field>
            <Field label="Project Lifetime (years)" error={err("projectLifetime")}>
              <input type="number" min={0} max={100} className={inputCls} value={form.projectLifetime}
                onBlur={() => markTouched("projectLifetime")}
                onChange={(e) => set("projectLifetime", e.target.value)} />
            </Field>
            <Field label="Role in Project">
              <select className={inputCls} value={form.roleInProject}
                onChange={(e) => set("roleInProject", e.target.value)}>
                <option value="">– Select –</option>
                {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </Field>
          </div>
        </Section>
      </div>

      <div className="py-3 sm:py-6">
        <Section id="pathway" step={2} title="Pathway" progress={progress.pathway}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Primary Pathway">
              <select className={inputCls} value={form.primaryPathway}
                onChange={(e) => set("primaryPathway", e.target.value)}>
                <option value="">– Select –</option>
                {PRIMARY_PATHWAYS.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </Field>
            <Field label="Plant Configuration">
              <select className={inputCls} value={form.plantConfiguration}
                onChange={(e) => set("plantConfiguration", e.target.value)}>
                <option value="">– Select –</option>
                {PLANT_CONFIGS.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </Field>
          </div>
        </Section>
      </div>

      <div className="py-3 sm:py-6">
        <Section id="location" step={3} title="Geographic Location" progress={progress.location}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Country" required error={err("country")}>
              <input className={inputCls} value={form.country} list="psd-countries"
                onBlur={() => markTouched("country")}
                onChange={(e) => set("country", e.target.value)} />
            </Field>
            <Field label="Region or State">
              <input className={inputCls} value={form.region} maxLength={100}
                onChange={(e) => set("region", e.target.value)} />
            </Field>
            <Field label="City">
              <input className={inputCls} value={form.city} maxLength={100}
                onChange={(e) => set("city", e.target.value)} />
            </Field>
            <Field label="Postal Code">
              <input className={inputCls} value={form.postalCode} maxLength={20}
                onChange={(e) => set("postalCode", e.target.value)} />
            </Field>
            <div className="sm:col-span-2">
              <Field label="Address">
                <input className={inputCls} value={form.address} maxLength={200}
                  onChange={(e) => set("address", e.target.value)} />
              </Field>
            </div>
            <Field label="Latitude" error={err("latitude")}>
              <input type="number" step="any" min={-90} max={90} className={inputCls} value={form.latitude}
                onBlur={() => markTouched("latitude")}
                onChange={(e) => set("latitude", e.target.value)} />
            </Field>
            <Field label="Longitude" error={err("longitude")}>
              <input type="number" step="any" min={-180} max={180} className={inputCls} value={form.longitude}
                onBlur={() => markTouched("longitude")}
                onChange={(e) => set("longitude", e.target.value)} />
            </Field>
            <div className="sm:col-span-2">
              <Field label="Site Environment">
                <select className={inputCls} value={form.siteEnvironment}
                  onChange={(e) => set("siteEnvironment", e.target.value)}>
                  <option value="">– Select –</option>
                  {SITE_ENVIRONMENTS.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </Field>
            </div>
          </div>
        </Section>
      </div>

      <div className="py-3 sm:py-6">
        <Section id="maturity" step={4} title="Project Maturity" progress={progress.maturity}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Project Maturity Stage" required error={err("maturityStage")}>
              <select className={inputCls} value={form.maturityStage}
                onBlur={() => markTouched("maturityStage")}
                onChange={(e) => set("maturityStage", e.target.value)}>
                <option value="">– Select –</option>
                {MATURITY_STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </Field>
            <Field label="Stage Reference Year" error={err("stageReferenceYear")}>
              <input type="number" min={1900} max={2100} className={inputCls}
                value={form.stageReferenceYear}
                onBlur={() => markTouched("stageReferenceYear")}
                onChange={(e) => set("stageReferenceYear", e.target.value)} />
            </Field>
            <Field label="Certification Phase">
              <select className={inputCls} value={form.certificationPhase}
                onChange={(e) => set("certificationPhase", e.target.value)}>
                <option value="">– Select –</option>
                {CERTIFICATION_PHASES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </Field>
            <Field label="Expected COD (year or date)" error={err("expectedCod")}>
              <input className={inputCls} placeholder="e.g. 2028 or 2028-06-01"
                value={form.expectedCod}
                onBlur={() => markTouched("expectedCod")}
                onChange={(e) => set("expectedCod", e.target.value)} />
            </Field>
          </div>
        </Section>
      </div>

      <div className="py-3 sm:py-6">
        <Section id="products" step={5} title="Product" progress={progress.products}>
          <div className="space-y-3">
            {form.products.map((p, idx) => (
              <div key={p.id} className="rounded-lg border border-border bg-muted/30 p-2.5 sm:p-3 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Product {idx + 1}
                  </span>
                  {form.products.length > 1 && (
                    <button onClick={() => removeProduct(p.id)}
                      className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px] text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors">
                      <Trash2 className="h-3 w-3" /> Remove
                    </button>
                  )}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <Field label="Fuel Type" required error={productErr(p.id, "fuelType")}>
                    <select className={inputCls} value={p.fuelType}
                      onBlur={() => markTouched(`product.${p.id}.fuelType`)}
                      onChange={(e) => updateProduct(p.id, { fuelType: e.target.value })}>
                      <option value="">– Select –</option>
                      {FUEL_TYPES.map((f) => <option key={f} value={f}>{f}</option>)}
                    </select>
                  </Field>
                  <Field label="Production Capacity" error={productErr(p.id, "capacity")}>
                    <input type="number" min={0} step="any" className={inputCls}
                      value={p.capacity}
                      onBlur={() => markTouched(`product.${p.id}.capacity`)}
                      onChange={(e) => updateProduct(p.id, { capacity: e.target.value })} />
                  </Field>
                  <Field label="Capacity Unit">
                    <select className={inputCls} value={p.capacityUnit}
                      onChange={(e) => updateProduct(p.id, { capacityUnit: e.target.value })}>
                      {CAPACITY_UNITS.map((u) => <option key={u} value={u}>{u}</option>)}
                    </select>
                  </Field>
                </div>
              </div>
            ))}
            <button onClick={addProduct}
              className="inline-flex items-center gap-1.5 rounded-md border border-dashed border-border px-3 py-2 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition-colors">
              <Plus className="h-3 w-3" /> Add another product
            </button>
          </div>
        </Section>
      </div>

      <div className="flex items-center justify-between gap-2 pt-4 mt-2">
        <div className="text-[11px] text-muted-foreground">
          {dirty && draftSavedAt ? (
            <span>Draft autosaved · {new Date(draftSavedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}{restoredFromDraft ? " (restored)" : ""}</span>
          ) : restoredFromDraft ? (
            <span>Restored from autosaved draft</span>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" disabled={!dirty} onClick={() => { setForm(JSON.parse(savedSnapshot)); clearDraft(); }}>Reset</Button>
          <Button size="sm" disabled={!dirty} onClick={handleSave}>Save Changes</Button>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────── TAB 2 — Plant Parameters ────────────────────────── */

function ParametersTab(props: Props) {
  const {
    hoursYear, onHoursYearChange, plantAvailability, onPlantAvailabilityChange,
    criticalPathMode, onToggleCriticalPathMode, criticalPathNodeIds, onCriticalPathChange,
    equipmentNodes, onOpenChange,
  } = props;
  const [addOpen, setAddOpen] = useState(false);
  const effectiveHours = Math.round(hoursYear * (plantAvailability / 100));
  const criticalNodes = equipmentNodes.filter((n) => criticalPathNodeIds.has(n.id));
  const availableToAdd = equipmentNodes.filter((n) => !criticalPathNodeIds.has(n.id));

  const removeFromCriticalPath = (nodeId: string) => {
    const next = new Set(criticalPathNodeIds);
    next.delete(nodeId);
    onCriticalPathChange(next);
  };
  const addToCriticalPath = (nodeId: string) => {
    const next = new Set(criticalPathNodeIds);
    next.add(nodeId);
    onCriticalPathChange(next);
    setAddOpen(false);
  };

  return (
    <div className="space-y-6">
      <Section id="hours" title="Operating Hours">
        <Field
          label={
            <span className="inline-flex items-center gap-1.5">
              Total Calendar Hours per Year
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="inline-flex items-center justify-center h-4 w-4 rounded-full border border-muted-foreground/30 text-[9px] font-semibold text-muted-foreground cursor-help">i</span>
                </TooltipTrigger>
                <TooltipContent side="right" className="max-w-60 text-xs">
                  365 × 24 = 8,760 hours, or 366 × 24 = 8,784 hours for a leap year.
                </TooltipContent>
              </Tooltip>
            </span>
          }
        >
          <div className="flex items-center gap-2">
            <Input
              type="number" min={0} max={8784} step={100}
              value={hoursYear}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                if (!isNaN(v) && v >= 0 && v <= 8784) {
                  onHoursYearChange(v);
                  engineInstance.setPlantParameter("HOURS_YEAR", v, "h/yr");
                }
              }}
              className="h-9 font-mono text-sm"
            />
            <span className="text-xs text-muted-foreground whitespace-nowrap">h / yr</span>
          </div>
        </Field>

        <Field label="Plant Availability">
          <div className="flex items-center gap-2">
            <Input
              type="number" min={0} max={100} step={0.1}
              value={plantAvailability}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                if (!isNaN(v) && v >= 0 && v <= 100) onPlantAvailabilityChange(v);
              }}
              className="h-9 font-mono text-sm"
            />
            <span className="text-xs text-muted-foreground whitespace-nowrap">%</span>
          </div>
        </Field>

        <Field label="Effective Operating Hours">
          <div className="flex items-center gap-2">
            <div className="h-9 flex-1 rounded-md border border-border bg-muted/50 px-3 flex items-center font-mono text-sm">
              {effectiveHours.toLocaleString()}
            </div>
            <span className="text-xs text-muted-foreground whitespace-nowrap">h / yr</span>
          </div>
          <p className="text-[10px] text-muted-foreground mt-1">Annual Hours × Plant Availability.</p>
        </Field>
      </Section>

      <Section id="critical-path" title="Critical Path">
        <div className="rounded-lg border border-border bg-muted/30 p-2.5 sm:p-3 space-y-3">
          <div className="flex items-center gap-2">
            <Route className="h-4 w-4 text-primary" />
            <Label className="text-xs font-semibold">Critical Path</Label>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-flex items-center justify-center h-4 w-4 rounded-full border border-muted-foreground/30 text-[9px] font-semibold text-muted-foreground cursor-help">i</span>
              </TooltipTrigger>
              <TooltipContent side="right" className="max-w-52 text-xs">
                Equipment on the critical path inherits the plant availability factor.
              </TooltipContent>
            </Tooltip>
          </div>

          <Button
            variant={criticalPathMode ? "default" : "outline"}
            size="sm"
            className={`h-9 w-full text-xs gap-2 ${criticalPathMode ? "ring-2 ring-primary/40" : ""}`}
            onClick={() => {
              onToggleCriticalPathMode?.();
              if (!criticalPathMode) onOpenChange(false);
            }}
          >
            <Route className="h-3.5 w-3.5" />
            {criticalPathMode ? `Done (${criticalPathNodeIds.size} selected)` : "Select on Canvas"}
          </Button>

          {criticalNodes.length > 0 && (
            <div className="space-y-1.5 pt-1">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
                Selected Equipment ({criticalNodes.length})
              </p>
              <div className="space-y-1">
                {criticalNodes.map((node) => (
                  <div key={node.id} className="flex items-center gap-2 rounded-md border border-border bg-card px-2.5 py-1.5 group/item">
                    <div className="h-1.5 w-1.5 rounded-full bg-amber-500 shrink-0" />
                    <span className="text-[10px] font-medium text-foreground flex-1 truncate">{node.data.label as string}</span>
                    <span className="text-[9px] font-mono text-muted-foreground whitespace-nowrap shrink-0">
                      {effectiveHours.toLocaleString()} h
                    </span>
                    <button
                      onClick={() => removeFromCriticalPath(node.id)}
                      className="h-4 w-4 rounded flex items-center justify-center text-muted-foreground opacity-0 group-hover/item:opacity-100 hover:text-destructive hover:bg-destructive/10"
                      title="Remove from critical path"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {availableToAdd.length > 0 && (
            <Popover open={addOpen} onOpenChange={setAddOpen}>
              <PopoverTrigger asChild>
                <Button variant="ghost" size="sm" className="h-7 w-full text-[10px] gap-1.5 text-muted-foreground hover:text-foreground">
                  <Plus className="h-3 w-3" /> Add Equipment
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-64 p-1.5" side="bottom" align="start">
                <ScrollArea className="max-h-48">
                  <div className="space-y-0.5">
                    {availableToAdd.map((node) => (
                      <button
                        key={node.id}
                        onClick={() => addToCriticalPath(node.id)}
                        className="w-full text-left rounded-md px-2.5 py-1.5 text-[10px] font-medium hover:bg-accent"
                      >
                        {node.data.label as string}
                      </button>
                    ))}
                  </div>
                </ScrollArea>
              </PopoverContent>
            </Popover>
          )}

          {criticalNodes.length === 0 && (
            <p className="text-[10px] text-muted-foreground/60 italic text-center py-1">No equipment selected yet</p>
          )}
        </div>
      </Section>
    </div>
  );
}

/* ───────────────────────────── TAB 3 — History ───────────────────────────── */

function HistoryTab(props: Props) {
  const { listVersions, restoreVersion, onRestored, onOpenChange } = props;
  const [versions, setVersions] = useState<VersionEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [restoring, setRestoring] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listVersions()
      .then((list) => { if (!cancelled) setVersions(list); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [listVersions, reloadKey]);

  const fmtRelative = (date: Date) => {
    const sec = Math.round((Date.now() - date.getTime()) / 1000);
    if (sec < 60) return `${sec}s ago`;
    const min = Math.round(sec / 60);
    if (min < 60) return `${min} min ago`;
    const hr = Math.round(min / 60);
    if (hr < 24) return `${hr} h ago`;
    return `${Math.round(hr / 24)} d ago`;
  };

  const handleRestore = async (entry: VersionEntry) => {
    setRestoring(entry.path);
    try {
      const restored = await restoreVersion(entry.path);
      if (restored) {
        onRestored(restored);
        toast.success(`Restored snapshot from ${entry.createdAt.toLocaleString()}`);
        onOpenChange(false);
      } else {
        toast.error("Could not restore this version");
      }
    } finally {
      setRestoring(null);
    }
  };

  return (
    <div className="space-y-4">
      <Section id="snapshots" title="Snapshots">
        <div className="flex items-center justify-between">
          <p className="text-[11px] text-muted-foreground">
            {loading ? "Loading…" : `${versions.length} snapshot${versions.length === 1 ? "" : "s"} available`}
          </p>
          <Button variant="ghost" size="sm" className="h-7 text-[11px] gap-1.5" onClick={() => setReloadKey((k) => k + 1)} disabled={loading}>
            <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} /> Refresh
          </Button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-8 text-xs text-muted-foreground gap-2">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading snapshots…
          </div>
        ) : versions.length === 0 ? (
          <div className="py-8 text-center text-xs text-muted-foreground">
            No snapshots yet. Make a few changes to start building version history.
          </div>
        ) : (
          <ul className="space-y-1.5">
            {versions.map((v) => (
              <li key={v.path} className="flex items-center justify-between rounded-md border border-border bg-card px-3 py-2 text-xs">
                <div className="flex flex-col min-w-0">
                  <span className="font-medium text-card-foreground truncate">{v.createdAt.toLocaleString()}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {fmtRelative(v.createdAt)}{v.size ? ` · ${(v.size / 1024).toFixed(1)} KB` : ""}
                  </span>
                </div>
                <Button size="sm" variant="outline" className="h-7 text-[11px]" disabled={restoring !== null} onClick={() => handleRestore(v)}>
                  {restoring === v.path ? <Loader2 className="h-3 w-3 animate-spin" /> : <RotateCcw className="h-3 w-3" />}
                  <span className="ml-1">Restore</span>
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}

/* ────────────────────────── TAB — Identifiers ────────────────────────────── */

function IdentifiersTab(props: Props) {
  const {
    showNodeIds, onShowNodeIdsChange,
    debugNodeIds, onDebugNodeIdsChange,
    labelNormPrefs, onLabelNormPrefChange, onResetLabelNormPrefs,
    allNodes, retiredDisplayIds,
  } = props;
  return (
    <div className="space-y-6">
      <Section id="badges" title="Identifier Badges">
        <ToggleRow
          icon={<Hash className="h-4 w-4" />}
          title="Component IDs"
          description="Render the E1 / C1 / G1 badges and per-label occurrence indices."
          checked={showNodeIds}
          onChange={onShowNodeIdsChange}
        />
        <ToggleRow
          icon={<Bug className="h-4 w-4" />}
          title="ID Debug Overlay"
          description="QA highlight: show whether each node's duplicate counter is active, unique, or suppressed."
          checked={debugNodeIds}
          onChange={onDebugNodeIdsChange}
        />
      </Section>

      <Section
        id="normalization"
        title="Label Normalization Rules"
      >
        <div className="rounded-lg border border-border divide-y divide-border">
          <ToggleRow
            icon={<TextCursor className="h-4 w-4" />}
            title="Trim & collapse whitespace"
            description="Treat ' Pump ' and 'Pump' as the same label."
            checked={labelNormPrefs.trim}
            onChange={(v) => onLabelNormPrefChange("trim", v)}
          />
          <ToggleRow
            icon={<TextCursor className="h-4 w-4" />}
            title="Case-insensitive matching"
            description="Group 'Pump', 'pump', and 'PUMP' as duplicates."
            checked={labelNormPrefs.caseFold}
            onChange={(v) => onLabelNormPrefChange("caseFold", v)}
          />
          <ToggleRow
            icon={<TextCursor className="h-4 w-4" />}
            title="Strip diacritics"
            description="Treat 'Électrolyseur' and 'Electrolyseur' as the same label."
            checked={labelNormPrefs.stripDiacritics}
            onChange={(v) => onLabelNormPrefChange("stripDiacritics", v)}
          />
          <ToggleRow
            icon={<TextCursor className="h-4 w-4" />}
            title="Strip trailing numeric suffix"
            description="Drop manual ' #2', ' (3)', ' - 4' suffixes so they group with the base label."
            checked={labelNormPrefs.stripNumericSuffix}
            onChange={(v) => onLabelNormPrefChange("stripNumericSuffix", v)}
          />
        </div>

        <Field label="Placeholder labels (treated as 'no label')">
          <PlaceholderEditor
            value={labelNormPrefs.placeholders}
            onChange={(next) => onLabelNormPrefChange("placeholders", next)}
          />
          <p className="text-[10px] text-muted-foreground mt-1">
            Comma-separated, case-insensitive. Empty labels are always suppressed.
          </p>
        </Field>

        <div className="flex justify-end">
          <Button
            variant="ghost" size="sm" className="h-7 text-[11px] gap-1.5"
            onClick={() => { onResetLabelNormPrefs(); toast.success("Label normalization rules reset to defaults."); }}
          >
            <RotateCcw className="h-3 w-3" /> Reset to defaults
          </Button>
        </div>
      </Section>

      <Section
        id="normalization-preview"
        title="Normalization Preview"
      >
        <NormalizationPreview prefs={labelNormPrefs} allNodes={allNodes} />
      </Section>

      <Section
        id="traceability"
        title="ID Traceability"
      >
        <TraceabilityPanel allNodes={allNodes} retiredDisplayIds={retiredDisplayIds} />
      </Section>
    </div>
  );
}

/* ──────────────────────────── TAB — Plant Display ────────────────────────── */

function DisplayTab(props: Props) {
  const {
    layoutOrientation, onLayoutOrientationChange,
    compactNodes, onCompactNodesChange,
    straightEdges, onStraightEdgesChange,
    carrierNodes,
  } = props;

  // Distinct carrier labels currently on the canvas (sorted).
  const carrierLabels = useMemo(() => {
    const set = new Set<string>();
    for (const n of carrierNodes) {
      const l = (n.data as { label?: unknown })?.label;
      if (typeof l === "string" && l.trim()) set.add(l);
    }
    return [...set].sort((a, b) => a.localeCompare(b));
  }, [carrierNodes]);

  // Re-render when overrides change so swatches update live.
  const [, force] = useState(0);
  useEffect(() => subscribeCarrierOverrides(() => force((x) => x + 1)), []);

  return (
    <div className="space-y-6">
      <Section id="layout" title="Canvas Layout">
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={() => onLayoutOrientationChange("horizontal")}
            className={`flex flex-col items-center justify-center gap-1.5 rounded-lg border p-3 transition-colors ${
              layoutOrientation === "horizontal"
                ? "border-primary/50 bg-primary/10 text-primary"
                : "border-border hover:bg-accent"
            }`}
          >
            <ArrowRightLeft className="h-4 w-4" />
            <span className="text-xs font-semibold">Horizontal</span>
            <span className="text-[10px] opacity-80">Left → Right</span>
          </button>
          <button
            onClick={() => onLayoutOrientationChange("vertical")}
            className={`flex flex-col items-center justify-center gap-1.5 rounded-lg border p-3 transition-colors ${
              layoutOrientation === "vertical"
                ? "border-primary/50 bg-primary/10 text-primary"
                : "border-border hover:bg-accent"
            }`}
          >
            <ArrowDownUp className="h-4 w-4" />
            <span className="text-xs font-semibold">Vertical</span>
            <span className="text-[10px] opacity-80">Top → Bottom</span>
          </button>
        </div>
        <div className="mt-3 flex items-center justify-between rounded-lg border border-border bg-muted/30 px-3 py-2">
          <div className="min-w-0">
            <p className="text-xs font-semibold text-foreground">Compact Equipment Nodes</p>
            <p className="text-[10px] text-muted-foreground">Tighter padding and smaller chrome; NAME and ID stay readable.</p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={compactNodes}
            onClick={() => onCompactNodesChange(!compactNodes)}
            className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors ${
              compactNodes ? "bg-primary" : "bg-muted"
            }`}
          >
            <span className={`inline-block h-4 w-4 rounded-full bg-background shadow transition-transform ${compactNodes ? "translate-x-4" : "translate-x-0.5"}`} />
          </button>
        </div>
        <div className="mt-3 flex items-center justify-between rounded-lg border border-border bg-muted/30 px-3 py-2">
          <div className="min-w-0">
            <p className="text-xs font-semibold text-foreground">Straight-Line Connections</p>
            <p className="text-[10px] text-muted-foreground">Render edges as a single straight segment between handles instead of orthogonal smooth-step paths.</p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={straightEdges}
            onClick={() => onStraightEdgesChange(!straightEdges)}
            className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors ${
              straightEdges ? "bg-primary" : "bg-muted"
            }`}
          >
            <span className={`inline-block h-4 w-4 rounded-full bg-background shadow transition-transform ${straightEdges ? "translate-x-4" : "translate-x-0.5"}`} />
          </button>
        </div>
      </Section>

      <Section id="legend" title="Legend Recolor (RGB)">
        <div className="rounded-lg border border-border">
          <div className="grid grid-cols-[1fr_auto_auto] items-center gap-2 px-3 py-2 border-b border-border bg-muted/40 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
            <span><Palette className="inline h-3 w-3 mr-1" /> Carrier</span>
            <span>Color</span>
            <span>Reset</span>
          </div>
          {carrierLabels.length === 0 ? (
            <div className="px-3 py-6 text-center text-[11px] text-muted-foreground italic">
              No carriers on the canvas yet, add a stream to recolor it here.
            </div>
          ) : (
            <ul className="divide-y divide-border">
              {carrierLabels.map((label) => {
                const overrides = getAllCarrierOverrides();
                const hasOverride = label in overrides;
                const current = getColorFromResource(label);
                const rgb = hexToRgb(current);
                // Normalise whatever the resource returns (hex/rgb/hsl) into
                // a hex string the color picker can consume safely. Without
                // this, react-colorful keeps re-emitting onChange to coerce
                // non-hex inputs, which triggers an infinite render loop
                // (React error #185) through the override subscription.
                const parsed = rgb ?? parseColor(current);
                const currentHex = parsed
                  ? `#${parsed.r.toString(16).padStart(2, "0")}${parsed.g.toString(16).padStart(2, "0")}${parsed.b.toString(16).padStart(2, "0")}`
                  : "#888888";
                const commitColor = (c: string) => {
                  if (c.toLowerCase() === currentHex.toLowerCase()) return;
                  setCarrierColorOverride(label, c);
                };
                return (
                  <li key={label} className="grid grid-cols-[1fr_auto_auto] items-center gap-2 px-3 py-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="h-4 w-4 rounded-sm border border-border shrink-0" style={{ backgroundColor: current }} />
                      <span className="text-xs font-medium truncate">{label}</span>
                      {hasOverride && (
                        <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-primary/15 text-primary font-bold">
                          Custom
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Popover>
                        <PopoverTrigger asChild>
                          <button
                            type="button"
                            aria-label={`Pick color for ${label}`}
                            className="h-7 w-9 rounded border border-border cursor-pointer"
                            style={{ backgroundColor: current }}
                          />
                        </PopoverTrigger>
                        <PopoverContent className="w-auto p-2 space-y-2" align="start">
                          <PrecisionColorPicker
                            color={currentHex}
                            onChange={commitColor}
                          />
                          <HexInputField
                            value={currentHex}
                            onChange={commitColor}
                          />
                          <ColorPresetRow
                            currentColor={currentHex}
                            onPick={commitColor}
                          />
                        </PopoverContent>
                      </Popover>
                      <Input
                        value={current}
                        onChange={(e) => setCarrierColorOverride(label, e.target.value)}
                        className="h-7 w-32 font-mono text-[10px]"
                        aria-label={`Color value for ${label}`}
                      />
                    </div>
                    <Button
                      variant="ghost" size="sm" className="h-7 w-7 p-0"
                      disabled={!hasOverride}
                      onClick={() => setCarrierColorOverride(label, null)}
                      title="Reset to default color"
                    >
                      <RotateCcw className="h-3 w-3" />
                    </Button>
                  </li>
                );
              })}
            </ul>
          )}
          <div className="flex items-center justify-end px-3 py-2 border-t border-border bg-muted/20">
            <Button
              variant="ghost" size="sm" className="h-7 text-[11px]"
              onClick={() => { resetCarrierOverrides(); toast.success("All carrier colors restored to defaults."); }}
            >
              Reset all colors
            </Button>
          </div>
        </div>
      </Section>

    </div>
  );
}

/* ─────────────────────────── Shared sub-components ───────────────────────── */

function Section({
  id, title, subtitle, icon, step, progress, children,
}: {
  id?: string;
  title: string;
  subtitle?: string;
  icon?: React.ComponentType<{ className?: string }>;
  step?: number;
  progress?: { requiredFilled: number; requiredTotal: number; optionalFilled: number; optionalTotal: number };
  children: React.ReactNode;
}) {
  const Icon = icon;
  const totalCount = progress ? progress.requiredTotal + progress.optionalTotal : 0;
  const filledCount = progress ? progress.requiredFilled + progress.optionalFilled : 0;
  const reqComplete = progress ? progress.requiredTotal === 0 || progress.requiredFilled >= progress.requiredTotal : false;
  const totalPct = totalCount === 0 ? 0 : Math.round((filledCount / totalCount) * 100);
  return (
    <section
      data-section={id}
      className="scroll-mt-4 rounded-lg border border-border bg-card shadow-sm overflow-hidden"
    >
      <header className="flex items-center gap-2 sm:gap-2.5 px-3 sm:px-4 py-2 sm:py-2.5 bg-muted/40 border-b border-border">
        {step !== undefined && (
          <span className="inline-flex items-center justify-center h-5 w-5 rounded-full bg-primary/15 text-primary text-[10px] font-bold shrink-0">
            {step}
          </span>
        )}
        {Icon && (
          <span className="inline-flex items-center justify-center h-6 w-6 rounded-md bg-primary/10 text-primary shrink-0">
            <Icon className="h-3.5 w-3.5" />
          </span>
        )}
        <div className="min-w-0 flex-1">
          <h3 className="text-xs font-bold uppercase tracking-wider text-foreground leading-tight">{title}</h3>
          {subtitle && <p className="text-[10px] text-muted-foreground mt-0.5 leading-snug">{subtitle}</p>}
        </div>
        {progress && (
          <div className="hidden sm:flex items-center gap-2 shrink-0">
            <div className="flex items-center gap-1.5 min-w-[140px]">
              <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                <div className={`h-full rounded-full transition-all ${reqComplete ? "bg-success" : "bg-primary/70"}`} style={{ width: `${totalPct}%` }} />
              </div>
              <span className="text-[10px] font-mono text-muted-foreground tabular-nums">{filledCount}/{totalCount}</span>
            </div>
          </div>
        )}
      </header>
      <div className="p-3 sm:p-4 space-y-3 bg-background/40">{children}</div>
    </section>
  );
}


function Field({ label, required, error, children }: { label: React.ReactNode; required?: boolean; error?: string | null; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <Label className="text-[11px] font-semibold">
        {label}
        {required && <span className="text-destructive ml-0.5" aria-hidden="true">*</span>}
      </Label>
      <div className={error ? "[&_input]:border-destructive [&_input]:focus:ring-destructive [&_select]:border-destructive [&_select]:focus:ring-destructive" : undefined}>
        {children}
      </div>
      {error && <p className="text-[10px] font-medium text-destructive leading-tight">{error}</p>}
    </div>
  );
}

function ToggleRow({
  icon, title, description, checked, onChange,
}: { icon: React.ReactNode; title: string; description: string; checked: boolean; onChange: (next: boolean) => void; }) {
  return (
    <button
      onClick={() => onChange(!checked)}
      aria-pressed={checked}
      className={`w-full flex items-start gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors ${
        checked ? "border-primary/40 bg-primary/5" : "border-border hover:bg-accent"
      }`}
    >
      <div className={`mt-0.5 ${checked ? "text-primary" : "text-muted-foreground"}`}>{icon}</div>
      <div className="flex-1 min-w-0">
        <p className="text-xs font-semibold text-foreground">{title}</p>
        <p className="text-[10px] text-muted-foreground">{description}</p>
      </div>
      <div
        className={`mt-0.5 h-5 w-9 rounded-full border transition-colors relative ${
          checked ? "bg-primary border-primary" : "bg-muted border-border"
        }`}
      >
        <span
          className={`absolute top-0.5 h-3.5 w-3.5 rounded-full bg-background transition-all ${
            checked ? "left-[18px]" : "left-0.5"
          }`}
        />
      </div>
    </button>
  );
}

export default PlantSettingsDialog;

function PlaceholderEditor({
  value, onChange,
}: { value: string[]; onChange: (next: string[]) => void }) {
  const [draft, setDraft] = useState(value.join(", "));
  useEffect(() => { setDraft(value.join(", ")); }, [value]);

  const MAX_LEN = 32;
  const MAX_COUNT = 50;
  // Allowed: letters, digits, spaces, and a small punctuation set commonly
  // used as placeholder tokens (?, /, -, _, .). Rejects control chars, HTML
  // metacharacters (<, >, &, "), and other risky punctuation.
  const ALLOWED = /^[\p{L}\p{N} ?/\-_.]+$/u;

  // Live-validate the draft and produce a cleaned list + structured errors.
  const validation = useMemo(() => {
    const tokens = draft.split(",").map((s) => s.trim()).filter((s) => s.length > 0);
    const errors: string[] = [];
    const lowered: string[] = [];
    const seen = new Set<string>();
    const dupes = new Set<string>();
    const tooLong: string[] = [];
    const invalid: string[] = [];

    for (const t of tokens) {
      const lc = t.toLowerCase();
      if (lc.length > MAX_LEN) { tooLong.push(t); continue; }
      if (!ALLOWED.test(lc))   { invalid.push(t); continue; }
      if (seen.has(lc))        { dupes.add(lc); continue; }
      seen.add(lc);
      lowered.push(lc);
    }

    if (lowered.length > MAX_COUNT) {
      errors.push(`Too many placeholders (${lowered.length}). Limit is ${MAX_COUNT}.`);
    }
    if (dupes.size > 0) {
      errors.push(`Duplicate placeholders ignored: ${Array.from(dupes).join(", ")}`);
    }
    if (tooLong.length > 0) {
      errors.push(`Too long (max ${MAX_LEN} chars): ${tooLong.join(", ")}`);
    }
    if (invalid.length > 0) {
      errors.push(`Invalid characters: ${invalid.join(", ")} (letters, digits, spaces and ? / - _ . only)`);
    }

    return {
      cleaned: lowered.slice(0, MAX_COUNT),
      errors,
      hasErrors: errors.length > 0,
    };
  }, [draft]);

  const commit = () => {
    // Always persist the cleaned/lowercased/deduped list — even when there
    // are warnings about ignored entries — so invalid tokens are dropped
    // rather than corrupting the stored prefs.
    onChange(validation.cleaned);
    setDraft(validation.cleaned.join(", "));
  };

  return (
    <div className="space-y-1">
      <Input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
        placeholder="untitled, new, n/a, tbd, ?"
        aria-invalid={validation.hasErrors || undefined}
        className={`h-9 text-xs font-mono ${
          validation.hasErrors
            ? "border-destructive focus-visible:ring-destructive/40"
            : ""
        }`}
      />
      {validation.hasErrors && (
        <ul role="alert" className="text-[10px] text-destructive space-y-0.5">
          {validation.errors.map((msg, i) => (
            <li key={i}>• {msg}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ─────────────────────────── Traceability Panel ──────────────────────────── */

const PREFIX_META: Array<{ prefix: "E" | "C" | "G"; label: string; nodeType: string; tone: string }> = [
  { prefix: "E", label: "Equipment", nodeType: "equipment", tone: "text-teal-600 dark:text-teal-400" },
  { prefix: "C", label: "Carrier",   nodeType: "carrier",   tone: "text-sky-600 dark:text-sky-400" },
  { prefix: "G", label: "Gate",      nodeType: "gate",      tone: "text-amber-600 dark:text-amber-400" },
];

function parseDisplayNum(prefix: string, id: string): number | null {
  if (!id.startsWith(prefix)) return null;
  const n = Number.parseInt(id.slice(prefix.length), 10);
  return Number.isFinite(n) && n > 0 ? n : null;
}

/* ─────────────────────── Normalization Preview ─────────────────────── */

const SAMPLE_LABELS = [
  "Pump", "pump", " PUMP ", "Pump #1", "Pump (2)", "Pump - 3",
  "Électrolyseur", "electrolyseur", "ELECTROLYSEUR",
  "H2", "h2", " H2 ",
  "Untitled", "TBD", "?",
  "Heat Exchanger", "heat  exchanger",
];

function NormalizationPreview({
  prefs,
  allNodes,
}: {
  prefs: LabelNormalizationPrefs;
  allNodes: Node[];
}) {
  const [customInput, setCustomInput] = useState("");

  // Pull distinct labels from canvas to enrich the preview with real data.
  const canvasLabels = useMemo(() => {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const n of allNodes) {
      const l = (n.data as { label?: unknown })?.label;
      if (typeof l === "string" && !seen.has(l)) {
        seen.add(l);
        out.push(l);
      }
    }
    return out;
  }, [allNodes]);

  const customLabels = useMemo(
    () => customInput.split("\n").map((s) => s).filter((s) => s.length > 0),
    [customInput],
  );

  const allLabels = useMemo(
    () => Array.from(new Set([...SAMPLE_LABELS, ...canvasLabels, ...customLabels])),
    [canvasLabels, customLabels],
  );

  // Group labels by their normalized key under the CURRENT prefs.
  const groups = useMemo(() => {
    const map = new Map<string, { key: string; labels: string[] }>();
    const unlabelled: string[] = [];
    for (const raw of allLabels) {
      const key = normalizeLabel(raw, prefs);
      if (key === null) {
        unlabelled.push(raw);
        continue;
      }
      const entry = map.get(key);
      if (entry) entry.labels.push(raw);
      else map.set(key, { key, labels: [raw] });
    }
    const groupList = Array.from(map.values()).sort(
      (a, b) => b.labels.length - a.labels.length || a.key.localeCompare(b.key),
    );
    return { groupList, unlabelled };
  }, [allLabels, prefs]);

  const dupGroups = groups.groupList.filter((g) => g.labels.length > 1);
  const uniqueGroups = groups.groupList.filter((g) => g.labels.length === 1);

  return (
    <div className="space-y-3">
      {/* Custom input */}
      <div>
        <Label className="text-[11px] text-muted-foreground">Try your own labels (one per line)</Label>
        <textarea
          value={customInput}
          onChange={(e) => setCustomInput(e.target.value)}
          rows={3}
          placeholder={"My Pump\nmy pump\nMY PUMP #1"}
          className="mt-1 w-full rounded-md border border-border bg-background px-2 py-1.5 text-[11px] font-mono text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        />
      </div>

      {/* Summary */}
      <div className="grid grid-cols-3 gap-2 text-[11px]">
        <div className="rounded-md border border-border bg-muted/40 px-2 py-1.5">
          <div className="text-muted-foreground text-[10px]">Total labels</div>
          <div className="font-bold tabular-nums">{allLabels.length}</div>
        </div>
        <div className="rounded-md border border-amber-500/30 bg-amber-500/5 px-2 py-1.5">
          <div className="text-muted-foreground text-[10px]">Duplicate groups</div>
          <div className="font-bold tabular-nums text-amber-600 dark:text-amber-400">{dupGroups.length}</div>
        </div>
        <div className="rounded-md border border-border bg-muted/40 px-2 py-1.5">
          <div className="text-muted-foreground text-[10px]">Suppressed (no label)</div>
          <div className="font-bold tabular-nums">{groups.unlabelled.length}</div>
        </div>
      </div>

      {/* Duplicate groups */}
      {dupGroups.length > 0 && (
        <div className="rounded-md border border-border">
          <div className="px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground border-b border-border bg-muted/30">
            Duplicates, collapsed under the current rules
          </div>
          <ul className="divide-y divide-border max-h-48 overflow-y-auto">
            {dupGroups.map((g) => (
              <li key={g.key} className="px-2 py-1.5 text-[11px]">
                <div className="flex items-center justify-between gap-2">
                  <code className="font-mono text-foreground bg-muted/40 px-1 rounded">{g.key}</code>
                  <span className="text-[10px] text-muted-foreground tabular-nums">×{g.labels.length}</span>
                </div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {g.labels.map((l, i) => (
                    <span key={`${l}-${i}`} className="inline-block rounded border border-border bg-background px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
                      {l === "" ? "∅" : l}
                    </span>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Unique + suppressed (collapsed) */}
      <details className="rounded-md border border-border">
        <summary className="cursor-pointer px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground">
          Unique labels ({uniqueGroups.length}) & suppressed ({groups.unlabelled.length})
        </summary>
        <div className="border-t border-border p-2 space-y-2 max-h-40 overflow-y-auto">
          {uniqueGroups.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {uniqueGroups.map((g) => (
                <span key={g.key} className="inline-block rounded border border-border bg-background px-1.5 py-0.5 text-[10px] font-mono text-foreground">
                  {g.labels[0]}
                </span>
              ))}
            </div>
          )}
          {groups.unlabelled.length > 0 && (
            <div>
              <div className="text-[10px] text-muted-foreground mb-1">Suppressed (treated as no label):</div>
              <div className="flex flex-wrap gap-1">
                {groups.unlabelled.map((l, i) => (
                  <span key={`u-${i}`} className="inline-block rounded border border-dashed border-border bg-muted/20 px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground line-through">
                    {l === "" ? "∅" : l}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </details>
    </div>
  );
}

function TraceabilityPanel({
  allNodes, retiredDisplayIds,
}: { allNodes: Node[]; retiredDisplayIds: string[] }) {
  const groups = useMemo(() => {
    const retiredSet = new Set(retiredDisplayIds);
    return PREFIX_META.map(({ prefix, label, nodeType, tone }) => {
      const current: Array<{ displayId: string; num: number; nodeLabel: string; nodeId: string; conflict: boolean }> = [];
      for (const n of allNodes) {
        if (n.type !== nodeType) continue;
        const did = (n.data as { displayId?: unknown })?.displayId;
        if (typeof did !== "string") continue;
        const num = parseDisplayNum(prefix, did);
        if (num === null) continue;
        const rawLabel = (n.data as { label?: unknown })?.label;
        const nodeLabel = typeof rawLabel === "string" && rawLabel.trim() ? rawLabel : "(unlabeled)";
        current.push({ displayId: did, num, nodeLabel, nodeId: n.id, conflict: retiredSet.has(did) });
      }
      current.sort((a, b) => a.num - b.num);

      const retired = retiredDisplayIds
        .map((id) => ({ id, num: parseDisplayNum(prefix, id) }))
        .filter((r): r is { id: string; num: number } => r.num !== null)
        .sort((a, b) => a.num - b.num);

      const maxNum = Math.max(0, ...current.map((c) => c.num), ...retired.map((r) => r.num));
      const conflicts = current.filter((c) => c.conflict);
      return { prefix, label, tone, current, retired, maxNum, conflicts };
    });
  }, [allNodes, retiredDisplayIds]);

  const allConflicts = useMemo(
    () => groups.flatMap((g) => g.conflicts.map((c) => ({ ...c, prefix: g.prefix, label: g.label }))),
    [groups],
  );

  return (
    <div className="space-y-3">
      {allConflicts.length > 0 && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-destructive/50 bg-destructive/10 px-3 py-2.5"
        >
          <AlertTriangle className="h-4 w-4 text-destructive shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0 space-y-1.5">
            <p className="text-[11px] font-bold text-destructive">
              {allConflicts.length} display ID conflict{allConflicts.length === 1 ? "" : "s"} detected
            </p>
            <p className="text-[10px] text-destructive/90 leading-relaxed">
              The following node{allConflicts.length === 1 ? " has" : "s have"} a pinned display ID that collides with a retired (reserved) number. This usually happens after restoring a snapshot or importing a node, historical references may now be ambiguous.
            </p>
            <ul className="space-y-0.5 pt-1">
              {allConflicts.map((c) => (
                <li key={c.nodeId} className="flex items-center gap-2 text-[10px]">
                  <span className="inline-flex items-center justify-center min-w-[28px] h-5 px-1.5 rounded font-mono font-bold border border-destructive/40 bg-background text-destructive">
                    {c.displayId}
                  </span>
                  <span className="text-foreground/90 truncate" title={c.nodeLabel}>
                    {c.label} · {c.nodeLabel}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
      {groups.map((g) => (
        <div key={g.prefix} className="rounded-lg border border-border overflow-hidden">
          <header className="flex items-center justify-between gap-2 bg-muted/40 border-b border-border px-3 py-2">
            <div className="flex items-center gap-2">
              <ListOrdered className={`h-3.5 w-3.5 ${g.tone}`} />
              <span className={`text-xs font-bold ${g.tone}`}>{g.prefix}</span>
              <span className="text-[11px] font-semibold text-foreground">{g.label}</span>
            </div>
            <div className="flex items-center gap-3 text-[10px] text-muted-foreground font-mono">
              <span><span className="text-foreground font-semibold">{g.current.length}</span> active</span>
              <span><span className="text-destructive font-semibold">{g.retired.length}</span> retired</span>
              <span>max #{g.maxNum || "–"}</span>
            </div>
          </header>
          <div className="grid grid-cols-2 divide-x divide-border">
            <div className="p-2.5 space-y-1.5 min-h-[80px]">
              <p className="text-[9px] uppercase tracking-wider text-muted-foreground font-semibold">Active</p>
              {g.current.length === 0 ? (
                <p className="text-[10px] italic text-muted-foreground/60">No active {g.label.toLowerCase()} nodes.</p>
              ) : (
                <ul className="space-y-1">
                  {g.current.map((c) => (
                    <li key={c.nodeId} className="flex items-center gap-2 text-[10px]">
                      <span
                        title={c.conflict ? `${c.displayId} conflicts with a retired/reserved ID` : undefined}
                        className={`inline-flex items-center justify-center min-w-[28px] h-5 px-1.5 rounded font-mono font-bold border bg-background ${
                          c.conflict
                            ? "border-destructive/60 text-destructive ring-1 ring-destructive/40"
                            : `border-border ${g.tone}`
                        }`}
                      >
                        {c.displayId}
                        {c.conflict && <AlertTriangle className="h-2.5 w-2.5 ml-1" />}
                      </span>
                      <span className="text-foreground truncate" title={c.nodeLabel}>{c.nodeLabel}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="p-2.5 space-y-1.5 min-h-[80px] bg-muted/20">
              <p className="text-[9px] uppercase tracking-wider text-muted-foreground font-semibold">Retired (reserved)</p>
              {g.retired.length === 0 ? (
                <p className="text-[10px] italic text-muted-foreground/60">None, no nodes have been deleted yet.</p>
              ) : (
                <div className="flex flex-wrap gap-1">
                  {g.retired.map((r) => (
                    <span
                      key={r.id}
                      title={`${r.id}, number reserved, will not be reused`}
                      className="inline-flex items-center h-5 px-1.5 rounded font-mono text-[10px] font-bold border border-destructive/30 text-destructive bg-destructive/5 line-through decoration-destructive/60"
                    >
                      {r.id}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
      <p className="text-[10px] text-muted-foreground italic">
        Numbering is monotonic per prefix. Deleted IDs are kept in the retired list and reserved against reuse so historical references in exports and reports remain unambiguous.
      </p>
    </div>
  );
}
