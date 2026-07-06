import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Plus, Trash2, ArrowRight, ArrowLeft, Settings2, Package, Info } from "lucide-react";
import { normalizeFlow } from "@/lib/seedInitialCanvas";

type FuelType = string;

export interface NewPlantCreatePayload {
  slug: string;
  name: string;
  location: string;
  country: string;
  fuelType: string;
  capacity: string;
  maturityStage: string;
  expectedCod: string;
  profile: Record<string, string>;
  form: unknown;
  /** Selected products (fuel + capacity). Used to seed the initial canvas
   *  with one carrier per product wired to the Offtake Market gate. */
  products: Array<{ fuelType: string; capacity: string; capacityUnit: string }>;
  /** Optional geo coordinates. Used to publish the plant to the Ecosystem Map. */
  latitude?: number;
  longitude?: number;
  /** Non-sensitive metadata mirrored to the map. */
  companyName?: string;
  primaryPathway?: string;
  /** Whether to publish (or enrich) this plant on the Ecosystem Map. Defaults to true. */
  publishToEcosystem?: boolean;
}

export interface NewPlantDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialValues?: {
    name?: string;
    location?: string;
    country?: string;
    capacity?: string;
    fuelType?: FuelType;
  };
  /** Called BEFORE navigation so the host page can register the new plant card and return the final unique slug. */
  onCreate?: (payload: NewPlantCreatePayload) => string | void | Promise<string | void>;
}

/* ── Option lists ── */
const PRIMARY_PATHWAYS = [
  "Synthetic Pathway", "Biogenic Pathway", "Thermochemical Pathway",
  "Hybrid Pathway", "Physical Recovery Pathway", "Other",
];
const PLANT_CONFIGS = ["New Build", "Retrofit", "Expansion", "Mixed"];
const SITE_ENVIRONMENTS = [
  "Coastal", "Inland", "Industrial Cluster", "Port Terminal", "Urban", "Rural", "Other",
];
const MATURITY_STAGES = [
  "Concept", "Pre Feasibility", "Feasibility", "Pre FEED", "FEED", "Permitting",
  "Pre FID", "FID", "Construction", "Commissioning", "Operating",
];
const CERTIFICATION_PHASES = [
  "Not Started", "Eligibility Scoping", "Data Collection", "Pre Assessment",
  "Documentation Prepared", "Auditor Engagement", "Certification Submitted",
  "Certified", "Surveillance",
];
const FUEL_TYPES = [
  "Hydrogen", "Ammonia", "Methanol", "Methane", "Diesel", "Kerosene",
  "Naphtha", "Butane", "Propane", "Ethanol", "Gasoline",
];
const CAPACITY_UNITS = [
  "Ton per Year", "Ton per Day", "Kilogram per Hour", "Normal Cubic Meter per Hour",
];

/* Comprehensive global country list */
const COUNTRIES = [
  "Afghanistan","Albania","Algeria","Andorra","Angola","Antigua and Barbuda","Argentina","Armenia","Australia","Austria",
  "Azerbaijan","Bahamas","Bahrain","Bangladesh","Barbados","Belarus","Belgium","Belize","Benin","Bhutan","Bolivia",
  "Bosnia and Herzegovina","Botswana","Brazil","Brunei","Bulgaria","Burkina Faso","Burundi","Cabo Verde","Cambodia",
  "Cameroon","Canada","Central African Republic","Chad","Chile","China","Colombia","Comoros","Congo","Costa Rica",
  "Croatia","Cuba","Cyprus","Czech Republic","Democratic Republic of the Congo","Denmark","Djibouti","Dominica",
  "Dominican Republic","Ecuador","Egypt","El Salvador","Equatorial Guinea","Eritrea","Estonia","Eswatini","Ethiopia",
  "Fiji","Finland","France","Gabon","Gambia","Georgia","Germany","Ghana","Greece","Grenada","Guatemala","Guinea",
  "Guinea-Bissau","Guyana","Haiti","Honduras","Hungary","Iceland","India","Indonesia","Iran","Iraq","Ireland","Israel",
  "Italy","Ivory Coast","Jamaica","Japan","Jordan","Kazakhstan","Kenya","Kiribati","Kuwait","Kyrgyzstan","Laos",
  "Latvia","Lebanon","Lesotho","Liberia","Libya","Liechtenstein","Lithuania","Luxembourg","Madagascar","Malawi",
  "Malaysia","Maldives","Mali","Malta","Marshall Islands","Mauritania","Mauritius","Mexico","Micronesia","Moldova",
  "Monaco","Mongolia","Montenegro","Morocco","Mozambique","Myanmar","Namibia","Nauru","Nepal","Netherlands",
  "New Zealand","Nicaragua","Niger","Nigeria","North Korea","North Macedonia","Norway","Oman","Pakistan","Palau",
  "Palestine","Panama","Papua New Guinea","Paraguay","Peru","Philippines","Poland","Portugal","Qatar","Romania",
  "Russia","Rwanda","Saint Kitts and Nevis","Saint Lucia","Saint Vincent and the Grenadines","Samoa","San Marino",
  "Sao Tome and Principe","Saudi Arabia","Senegal","Serbia","Seychelles","Sierra Leone","Singapore","Slovakia",
  "Slovenia","Solomon Islands","Somalia","South Africa","South Korea","South Sudan","Spain","Sri Lanka","Sudan",
  "Suriname","Sweden","Switzerland","Syria","Taiwan","Tajikistan","Tanzania","Thailand","Timor-Leste","Togo","Tonga",
  "Trinidad and Tobago","Tunisia","Turkey","Turkmenistan","Tuvalu","Uganda","Ukraine","United Arab Emirates",
  "United Kingdom","United States","Uruguay","Uzbekistan","Vanuatu","Vatican City","Venezuela","Vietnam","Yemen",
  "Zambia","Zimbabwe",
];

/* ── Form state types ── */
interface ProductBlock {
  id: string;
  fuelType: string;
  capacity: string;
  capacityUnit: string;
}

interface FormState {
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
  // Publishing
  publishToEcosystem: boolean;
}

const inputClass =
  "w-full h-9 rounded-md border border-border bg-card px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring";

const Field = ({
  label, required, error, children,
}: { label: React.ReactNode; required?: boolean; error?: string; children: React.ReactNode }) => (
  <div className="space-y-1">
    <Label className="text-[11px] font-semibold">
      {label}
      {required && <span className="text-destructive ml-0.5" aria-hidden="true">*</span>}
    </Label>
    <div className={error ? "[&_input]:border-destructive [&_select]:border-destructive" : undefined}>
      {children}
    </div>
    {error && <p className="text-[10px] font-medium text-destructive leading-tight">{error}</p>}
  </div>
);

function Section({
  title, icon: Icon, step, progress, children,
}: {
  title: string;
  icon?: React.ComponentType<{ className?: string }>;
  step: number;
  progress?: { filled: number; total: number; reqComplete: boolean };
  children: React.ReactNode;
}) {
  const pct = progress && progress.total > 0 ? Math.round((progress.filled / progress.total) * 100) : 0;
  return (
    <section className="rounded-lg border border-border bg-card shadow-sm overflow-hidden">
      <header className="flex items-center gap-2.5 px-4 py-2.5 bg-muted/40 border-b border-border">
        <span className="inline-flex items-center justify-center h-5 w-5 rounded-full bg-primary/15 text-primary text-[10px] font-bold shrink-0">
          {step}
        </span>
        {Icon && (
          <span className="inline-flex items-center justify-center h-6 w-6 rounded-md bg-primary/10 text-primary shrink-0">
            <Icon className="h-3.5 w-3.5" />
          </span>
        )}
        <div className="min-w-0 flex-1">
          <h3 className="text-xs font-bold uppercase tracking-wider text-foreground leading-tight">{title}</h3>
        </div>
        {progress && (
          <div className="hidden sm:flex items-center gap-1.5 min-w-[140px] shrink-0">
            <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
              <div className={`h-full rounded-full transition-all ${progress.reqComplete ? "bg-success" : "bg-primary/70"}`} style={{ width: `${pct}%` }} />
            </div>
            <span className="text-[10px] font-mono text-muted-foreground tabular-nums">{progress.filled}/{progress.total}</span>
          </div>
        )}
      </header>
      <div className="p-4 space-y-3 bg-background/40">{children}</div>
    </section>
  );
}

function makeProduct(): ProductBlock {
  return {
    id: crypto.randomUUID?.() ?? `p-${Date.now()}-${Math.random()}`,
    fuelType: "",
    capacity: "",
    capacityUnit: "Ton per Year",
  };
}

const NewPlantDialog = ({ open, onOpenChange, initialValues, onCreate }: NewPlantDialogProps) => {
  const navigate = useNavigate();
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [form, setForm] = useState<FormState>(() => ({
    projectName: initialValues?.name ?? "",
    plantName: "",
    companyName: "",
    projectLifetime: "",
    roleInProject: "",
    primaryPathway: "",
    plantConfiguration: "",
    country: initialValues?.country ?? "",
    region: "",
    city: initialValues?.location ?? "",
    address: "",
    postalCode: "",
    latitude: "",
    longitude: "",
    siteEnvironment: "",
    maturityStage: "",
    stageReferenceYear: "",
    certificationPhase: "",
    expectedCod: "",
    products: [
      {
        ...makeProduct(),
        fuelType: initialValues?.fuelType ?? "",
        capacity: initialValues?.capacity ?? "",
      },
    ],
    publishToEcosystem: true,
  }));
  const [errors, setErrors] = useState<Record<string, string>>({});

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const updateProduct = (id: string, patch: Partial<ProductBlock>) =>
    setForm((f) => ({
      ...f,
      products: f.products.map((p) => (p.id === id ? { ...p, ...patch } : p)),
    }));

  const addProduct = () => setForm((f) => ({ ...f, products: [...f.products, makeProduct()] }));
  const removeProduct = (id: string) =>
    setForm((f) => ({ ...f, products: f.products.filter((p) => p.id !== id) }));

  const validateStep1 = () => {
    const e: Record<string, string> = {};
    if (!form.projectName.trim()) e.projectName = "Required";
    if (!form.companyName.trim()) e.companyName = "Required";
    if (!form.country.trim()) e.country = "Required";
    if (!form.maturityStage.trim()) e.maturityStage = "Required";
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const validateStep2 = () => {
    setErrors({});
    return true;
  };

  const validateStep3 = () => {
    const e: Record<string, string> = {};
    const hasFuel = form.products.some((p) => p.fuelType.trim());
    if (!hasFuel) e.products = "At least one fuel type is required";
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const slug = useMemo(() => {
    const base = form.projectName.trim() || form.plantName.trim();
    return base.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
  }, [form.projectName, form.plantName]);

  const handleNext = () => {
    if (step === 1 && validateStep1()) setStep(2);
    else if (step === 2 && validateStep2()) setStep(3);
  };

  const handleCreate = async () => {
    if (!validateStep3()) return;
    // Persist plant profile so ProjectProfilePanel can pick it up
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
      maturityStage: form.maturityStage,
      siteEnvironment: form.siteEnvironment || "–",
      roleInProject: form.roleInProject || "–",
      projectLifetime: form.projectLifetime ? `${form.projectLifetime} years` : "–",
    };

    // Notify host so it can register the plant card (cloud + local cache).
    let finalSlug = slug;
    try {
      const createdSlug = await onCreate?.({
        slug,
        name: form.plantName || form.projectName,
        location: profile.location,
        country: form.country,
        fuelType: profile.fuelType,
        capacity: profile.productionCapacity,
        maturityStage: form.maturityStage,
        expectedCod: form.expectedCod,
        profile,
        form,
        products: form.products
          .filter((p) => p.fuelType.trim())
          .map((p) => ({
            fuelType: p.fuelType,
            capacity: p.capacity,
            capacityUnit: p.capacityUnit,
          })),
        latitude: form.latitude ? Number(form.latitude) : undefined,
        longitude: form.longitude ? Number(form.longitude) : undefined,
        companyName: form.companyName || undefined,
        primaryPathway: form.primaryPathway || undefined,
        publishToEcosystem: form.publishToEcosystem,
      });
      if (typeof createdSlug === "string" && createdSlug.trim()) finalSlug = createdSlug;
    } catch (err) {
      console.error("[NewPlantDialog] onCreate handler failed:", err);
    }

    try {
      localStorage.setItem(`gex_plant_profile_${finalSlug}`, JSON.stringify(profile));
      localStorage.setItem(`gex_plant_setup_${finalSlug}`, JSON.stringify(form));
    } catch { /* ignore */ }

    onOpenChange(false);
    navigate(`/canvas/${finalSlug}`);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl max-h-[88vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <Settings2 className="h-4 w-4 text-primary" />
            Create New Plant
          </DialogTitle>
          <DialogDescription className="sr-only">Create new plant</DialogDescription>
        </DialogHeader>

        {/* Step indicator, named tabs the user will complete */}
        {(() => {
          const stepDefs: { n: 1 | 2 | 3; label: string }[] = [
            { n: 1, label: "Project Profile" },
            { n: 2, label: "Plant Configuration" },
            { n: 3, label: "Products" },
          ];
          return (
            <div className="flex items-stretch gap-2 pt-1">
              {stepDefs.map(({ n, label }) => {
                const active = step === n;
                const done = step > n;
                return (
                  <button
                    type="button"
                    key={n}
                    onClick={() => { if (done) setStep(n); }}
                    disabled={!done && !active}
                    className={`flex-1 text-left rounded-md border px-3 py-2 transition-colors ${
                      active
                        ? "border-primary bg-primary/5"
                        : done
                        ? "border-border bg-card hover:bg-accent cursor-pointer"
                        : "border-border bg-muted/40 cursor-not-allowed"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold ${
                        active || done ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
                      }`}>{n}</span>
                      <span className={`text-xs font-medium ${
                        active ? "text-foreground" : done ? "text-foreground/80" : "text-muted-foreground"
                      }`}>{label}</span>
                    </div>
                    <div className={`mt-1.5 h-1 rounded-full ${active || done ? "bg-primary" : "bg-muted"}`} />
                  </button>
                );
              })}
            </div>
          );
        })()}

        {step === 1 && (
          <div className="space-y-4 pt-2">
            <Section title="Project Identity" step={1}>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="Project Name" required error={errors.projectName}>
                <input className={inputClass} value={form.projectName}
                  onChange={(e) => set("projectName", e.target.value)} maxLength={120} />
              </Field>
              <Field label="Plant Name">
                <input className={inputClass} value={form.plantName}
                  onChange={(e) => set("plantName", e.target.value)} maxLength={120} />
              </Field>
              <Field label="Company Name" required error={errors.companyName}>
                <input className={inputClass} value={form.companyName}
                  onChange={(e) => set("companyName", e.target.value)} maxLength={120} />
              </Field>
              <Field label="Project Lifetime (years)">
                <input type="number" min={0} className={inputClass} value={form.projectLifetime}
                  onChange={(e) => set("projectLifetime", e.target.value)} />
              </Field>
              </div>
            </Section>

            <Section title="Location" step={2}>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="Country" required error={errors.country}>
                <select className={inputClass} value={form.country}
                  onChange={(e) => set("country", e.target.value)}>
                  <option value="">– Select –</option>
                  {COUNTRIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </Field>
              <Field label="Region or State">
                <input className={inputClass} value={form.region}
                  onChange={(e) => set("region", e.target.value)} maxLength={100} />
              </Field>
              <Field label="City">
                <input className={inputClass} value={form.city}
                  onChange={(e) => set("city", e.target.value)} maxLength={100} />
              </Field>
              <Field label="Postal Code">
                <input className={inputClass} value={form.postalCode}
                  onChange={(e) => set("postalCode", e.target.value)} maxLength={20} />
              </Field>
              <div className="sm:col-span-2">
                <Field label="Address">
                  <input className={inputClass} value={form.address}
                    onChange={(e) => set("address", e.target.value)} maxLength={200} />
                </Field>
              </div>
              <Field label="Latitude (optional)">
                <input type="number" step="any" className={inputClass} value={form.latitude}
                  onChange={(e) => set("latitude", e.target.value)} />
              </Field>
              <Field label="Longitude (optional)">
                <input type="number" step="any" className={inputClass} value={form.longitude}
                  onChange={(e) => set("longitude", e.target.value)} />
              </Field>
              </div>
              <div className="mt-3 flex items-start justify-between gap-4 rounded-md border border-border bg-card/50 p-3">
                <div className="space-y-0.5">
                  <Label htmlFor="publish-ecosystem" className="text-sm font-medium text-foreground">
                    Publish to Ecosystem Map
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    When enabled, this plant is added to the Ecosystem Map (or enriches a matching verified project) using non-sensitive fields only: name, location, capacity, pathway and status.
                  </p>
                </div>
                <Switch
                  id="publish-ecosystem"
                  checked={form.publishToEcosystem}
                  onCheckedChange={(v) => set("publishToEcosystem", v)}
                />
              </div>
            </Section>

            <Section title="Project Maturity" step={3}>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="Project Maturity Stage" required error={errors.maturityStage}>
                <select className={inputClass} value={form.maturityStage}
                  onChange={(e) => set("maturityStage", e.target.value)}>
                  <option value="">– Select –</option>
                  {MATURITY_STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </Field>
              <Field
                label={
                  <span className="inline-flex items-center gap-1">
                    Stage Reference Date
                    <span
                      title="The calendar date on which the project reached its current Project Maturity Stage. Use the format YYYY-MM-DD."
                      className="inline-flex items-center text-muted-foreground hover:text-foreground cursor-help"
                    >
                      <Info className="h-3 w-3" />
                    </span>
                  </span>
                }
              >
                <input
                  type="date"
                  className={inputClass}
                  value={form.stageReferenceYear}
                  onChange={(e) => set("stageReferenceYear", e.target.value)}
                />
              </Field>
              <Field label="Certification Phase">
                <select className={inputClass} value={form.certificationPhase}
                  onChange={(e) => set("certificationPhase", e.target.value)}>
                  <option value="">– Select –</option>
                  {CERTIFICATION_PHASES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </Field>
              <Field
                label={
                  <span className="inline-flex items-center gap-1">
                    Commercial Operation Date (COD)
                    <span
                      title="The Commercial Operation Date is the day on which the plant begins, or is expected to begin, full commercial production. Enter the actual date if the plant is already operational, or the planned date if it is not yet operational. Use the format YYYY-MM-DD."
                      className="inline-flex items-center text-muted-foreground hover:text-foreground cursor-help"
                    >
                      <Info className="h-3 w-3" />
                    </span>
                  </span>
                }
              >
                <input
                  type="date"
                  className={inputClass}
                  value={form.expectedCod}
                  onChange={(e) => set("expectedCod", e.target.value)}
                />
              </Field>
              </div>
            </Section>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4 pt-2">
            <Section title="Plant Configuration" icon={Settings2} step={1}>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Field label="Primary Pathway">
                  <select className={inputClass} value={form.primaryPathway}
                    onChange={(e) => set("primaryPathway", e.target.value)}>
                    <option value="">– Select –</option>
                    {PRIMARY_PATHWAYS.map((p) => <option key={p} value={p}>{p}</option>)}
                  </select>
                </Field>
                <Field label="Plant Configuration">
                  <select className={inputClass} value={form.plantConfiguration}
                    onChange={(e) => set("plantConfiguration", e.target.value)}>
                    <option value="">– Select –</option>
                    {PLANT_CONFIGS.map((p) => <option key={p} value={p}>{p}</option>)}
                  </select>
                </Field>
                <div className="sm:col-span-2">
                  <Field label="Site Environment">
                    <select className={inputClass} value={form.siteEnvironment}
                      onChange={(e) => set("siteEnvironment", e.target.value)}>
                      <option value="">– Select –</option>
                      {SITE_ENVIRONMENTS.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </Field>
                </div>
              </div>
            </Section>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-4 pt-2">
            <Section title="Products" icon={Package} step={1}>
              <p className="text-[11px] text-muted-foreground">
                Define the output fuels for this plant. At least one fuel type is required.
              </p>

            {form.products.map((p, idx) => (
              <div key={p.id} className="rounded-lg border border-border bg-card p-3 space-y-3">
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
                  <Field label="Fuel Type" required>
                    <select className={inputClass} value={p.fuelType}
                      onChange={(e) => updateProduct(p.id, { fuelType: e.target.value })}>
                      <option value="">– Select –</option>
                      {FUEL_TYPES.map((f) => <option key={f} value={f}>{f}</option>)}
                    </select>
                  </Field>
                  <Field label="Production Capacity">
                    <input type="number" min={0} step="any" className={inputClass}
                      value={p.capacity}
                      onChange={(e) => updateProduct(p.id, { capacity: e.target.value })} />
                  </Field>
                  <Field label="Capacity Unit">
                    <select className={inputClass} value={p.capacityUnit}
                      onChange={(e) => updateProduct(p.id, { capacityUnit: e.target.value })}>
                      {CAPACITY_UNITS.map((u) => <option key={u} value={u}>{u}</option>)}
                    </select>
                  </Field>
                </div>
                {(() => {
                  if (!p.capacity || !Number(p.capacity)) return null;
                  const flow = normalizeFlow(p.capacity, p.capacityUnit, 8000);
                  const formatted = flow.value >= 100
                    ? flow.value.toFixed(1)
                    : flow.value >= 1
                      ? flow.value.toFixed(3)
                      : flow.value.toPrecision(3);
                  const converted = p.capacityUnit !== flow.unit;
                  return (
                    <div className="rounded-md border border-border bg-muted/40 px-2.5 py-1.5 text-[11px] flex items-center justify-between gap-2">
                      <span className="text-muted-foreground">Canvas edge value</span>
                      <span className="font-mono font-semibold text-foreground tabular-nums">
                        {formatted} <span className="text-muted-foreground font-normal">{flow.unit}</span>
                      </span>
                      {converted && (
                        <span className="text-[10px] text-muted-foreground italic">
                          (converted from {p.capacityUnit}, assumes 8000 h/year)
                        </span>
                      )}
                    </div>
                  );
                })()}
              </div>
            ))}

            {errors.products && (
              <p className="text-[11px] text-destructive">{errors.products}</p>
            )}

            <button onClick={addProduct}
              className="inline-flex items-center gap-1.5 rounded-md border border-dashed border-border px-3 py-2 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition-colors">
              <Plus className="h-3 w-3" /> Add another product
            </button>
            </Section>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center justify-between gap-2 pt-3 border-t border-border">
          <button onClick={() => onOpenChange(false)}
            className="rounded-lg border border-border px-4 py-2 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition-colors">
            Cancel
          </button>
          <div className="flex items-center gap-2">
            {step > 1 && (
              <button onClick={() => setStep((step - 1) as 1 | 2 | 3)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-border px-4 py-2 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition-colors">
                <ArrowLeft className="h-3 w-3" /> Back
              </button>
            )}
            {step < 3 ? (
              <button onClick={handleNext}
                className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors">
                Next <ArrowRight className="h-3 w-3" />
              </button>
            ) : (
              <button onClick={handleCreate}
                className="rounded-lg bg-primary px-4 py-2 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors">
                Create & Open Canvas
              </button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default NewPlantDialog;
