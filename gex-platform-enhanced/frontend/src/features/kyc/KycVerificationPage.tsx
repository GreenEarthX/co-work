/**
 * KycVerification — Identity verification flow.
 *
 * Multi-step KYC wizard collecting company details, contact info,
 * role verification, and document uploads. Completing KYC unlocks
 * ownership matching and protected project features.
 *
 * @route /project/:projectId/kyc
 * @auth  Requires authenticated user
 */
import brandIcon from "@/assets/greenearthx-icon.png";
import { useState, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ChevronLeft,
  Building2,
  User,
  Users,
  Mail,
  Globe,
  Shield,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  BarChart3,
  Hammer,
  Factory,
  Ship,
  ShoppingCart,
  Anchor,
  Zap,
  Fuel,
  Truck,
  Plane,
  Landmark,
  FileText,
  MapPin,
  Wind,
  Upload,
  X,
  Paperclip,
} from "lucide-react";
import { useKycState } from "./kycState";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type KycRole = "production" | "infrastructure" | "offtaker";
type InfraSubType = "port" | "pipeline" | "storage" | "grid" | "hub" | "ccus";
type KycStep =
  | "select-role"
  | "company-email"
  | "personal-details"
  | "sector-details"
  | "documents"
  | "add-colleague"
  | "email-check"
  | "confirmation";

/* ------------------------------------------------------------------ */
/*  Role-specific config                                               */
/* ------------------------------------------------------------------ */

const roleConfig: Record<KycRole, { label: string; icon: React.ElementType; color: string; description: string; examples: string }> = {
  production: {
    label: "Production / Plant Operator",
    icon: Factory,
    color: "text-emerald-500",
    description: "You develop, own, or operate hydrogen, e-fuel, ammonia, or SAF production facilities.",
    examples: "Electrolyser operators, e-methanol producers, green ammonia plants, SAF refineries",
  },
  infrastructure: {
    label: "Infrastructure Provider",
    icon: Ship,
    color: "text-sky-500",
    description: "You own, operate, or manage transport, storage, or distribution infrastructure for clean fuels.",
    examples: "Port authorities, pipeline operators, storage terminal owners, grid operators, hydrogen hubs",
  },
  offtaker: {
    label: "Off-taker / Buyer",
    icon: ShoppingCart,
    color: "text-amber-500",
    description: "You procure or consume clean fuels for transport, industrial processes, or power generation.",
    examples: "Shipping lines, airlines, steel mills, chemical companies, fleet operators, utilities",
  },
};

const infraSubTypes: { id: InfraSubType; label: string; icon: React.ElementType; desc: string }[] = [
  { id: "port", label: "Port / Terminal", icon: Anchor, desc: "Port authority, bunkering terminal, import/export terminal" },
  { id: "pipeline", label: "Pipeline Operator", icon: Truck, desc: "Gas grid, hydrogen backbone, dedicated pipeline" },
  { id: "storage", label: "Storage Facility", icon: Fuel, desc: "Tank storage, salt cavern, underground storage" },
  { id: "grid", label: "Grid / Electricity", icon: Zap, desc: "Transmission, distribution, renewable PPA provider" },
  { id: "hub", label: "Industrial Hub", icon: Landmark, desc: "Cluster operator, industrial park, joint venture hub" },
  { id: "ccus", label: "CCUS / Carbon Capture", icon: Wind, desc: "CO₂ capture, transport, utilisation, or geological storage" },
];

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

const KycVerification = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const kyc = useKycState();
  const [step, setStep] = useState<KycStep>("select-role");
  const [role, setRole] = useState<KycRole | null>(null);

  // Common form state
  const [companyEmail, setCompanyEmail] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [companyWebsite, setCompanyWebsite] = useState("");
  const [colleagueName, setColleagueName] = useState("");
  const [colleagueEmail, setColleagueEmail] = useState("");
  const [colleagueRole, setColleagueRole] = useState("");

  // Production-specific (aligned with Plant Builder Form 1 + Form 2)
  const [projectName, setProjectName] = useState("");
  const [plantName, setPlantName] = useState("");
  const [projectLifetime, setProjectLifetime] = useState("");
  const [roleInProject, setRoleInProject] = useState("");
  const [primaryPathway, setPrimaryPathway] = useState("");
  const [plantConfiguration, setPlantConfiguration] = useState("");
  const [country, setCountry] = useState("");
  const [region, setRegion] = useState("");
  const [city, setCity] = useState("");
  const [siteEnvironment, setSiteEnvironment] = useState("");
  const [maturityStage, setMaturityStage] = useState("");
  const [expectedCod, setExpectedCod] = useState("");
  const [fuelTypesProduced, setFuelTypesProduced] = useState<string[]>([]);
  const [productionCapacity, setProductionCapacity] = useState("");

  // Infrastructure-specific
  const [infraType, setInfraType] = useState<InfraSubType | null>(null);
  const [facilityName, setFacilityName] = useState("");
  const [regulatoryLicense, setRegulatoryLicense] = useState("");
  const [throughputCapacity, setThroughputCapacity] = useState("");
  const [connectedTo, setConnectedTo] = useState("");

  // CCUS-specific
  const [ccusType, setCcusType] = useState("");
  const [captureSource, setCaptureSource] = useState("");
  const [storageMethod, setStorageMethod] = useState("");
  const [annualCo2Capacity, setAnnualCo2Capacity] = useState("");

  // Off-taker-specific
  const [procurementSector, setProcurementSector] = useState("");
  const [annualVolume, setAnnualVolume] = useState("");
  const [fuelTypes, setFuelTypes] = useState("");
  const [deliveryLocation, setDeliveryLocation] = useState("");
  const [contractStatus, setContractStatus] = useState("");

  // Document uploads
  const [documents, setDocuments] = useState<Record<string, File | null>>({});

  const addDocument = (key: string, file: File | null) => {
    setDocuments((prev) => ({ ...prev, [key]: file }));
  };

  const removeDocument = (key: string) => {
    setDocuments((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const requiredDocs = useMemo(() => {
    const common = [
      { key: "company-reg", label: "Company Registration Certificate", desc: "Official certificate of incorporation or trade register extract", required: true },
      { key: "id-doc", label: "Government-Issued ID", desc: "Passport, national ID card, or driver's license of the primary contact", required: true },
    ];
    if (role === "production") return [
      ...common,
      { key: "env-permit", label: "Environmental Permit", desc: "Operating permit or environmental impact assessment approval", required: false },
      { key: "ppa-contract", label: "PPA / Electricity Contract", desc: "Power Purchase Agreement or renewable electricity supply contract", required: false },
      { key: "certification", label: "Certification / Guarantee of Origin", desc: "CertifHy, ISCC, or relevant scheme documentation", required: false },
    ];
    if (role === "infrastructure") {
      const base = [
        ...common,
        { key: "operator-license", label: "Operator License", desc: "Infrastructure operating license issued by the relevant authority", required: true },
      ];
      if (infraType === "port") base.push({ key: "port-authority", label: "Port Authority Letter", desc: "Official letter from the port authority confirming your operating rights", required: false });
      if (infraType === "ccus") base.push(
        { key: "storage-permit", label: "CO₂ Storage Permit", desc: "Permit under the EU CCS Directive or equivalent national legislation", required: true },
        { key: "ets-registration", label: "EU ETS Installation Registration", desc: "EU Emissions Trading System installation ID documentation", required: false },
      );
      if (infraType === "pipeline") base.push({ key: "pipeline-license", label: "Pipeline Transport License", desc: "License for gas or hydrogen pipeline operation", required: false });
      return base;
    }
    if (role === "offtaker") return [
      ...common,
      { key: "procurement-loi", label: "Letter of Intent / MoU", desc: "Signed letter of intent or memorandum of understanding for fuel procurement", required: false },
      { key: "fleet-reg", label: "Fleet / Asset Registration", desc: "IMO registration, IATA code, or fleet operator license", required: false },
    ];
    return common;
  }, [role, infraType]);

  // Derived
  const emailDomain = companyEmail.includes("@") ? companyEmail.split("@")[1] : "";

  const canProceedEmail = companyEmail.includes("@") && companyEmail.includes(".");
  const canProceedDetails = firstName.trim() && lastName.trim() && jobTitle.trim() && companyName.trim();
  const canProceedColleague = colleagueName.trim() && colleagueEmail.includes("@") && colleagueEmail.includes(".");

  const canProceedSector = useMemo(() => {
    if (role === "production") return projectName.trim() && country.trim() && maturityStage && fuelTypesProduced.length > 0;
    if (role === "infrastructure") return infraType && facilityName;
    if (role === "offtaker") return procurementSector && fuelTypes;
    return false;
  }, [role, projectName, country, maturityStage, fuelTypesProduced, infraType, facilityName, procurementSector, fuelTypes]);

  const allSteps: KycStep[] = ["select-role", "company-email", "personal-details", "sector-details", "documents", "add-colleague", "email-check", "confirmation"];
  const stepLabels = ["Your Role", "Company Email", "Your Details", role ? roleConfig[role].label.split(" /")[0] + " Info" : "Sector Info", "Documents", "Add Colleague", "Verification", "Done"];
  const currentIdx = allSteps.indexOf(step);

  const inputCls = "mt-1 h-10 w-full rounded-lg border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring";
  const inputWithIconCls = "h-10 w-full rounded-lg border border-border bg-background pl-10 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring";
  const labelCls = "text-xs font-semibold text-card-foreground";
  const btnPrimary = "inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50";
  const btnSecondary = "inline-flex items-center gap-2 rounded-lg border border-border px-4 py-2.5 text-sm font-medium text-muted-foreground hover:bg-accent hover:text-foreground";

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-white/10 px-6 py-3" style={{ background: "linear-gradient(135deg, hsl(200 25% 10%), hsl(174 45% 18%))" }}>
        <div className="mx-auto max-w-2xl flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img src={brandIcon} alt="GreenEarthX" className="h-8 w-auto" />
            <div className="h-5 w-px bg-white/20" />
            <div>
              <h1 className="font-display text-sm font-bold text-white tracking-tight">KYC Verification</h1>
              <p className="text-[10px] text-white/50">
                {role ? roleConfig[role].label : "Identity Verification"}
              </p>
            </div>
          </div>
          <button
            onClick={() => projectId ? navigate(`/project/${projectId}`) : navigate("/")}
            className="text-xs text-primary-foreground/60 hover:text-primary-foreground"
          >
            Cancel
          </button>
        </div>
      </header>

      {/* Progress */}
      <div className="mx-auto max-w-2xl px-6 pt-6">
        <div className="flex items-center gap-1">
          {allSteps.map((s, i) => {
            const isDone = i < currentIdx;
            const isCurrent = i === currentIdx;
            return (
              <div key={s} className="flex-1 flex flex-col items-center gap-1">
                <div className={`h-1.5 w-full rounded-full transition-colors ${isDone ? "bg-emerald-500" : isCurrent ? "bg-primary" : "bg-muted"}`} />
                <span className={`text-[9px] leading-tight text-center ${isCurrent ? "text-foreground font-semibold" : "text-muted-foreground"}`}>
                  {stepLabels[i]}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <div className="mx-auto max-w-2xl px-6 py-8">
        {/* ============================================================ */}
        {/* STEP 0: Select Role                                          */}
        {/* ============================================================ */}
        {step === "select-role" && (
          <div className="bg-card border border-border rounded-xl p-6 space-y-5">
            <div className="space-y-1">
              <h2 className="text-lg font-bold text-card-foreground">What best describes your organization?</h2>
              <p className="text-sm text-muted-foreground">
                Select your role so we can tailor the verification process to your sector. This determines which documentation and details we'll need.
              </p>
            </div>

            <div className="space-y-3">
              {(Object.keys(roleConfig) as KycRole[]).map((r) => {
                const cfg = roleConfig[r];
                const Icon = cfg.icon;
                const selected = role === r;
                return (
                  <button
                    key={r}
                    onClick={() => setRole(r)}
                    className={`w-full text-left rounded-xl border-2 p-4 transition-all ${
                      selected
                        ? "border-primary bg-primary/5"
                        : "border-border hover:border-primary/30 hover:bg-accent/30"
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div className={`h-10 w-10 rounded-lg flex items-center justify-center flex-shrink-0 ${selected ? "bg-primary/10" : "bg-muted"}`}>
                        <Icon className={`h-5 w-5 ${selected ? cfg.color : "text-muted-foreground"}`} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <h3 className={`text-sm font-semibold ${selected ? "text-card-foreground" : "text-card-foreground/80"}`}>{cfg.label}</h3>
                          {selected && <CheckCircle2 className="h-4 w-4 text-primary flex-shrink-0" />}
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5">{cfg.description}</p>
                        <p className="text-[10px] text-muted-foreground/60 mt-1 italic">e.g. {cfg.examples}</p>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>

            <div className="flex justify-end">
              <button
                onClick={() => setStep("company-email")}
                disabled={!role}
                className={btnPrimary}
              >
                Continue <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}

        {/* ============================================================ */}
        {/* STEP 1: Company Email                                        */}
        {/* ============================================================ */}
        {step === "company-email" && (
          <div className="bg-card border border-border rounded-xl p-6 space-y-5">
            <div className="space-y-1">
              <h2 className="text-lg font-bold text-card-foreground">Enter your company email</h2>
              <p className="text-sm text-muted-foreground">
                We'll use your company email to verify your affiliation. Please use your official company email address.
              </p>
            </div>

            <div className="space-y-3">
              <div>
                <label className={labelCls}>Company Email Address *</label>
                <div className="relative mt-1">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <input
                    type="email"
                    placeholder="you@yourcompany.com"
                    value={companyEmail}
                    onChange={(e) => setCompanyEmail(e.target.value)}
                    className={inputWithIconCls}
                  />
                </div>
                {companyEmail && !companyEmail.includes("@") && (
                  <p className="text-[10px] text-destructive mt-1">Please enter a valid email address</p>
                )}
              </div>

              <div className="rounded-lg bg-[#0ea5a0]/5 border border-[#0ea5a0]/10 px-4 py-3">
                <p className="text-xs text-[#0ea5a0] flex items-start gap-2">
                  <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
                  Your email domain will be matched against known {role === "infrastructure" ? "operators and authorities" : role === "offtaker" ? "procurement organizations" : "project developers"} to verify your identity.
                </p>
              </div>
            </div>

            <div className="flex justify-between">
              <button onClick={() => setStep("select-role")} className={btnSecondary}>
                <ChevronLeft className="h-4 w-4" /> Back
              </button>
              <button onClick={() => setStep("personal-details")} disabled={!canProceedEmail} className={btnPrimary}>
                Continue <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}

        {/* ============================================================ */}
        {/* STEP 2: Personal Details                                     */}
        {/* ============================================================ */}
        {step === "personal-details" && (
          <div className="bg-card border border-border rounded-xl p-6 space-y-5">
            <div className="space-y-1">
              <h2 className="text-lg font-bold text-card-foreground">Tell us about yourself</h2>
              <p className="text-sm text-muted-foreground">
                Provide your details so we can verify your identity and role within your organization.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className={labelCls}>First Name *</label>
                <input type="text" value={firstName} onChange={(e) => setFirstName(e.target.value)} placeholder="Jan" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Last Name *</label>
                <input type="text" value={lastName} onChange={(e) => setLastName(e.target.value)} placeholder="van der Berg" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Job Title *</label>
                <input
                  type="text"
                  value={jobTitle}
                  onChange={(e) => setJobTitle(e.target.value)}
                  placeholder={role === "production" ? "Plant Director" : role === "infrastructure" ? "Operations Manager" : "Head of Procurement"}
                  className={inputCls}
                />
              </div>
              <div>
                <label className={labelCls}>Phone Number</label>
                <input type="tel" value={phoneNumber} onChange={(e) => setPhoneNumber(e.target.value)} placeholder="+31 10 555 0102" className={inputCls} />
              </div>
              <div className="sm:col-span-2">
                <label className={labelCls}>Company / Organization Name *</label>
                <div className="relative mt-1">
                  <Building2 className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <input
                    type="text"
                    value={companyName}
                    onChange={(e) => setCompanyName(e.target.value)}
                    placeholder={role === "production" ? "NorthSea Hydrogen BV" : role === "infrastructure" ? "Port of Rotterdam Authority" : "Maersk Line"}
                    className={inputWithIconCls}
                  />
                </div>
              </div>
              <div className="sm:col-span-2">
                <label className={labelCls}>Company Website</label>
                <div className="relative mt-1">
                  <Globe className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <input type="url" value={companyWebsite} onChange={(e) => setCompanyWebsite(e.target.value)} placeholder="https://yourcompany.com" className={inputWithIconCls} />
                </div>
              </div>
            </div>

            <div className="flex justify-between">
              <button onClick={() => setStep("company-email")} className={btnSecondary}><ChevronLeft className="h-4 w-4" /> Back</button>
              <button onClick={() => setStep("sector-details")} disabled={!canProceedDetails} className={btnPrimary}>Continue <ArrowRight className="h-4 w-4" /></button>
            </div>
          </div>
        )}

        {/* ============================================================ */}
        {/* STEP 3: Sector-Specific Details                              */}
        {/* ============================================================ */}
        {step === "sector-details" && role === "production" && (
          <div className="bg-card border border-border rounded-xl p-6 space-y-5">
            <div className="flex items-center gap-3 mb-1">
              <div className="h-8 w-8 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                <Factory className="h-4 w-4 text-emerald-500" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-card-foreground">Project Setup</h2>
                <p className="text-xs text-muted-foreground">Enter your project details, aligned with the Green Fuel Plant Builder.</p>
              </div>
            </div>

            {/* A. Project Identity */}
            <div className="space-y-1">
              <h3 className="text-xs font-bold text-card-foreground uppercase tracking-wider">A. Project Identity</h3>
              <div className="h-px bg-border" />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className={labelCls}>Project Name *</label>
                <input type="text" value={projectName} onChange={(e) => setProjectName(e.target.value)} placeholder="GreenFuel 2030" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Plant Name</label>
                <input type="text" value={plantName} onChange={(e) => setPlantName(e.target.value)} placeholder="Maasvlakte H₂ Plant" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Project Lifetime (years)</label>
                <input type="number" value={projectLifetime} onChange={(e) => setProjectLifetime(e.target.value)} placeholder="25" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Role in Project</label>
                <select value={roleInProject} onChange={(e) => setRoleInProject(e.target.value)} className={inputCls}>
                  <option value="">Select role…</option>
                  <option value="developer">Project Developer</option>
                  <option value="owner">Plant Owner</option>
                  <option value="epc">EPC Contractor</option>
                  <option value="investor">Investor</option>
                  <option value="offtaker">Offtaker</option>
                  <option value="advisor">Advisor</option>
                  <option value="other">Other</option>
                </select>
              </div>
            </div>

            {/* B. Pathway & Configuration */}
            <div className="space-y-1 pt-2">
              <h3 className="text-xs font-bold text-card-foreground uppercase tracking-wider">B. Pathway & Configuration</h3>
              <div className="h-px bg-border" />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className={labelCls}>Primary Pathway</label>
                <select value={primaryPathway} onChange={(e) => setPrimaryPathway(e.target.value)} className={inputCls}>
                  <option value="">Select pathway…</option>
                  <option value="synthetic">Synthetic Pathway</option>
                  <option value="biogenic">Biogenic Pathway</option>
                  <option value="thermochemical">Thermochemical Pathway</option>
                  <option value="hybrid">Hybrid Pathway</option>
                  <option value="physical-recovery">Physical Recovery Pathway</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div>
                <label className={labelCls}>Plant Configuration</label>
                <select value={plantConfiguration} onChange={(e) => setPlantConfiguration(e.target.value)} className={inputCls}>
                  <option value="">Select configuration…</option>
                  <option value="new-build">New Build</option>
                  <option value="retrofit">Retrofit</option>
                  <option value="expansion">Expansion</option>
                  <option value="mixed">Mixed</option>
                </select>
              </div>
            </div>

            {/* C. Location */}
            <div className="space-y-1 pt-2">
              <h3 className="text-xs font-bold text-card-foreground uppercase tracking-wider">C. Location</h3>
              <div className="h-px bg-border" />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className={labelCls}>Country *</label>
                <input type="text" value={country} onChange={(e) => setCountry(e.target.value)} placeholder="Netherlands" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Region / State</label>
                <input type="text" value={region} onChange={(e) => setRegion(e.target.value)} placeholder="South Holland" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>City</label>
                <input type="text" value={city} onChange={(e) => setCity(e.target.value)} placeholder="Rotterdam" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Site Environment</label>
                <select value={siteEnvironment} onChange={(e) => setSiteEnvironment(e.target.value)} className={inputCls}>
                  <option value="">Select environment…</option>
                  <option value="coastal">Coastal</option>
                  <option value="inland">Inland</option>
                  <option value="industrial-cluster">Industrial Cluster</option>
                  <option value="port-terminal">Port Terminal</option>
                  <option value="urban">Urban</option>
                  <option value="rural">Rural</option>
                  <option value="other">Other</option>
                </select>
              </div>
            </div>

            {/* D. Project Maturity */}
            <div className="space-y-1 pt-2">
              <h3 className="text-xs font-bold text-card-foreground uppercase tracking-wider">D. Project Maturity</h3>
              <div className="h-px bg-border" />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className={labelCls}>Project Maturity Stage *</label>
                <select value={maturityStage} onChange={(e) => setMaturityStage(e.target.value)} className={inputCls}>
                  <option value="">Select stage…</option>
                  <option value="concept">Concept</option>
                  <option value="pre-feasibility">Pre-Feasibility</option>
                  <option value="feasibility">Feasibility</option>
                  <option value="pre-feed">Pre-FEED</option>
                  <option value="feed">FEED</option>
                  <option value="permitting">Permitting</option>
                  <option value="pre-fid">Pre-FID</option>
                  <option value="fid">FID</option>
                  <option value="construction">Construction</option>
                  <option value="commissioning">Commissioning</option>
                  <option value="operating">Operating</option>
                </select>
              </div>
              <div>
                <label className={labelCls}>Expected COD</label>
                <input type="text" value={expectedCod} onChange={(e) => setExpectedCod(e.target.value)} placeholder="2028" className={inputCls} />
              </div>
              <div className="sm:col-span-2">
                <label className={labelCls}>Production Capacity</label>
                <input type="text" value={productionCapacity} onChange={(e) => setProductionCapacity(e.target.value)} placeholder="e.g. 100 MW / 50 ktpa" className={inputCls} />
              </div>
            </div>

            {/* E. Products (Form 2) */}
            <div className="space-y-1 pt-2">
              <h3 className="text-xs font-bold text-card-foreground uppercase tracking-wider">E. Output Products *</h3>
              <div className="h-px bg-border" />
            </div>
            <div>
              <p className="text-[10px] text-muted-foreground mb-2">Select at least one fuel type your project will produce.</p>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {[
                  { id: "hydrogen", label: "Hydrogen" },
                  { id: "ammonia", label: "Ammonia" },
                  { id: "methanol", label: "Methanol" },
                  { id: "methane", label: "Methane" },
                  { id: "diesel", label: "Diesel" },
                  { id: "kerosene", label: "Kerosene (SAF)" },
                  { id: "naphtha", label: "Naphtha" },
                  { id: "ethanol", label: "Ethanol" },
                  { id: "gasoline", label: "Gasoline" },
                ].map((fuel) => {
                  const selected = fuelTypesProduced.includes(fuel.id);
                  return (
                    <button
                      key={fuel.id}
                      type="button"
                      onClick={() => setFuelTypesProduced((prev) => selected ? prev.filter((f) => f !== fuel.id) : [...prev, fuel.id])}
                      className={`rounded-lg border-2 px-3 py-2 text-xs font-medium transition-all ${
                        selected ? "border-primary bg-primary/10 text-foreground" : "border-border text-muted-foreground hover:border-primary/30"
                      }`}
                    >
                      {fuel.label}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="flex justify-between">
              <button onClick={() => setStep("personal-details")} className={btnSecondary}><ChevronLeft className="h-4 w-4" /> Back</button>
              <button onClick={() => setStep("documents")} disabled={!canProceedSector} className={btnPrimary}>Continue <ArrowRight className="h-4 w-4" /></button>
            </div>
          </div>
        )}

        {step === "sector-details" && role === "infrastructure" && (
          <div className="bg-card border border-border rounded-xl p-6 space-y-5">
            <div className="flex items-center gap-3 mb-1">
              <div className="h-8 w-8 rounded-lg bg-sky-500/10 flex items-center justify-center">
                <Ship className="h-4 w-4 text-sky-500" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-card-foreground">Infrastructure Details</h2>
                <p className="text-xs text-muted-foreground">Specify the type and details of the infrastructure you operate or manage.</p>
              </div>
            </div>

            {/* Sub-type selection */}
            <div>
              <label className={labelCls}>Infrastructure Type *</label>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mt-2">
                {infraSubTypes.map((t) => {
                  const Icon = t.icon;
                  const selected = infraType === t.id;
                  return (
                    <button
                      key={t.id}
                      onClick={() => setInfraType(t.id)}
                      className={`rounded-lg border-2 p-3 text-left transition-all ${
                        selected ? "border-primary bg-primary/5" : "border-border hover:border-primary/30"
                      }`}
                    >
                      <Icon className={`h-4 w-4 mb-1 ${selected ? "text-sky-500" : "text-muted-foreground"}`} />
                      <p className="text-xs font-semibold text-card-foreground">{t.label}</p>
                      <p className="text-[9px] text-muted-foreground leading-tight mt-0.5">{t.desc}</p>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <label className={labelCls}>Facility / Asset Name *</label>
                <input type="text" value={facilityName} onChange={(e) => setFacilityName(e.target.value)} placeholder={infraType === "port" ? "Europoort Terminal 7" : infraType === "ccus" ? "Porthos CCS Project" : "Asset name"} className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Regulatory License / Code</label>
                <div className="relative mt-1">
                  <FileText className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <input type="text" value={regulatoryLicense} onChange={(e) => setRegulatoryLicense(e.target.value)} placeholder={infraType === "port" ? "IMO Facility No." : infraType === "ccus" ? "EU ETS Installation ID / Storage Permit" : "License number"} className={inputWithIconCls} />
                </div>
              </div>
              <div>
                <label className={labelCls}>Throughput / Capacity</label>
                <input type="text" value={throughputCapacity} onChange={(e) => setThroughputCapacity(e.target.value)} placeholder={infraType === "port" ? "e.g. 2M tonnes/yr" : infraType === "ccus" ? "e.g. 2.5 Mtpa CO₂" : "e.g. 500 GWh/yr"} className={inputCls} />
              </div>
              <div className="sm:col-span-2">
                <label className={labelCls}>Connected Infrastructure</label>
                <input type="text" value={connectedTo} onChange={(e) => setConnectedTo(e.target.value)} placeholder="e.g. Delta Corridor pipeline, Maasvlakte industrial cluster" className={inputCls} />
              </div>
            </div>

            {infraType === "port" && (
              <div className="rounded-lg bg-sky-500/5 border border-sky-500/10 px-4 py-3">
                <p className="text-xs text-sky-700 dark:text-sky-400 flex items-start gap-2">
                  <Anchor className="h-4 w-4 flex-shrink-0 mt-0.5" />
                  Port authorities: we'll cross-reference your email domain against IAPH, ESPO, and national port registry databases.
                </p>
              </div>
            )}

            {infraType === "ccus" && (
              <>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className={labelCls}>CCUS Value Chain Position *</label>
                    <select value={ccusType} onChange={(e) => setCcusType(e.target.value)} className={inputCls}>
                      <option value="">Select position…</option>
                      <option value="capture">CO₂ Capture (point source)</option>
                      <option value="dac">Direct Air Capture (DAC)</option>
                      <option value="transport-pipe">CO₂ Transport, Pipeline</option>
                      <option value="transport-ship">CO₂ Transport, Shipping</option>
                      <option value="storage-offshore">Geological Storage, Offshore</option>
                      <option value="storage-onshore">Geological Storage, Onshore</option>
                      <option value="utilisation">CO₂ Utilisation (CCU)</option>
                      <option value="integrated">Integrated CCS Chain</option>
                    </select>
                  </div>
                  <div>
                    <label className={labelCls}>Annual CO₂ Capacity</label>
                    <input type="text" value={annualCo2Capacity} onChange={(e) => setAnnualCo2Capacity(e.target.value)} placeholder="e.g. 2.5 Mtpa CO₂" className={inputCls} />
                  </div>
                  <div>
                    <label className={labelCls}>CO₂ Source / Emitter Type</label>
                    <input type="text" value={captureSource} onChange={(e) => setCaptureSource(e.target.value)} placeholder="e.g. Refinery flue gas, cement kiln, bioethanol" className={inputCls} />
                  </div>
                  <div>
                    <label className={labelCls}>Storage / Utilisation Method</label>
                    <select value={storageMethod} onChange={(e) => setStorageMethod(e.target.value)} className={inputCls}>
                      <option value="">Select method…</option>
                      <option value="depleted-gas">Depleted Gas Field</option>
                      <option value="saline-aquifer">Saline Aquifer</option>
                      <option value="basalt">Basalt Mineralisation</option>
                      <option value="eor">Enhanced Oil Recovery (EOR)</option>
                      <option value="e-fuel">e-Fuel Synthesis (CCU)</option>
                      <option value="building-materials">Building Materials (CCU)</option>
                      <option value="other">Other</option>
                    </select>
                  </div>
                </div>
                <div className="rounded-lg bg-sky-500/5 border border-sky-500/10 px-4 py-3">
                  <p className="text-xs text-sky-700 dark:text-sky-400 flex items-start gap-2">
                    <Wind className="h-4 w-4 flex-shrink-0 mt-0.5" />
                    CCUS operators: we'll verify your EU ETS installation ID, storage permit (EU CCS Directive), and cross-reference against the Global CCS Institute project database.
                  </p>
                </div>
              </>
            )}

            <div className="flex justify-between">
              <button onClick={() => setStep("personal-details")} className={btnSecondary}><ChevronLeft className="h-4 w-4" /> Back</button>
              <button onClick={() => setStep("documents")} disabled={!canProceedSector} className={btnPrimary}>Continue <ArrowRight className="h-4 w-4" /></button>
            </div>
          </div>
        )}

        {step === "sector-details" && role === "offtaker" && (
          <div className="bg-card border border-border rounded-xl p-6 space-y-5">
            <div className="flex items-center gap-3 mb-1">
              <div className="h-8 w-8 rounded-lg bg-amber-500/10 flex items-center justify-center">
                <ShoppingCart className="h-4 w-4 text-amber-500" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-card-foreground">Off-taker / Procurement Details</h2>
                <p className="text-xs text-muted-foreground">Tell us about your fuel procurement needs and sector.</p>
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className={labelCls}>Sector *</label>
                <select value={procurementSector} onChange={(e) => setProcurementSector(e.target.value)} className={inputCls}>
                  <option value="">Select sector…</option>
                  <option value="maritime">Maritime Shipping</option>
                  <option value="aviation">Aviation</option>
                  <option value="road-transport">Road Transport / Fleet</option>
                  <option value="rail">Rail</option>
                  <option value="steel">Steel & Metals</option>
                  <option value="chemicals">Chemicals & Refining</option>
                  <option value="cement">Cement & Construction</option>
                  <option value="power">Power Generation</option>
                  <option value="fertilizer">Fertilizer Production</option>
                  <option value="other">Other Industrial</option>
                </select>
              </div>
              <div>
                <label className={labelCls}>Fuel Types of Interest *</label>
                <select value={fuelTypes} onChange={(e) => setFuelTypes(e.target.value)} className={inputCls}>
                  <option value="">Select fuel…</option>
                  <option value="green-h2">Green Hydrogen</option>
                  <option value="green-ammonia">Green Ammonia</option>
                  <option value="e-methanol">e-Methanol</option>
                  <option value="saf">SAF</option>
                  <option value="bio-lng">Bio-LNG</option>
                  <option value="e-methane">e-Methane</option>
                  <option value="multiple">Multiple fuels</option>
                </select>
              </div>
              <div>
                <label className={labelCls}>Estimated Annual Volume</label>
                <input type="text" value={annualVolume} onChange={(e) => setAnnualVolume(e.target.value)} placeholder="e.g. 20,000 tonnes/yr" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Contract Status</label>
                <select value={contractStatus} onChange={(e) => setContractStatus(e.target.value)} className={inputCls}>
                  <option value="">Select…</option>
                  <option value="exploring">Exploring / Early Interest</option>
                  <option value="rfi">RFI / RFP Issued</option>
                  <option value="mou">MoU / Letter of Intent</option>
                  <option value="contracted">Contracted</option>
                  <option value="active">Active Supply</option>
                </select>
              </div>
              <div className="sm:col-span-2">
                <label className={labelCls}>Preferred Delivery Location</label>
                <div className="relative mt-1">
                  <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <input type="text" value={deliveryLocation} onChange={(e) => setDeliveryLocation(e.target.value)} placeholder="e.g. Port of Rotterdam, AMS Airport" className={inputWithIconCls} />
                </div>
              </div>
            </div>

            {procurementSector === "maritime" && (
              <div className="rounded-lg bg-amber-500/5 border border-amber-500/10 px-4 py-3">
                <p className="text-xs text-amber-700 dark:text-amber-400 flex items-start gap-2">
                  <Ship className="h-4 w-4 flex-shrink-0 mt-0.5" />
                  Maritime off-takers: we'll verify your IMO company number and cross-reference fleet data where applicable.
                </p>
              </div>
            )}
            {procurementSector === "aviation" && (
              <div className="rounded-lg bg-amber-500/5 border border-amber-500/10 px-4 py-3">
                <p className="text-xs text-amber-700 dark:text-amber-400 flex items-start gap-2">
                  <Plane className="h-4 w-4 flex-shrink-0 mt-0.5" />
                  Airlines: we'll verify your IATA/ICAO code and cross-reference against CORSIA participants.
                </p>
              </div>
            )}

            <div className="flex justify-between">
              <button onClick={() => setStep("personal-details")} className={btnSecondary}><ChevronLeft className="h-4 w-4" /> Back</button>
              <button onClick={() => setStep("documents")} disabled={!canProceedSector} className={btnPrimary}>Continue <ArrowRight className="h-4 w-4" /></button>
            </div>
          </div>
        )}

        {/* ============================================================ */}
        {/* STEP: Document Uploads                                       */}
        {/* ============================================================ */}
        {step === "documents" && (
          <div className="bg-card border border-border rounded-xl p-6 space-y-5">
            <div className="flex items-center gap-3 mb-1">
              <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center">
                <Upload className="h-4 w-4 text-primary" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-card-foreground">Supporting Documents</h2>
                <p className="text-xs text-muted-foreground">Upload documents to verify your organization and credentials. Required items are marked with *.</p>
              </div>
            </div>

            <div className="space-y-3">
              {requiredDocs.map((doc) => {
                const file = documents[doc.key];
                return (
                  <div key={doc.key} className="rounded-lg border border-border p-4 space-y-2">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="text-xs font-semibold text-card-foreground">
                          {doc.label} {doc.required && <span className="text-destructive">*</span>}
                        </p>
                        <p className="text-[10px] text-muted-foreground">{doc.desc}</p>
                      </div>
                      {file && (
                        <button onClick={() => removeDocument(doc.key)} className="text-muted-foreground hover:text-destructive transition-colors p-1">
                          <X className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                    {file ? (
                      <div className="flex items-center gap-2 rounded-md bg-muted px-3 py-2">
                        <Paperclip className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
                        <span className="text-xs text-foreground truncate">{file.name}</span>
                        <span className="text-[10px] text-muted-foreground ml-auto flex-shrink-0">{(file.size / 1024).toFixed(0)} KB</span>
                        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 flex-shrink-0" />
                      </div>
                    ) : (
                      <label className="flex items-center justify-center gap-2 rounded-lg border-2 border-dashed border-border hover:border-primary/40 cursor-pointer px-4 py-3 transition-colors">
                        <Upload className="h-4 w-4 text-muted-foreground" />
                        <span className="text-xs text-muted-foreground">Click to upload PDF, JPG, or PNG (max 10 MB)</span>
                        <input
                          type="file"
                          accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"
                          className="hidden"
                          onChange={(e) => {
                            const f = e.target.files?.[0];
                            if (f && f.size <= 10 * 1024 * 1024) addDocument(doc.key, f);
                          }}
                        />
                      </label>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="rounded-lg bg-primary/5 border border-primary/10 px-4 py-3">
              <p className="text-xs text-primary flex items-start gap-2">
                <Shield className="h-4 w-4 flex-shrink-0 mt-0.5" />
                All documents are encrypted and only used for verification purposes. They are not shared with third parties.
              </p>
            </div>

            <div className="flex justify-between">
              <button onClick={() => setStep("sector-details")} className={btnSecondary}><ChevronLeft className="h-4 w-4" /> Back</button>
              <button onClick={() => setStep("add-colleague")} className={btnPrimary}>Continue <ArrowRight className="h-4 w-4" /></button>
            </div>
          </div>
        )}

        {/* ============================================================ */}
        {/* STEP: Add Colleague                                          */}
        {/* ============================================================ */}
        {step === "add-colleague" && (
          <div className="bg-card border border-border rounded-xl p-6 space-y-5">
            <div className="space-y-1">
              <h2 className="text-lg font-bold text-card-foreground">Add a colleague for verification</h2>
              <p className="text-sm text-muted-foreground">
                Verification requires at least <span className="font-semibold text-card-foreground">two people</span> from the same organization. Add a colleague who can confirm your affiliation.
              </p>
            </div>

            <div className="rounded-lg bg-primary/5 border border-primary/10 px-4 py-3">
              <p className="text-xs text-primary flex items-start gap-2">
                <Users className="h-4 w-4 flex-shrink-0 mt-0.5" />
                <span>Both contacts must have email addresses from the same domain (<span className="font-mono font-semibold">@{emailDomain || "yourcompany.com"}</span>).</span>
              </p>
            </div>

            <div className="space-y-4">
              <div>
                <label className={labelCls}>Colleague's Full Name *</label>
                <div className="relative mt-1">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <input type="text" value={colleagueName} onChange={(e) => setColleagueName(e.target.value)} placeholder="Anna Müller" className={inputWithIconCls} />
                </div>
              </div>
              <div>
                <label className={labelCls}>Colleague's Company Email *</label>
                <div className="relative mt-1">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <input type="email" value={colleagueEmail} onChange={(e) => setColleagueEmail(e.target.value)} placeholder={emailDomain ? `colleague@${emailDomain}` : "colleague@yourcompany.com"} className={inputWithIconCls} />
                </div>
                {colleagueEmail.includes("@") && emailDomain && !colleagueEmail.endsWith(`@${emailDomain}`) && (
                  <p className="text-[10px] text-destructive mt-1 flex items-center gap-1">
                    <AlertCircle className="h-3 w-3" /> Email must be from the same domain (@{emailDomain})
                  </p>
                )}
              </div>
              <div>
                <label className={labelCls}>Colleague's Role</label>
                <input type="text" value={colleagueRole} onChange={(e) => setColleagueRole(e.target.value)} placeholder="Technical Lead" className={inputCls} />
              </div>
            </div>

            <div className="flex justify-between">
              <button onClick={() => setStep("documents")} className={btnSecondary}><ChevronLeft className="h-4 w-4" /> Back</button>
              <button onClick={() => setStep("email-check")} disabled={!canProceedColleague} className={btnPrimary}>Verify & Submit <ArrowRight className="h-4 w-4" /></button>
            </div>
          </div>
        )}

        {/* ============================================================ */}
        {/* STEP 5: Verification Checks                                  */}
        {/* ============================================================ */}
        {step === "email-check" && (
          <div className="bg-card border border-border rounded-xl p-6 space-y-5">
            <div className="space-y-1">
              <h2 className="text-lg font-bold text-card-foreground">Verifying your identity</h2>
              <p className="text-sm text-muted-foreground">
                We're cross-referencing your details against {role === "infrastructure" ? "infrastructure registries" : role === "offtaker" ? "industry databases" : "project records"}.
              </p>
            </div>

            <div className="space-y-3">
              <div className="flex items-center gap-3 rounded-lg border border-border p-3">
                <CheckCircle2 className="h-5 w-5 text-emerald-500 flex-shrink-0" />
                <div>
                  <p className="text-xs font-semibold text-card-foreground">Email domain verified</p>
                  <p className="text-[10px] text-muted-foreground">
                    <span className="font-mono">@{emailDomain}</span> matches {role === "infrastructure" ? "registered operator" : "company"} records
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-3 rounded-lg border border-border p-3">
                <CheckCircle2 className="h-5 w-5 text-emerald-500 flex-shrink-0" />
                <div>
                  <p className="text-xs font-semibold text-card-foreground">Organization verified</p>
                  <p className="text-[10px] text-muted-foreground">{companyName}</p>
                </div>
              </div>

              <div className="flex items-center gap-3 rounded-lg border border-border p-3">
                <CheckCircle2 className="h-5 w-5 text-emerald-500 flex-shrink-0" />
                <div>
                  <p className="text-xs font-semibold text-card-foreground">
                    {role === "production" && "Production facility registered"}
                    {role === "infrastructure" && "Infrastructure asset registered"}
                    {role === "offtaker" && "Procurement profile registered"}
                  </p>
                  <p className="text-[10px] text-muted-foreground">
                    {role === "production" && `${projectName || "Project"}, ${country || "Location TBD"} (${maturityStage ? maturityStage.replace(/-/g, " ").replace(/\b\w/g, c => c.toUpperCase()) : "Stage TBD"})`}
                    {role === "infrastructure" && `${facilityName}${infraType ? ` (${infraSubTypes.find(t => t.id === infraType)?.label})` : ""}`}
                    {role === "offtaker" && `${procurementSector ? procurementSector.replace(/-/g, " ").replace(/\b\w/g, c => c.toUpperCase()) : "Sector"}, ${fuelTypes ? fuelTypes.replace(/-/g, " ") : "fuels"}`}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-3 rounded-lg border border-border p-3">
                <CheckCircle2 className="h-5 w-5 text-emerald-500 flex-shrink-0" />
                <div>
                  <p className="text-xs font-semibold text-card-foreground">Dual verification contacts</p>
                  <p className="text-[10px] text-muted-foreground">{firstName} {lastName} & {colleagueName}</p>
                </div>
              </div>

              <div className="flex items-center gap-3 rounded-lg border border-border p-3">
                <CheckCircle2 className="h-5 w-5 text-emerald-500 flex-shrink-0" />
                <div>
                  <p className="text-xs font-semibold text-card-foreground">Documents uploaded</p>
                  <p className="text-[10px] text-muted-foreground">
                    {Object.keys(documents).length} document{Object.keys(documents).length !== 1 ? "s" : ""} attached
                    {requiredDocs.filter(d => d.required && !documents[d.key]).length > 0 && (
                      <span className="text-amber-500 ml-1">({requiredDocs.filter(d => d.required && !documents[d.key]).length} required missing)</span>
                    )}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-3 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
                <AlertCircle className="h-5 w-5 text-amber-500 flex-shrink-0" />
                <div>
                  <p className="text-xs font-semibold text-card-foreground">Colleague confirmation pending</p>
                  <p className="text-[10px] text-muted-foreground">An email will be sent to {colleagueEmail} to confirm your request</p>
                </div>
              </div>
            </div>

            <div className="flex justify-between">
              <button onClick={() => setStep("add-colleague")} className={btnSecondary}><ChevronLeft className="h-4 w-4" /> Back</button>
              <button
                onClick={() => {
                  kyc.setKycCompleted();
                  if (role) kyc.setKycRole(role);
                  kyc.setKycProfile({
                    companyEmail, firstName, lastName, jobTitle, phoneNumber,
                    companyName, companyWebsite,
                    projectName, plantName, projectLifetime, roleInProject,
                    primaryPathway, plantConfiguration, country, region, city,
                    siteEnvironment, maturityStage, expectedCod, fuelTypesProduced, productionCapacity,
                    infraType: infraType ?? undefined, facilityName, regulatoryLicense, throughputCapacity, connectedTo,
                    ccusType, captureSource, storageMethod, annualCo2Capacity,
                    procurementSector, annualVolume, fuelTypes, deliveryLocation, contractStatus,
                    colleagueName, colleagueEmail, colleagueRole,
                  });
                  if (companyName) {
                    kyc.setCompany(companyName);
                  }
                  setStep("confirmation");
                }}
                className={btnPrimary}
              >
                Submit Verification <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}

        {/* ============================================================ */}
        {/* STEP 6: Confirmation                                         */}
        {/* ============================================================ */}
        {step === "confirmation" && (() => {
          // Project matching will use GEX's project registry when available
          const matchedProjects: Array<{ id: string; name: string; country: string }> = [];
          const matchedCount = matchedProjects.length;
          return (
          <div className="space-y-6">
            <div className="bg-card border border-border rounded-xl p-8 text-center space-y-5">
              <div className="mx-auto h-16 w-16 rounded-full bg-emerald-500/10 flex items-center justify-center">
                <CheckCircle2 className="h-8 w-8 text-emerald-500" />
              </div>

              <div className="space-y-2">
                <h2 className="text-xl font-bold text-card-foreground">Welcome aboard, {firstName}!</h2>
                <p className="text-sm text-muted-foreground max-w-md mx-auto">
                  Your {role ? roleConfig[role].label : ""} profile is now active. You're all set to start using the platform.
                </p>
              </div>

              {/* Project matching result */}
              {role === "production" && matchedCount > 0 && (
                <div className="bg-emerald-500/5 border-2 border-emerald-500/20 rounded-xl p-5 text-left space-y-3 max-w-md mx-auto">
                  <div className="flex items-center gap-2">
                    <div className="h-8 w-8 rounded-full bg-emerald-500/10 flex items-center justify-center">
                      <MapPin className="h-4 w-4 text-emerald-500" />
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-card-foreground">
                        We identified {matchedCount} project{matchedCount !== 1 ? "s" : ""} linked to {companyName}
                      </h4>
                      <p className="text-[10px] text-muted-foreground">Please review and verify your project data to unlock full platform features.</p>
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    {matchedProjects.slice(0, 4).map((p) => (
                      <div key={p.id} className="flex items-center gap-2 rounded-lg bg-background/60 px-3 py-2">
                        <div className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse flex-shrink-0" />
                        <span className="text-xs font-medium text-card-foreground truncate">{p.name}</span>
                        <span className="text-[10px] text-muted-foreground ml-auto flex-shrink-0">{p.country}</span>
                      </div>
                    ))}
                    {matchedCount > 4 && (
                      <p className="text-[10px] text-muted-foreground text-center">+ {matchedCount - 4} more project{matchedCount - 4 !== 1 ? "s" : ""}</p>
                    )}
                  </div>
                </div>
              )}

              {role === "production" && matchedCount === 0 && (
                <div className="bg-primary/5 border border-primary/10 rounded-xl p-5 text-left space-y-2 max-w-md mx-auto">
                  <h4 className="text-sm font-bold text-card-foreground flex items-center gap-2">
                    <Factory className="h-4 w-4 text-primary" /> No existing projects found
                  </h4>
                  <p className="text-xs text-muted-foreground">
                    We didn't find any projects linked to "{companyName}" yet. Add your first project to get started with plant modelling, compliance tracking, and bankability analysis.
                  </p>
                </div>
              )}

              {(role === "offtaker" || role === "infrastructure") && (
                <div className="bg-primary/5 border border-primary/10 rounded-xl p-5 text-left space-y-2 max-w-md mx-auto">
                  <h4 className="text-sm font-bold text-card-foreground">You're verified and ready to go</h4>
                  <p className="text-xs text-muted-foreground">
                    {role === "offtaker"
                      ? "Explore the map to find producers and start making deals. Your procurement profile is live."
                      : "Your infrastructure profile is active. Verify your asset data and connect with producers on the map."}
                  </p>
                </div>
              )}
            </div>

            {/* Action cards, context-aware CTAs */}
            <div className="grid gap-3 sm:grid-cols-2">
              {/* Production with matched projects → Verify projects (primary) */}
              {role === "production" && matchedCount > 0 && (
                <>
                  <button
                    onClick={() => navigate("/portfolio")}
                    className="bg-card border-2 border-primary rounded-xl p-5 text-left hover:bg-primary/5 transition-colors group"
                  >
                    <CheckCircle2 className="h-5 w-5 text-primary mb-2" />
                    <h3 className="text-sm font-bold text-card-foreground group-hover:text-primary transition-colors">
                      Verify your project{matchedCount !== 1 ? "s" : ""}
                    </h3>
                    <p className="text-[10px] text-muted-foreground mt-1">
                      Review and confirm the data for {matchedCount} project{matchedCount !== 1 ? "s" : ""} linked to {companyName}
                    </p>
                  </button>
                  <button
                    onClick={() => navigate("/")}
                    className="bg-card border border-border rounded-xl p-5 text-left hover:border-primary/30 transition-colors group"
                  >
                    <MapPin className="h-5 w-5 text-muted-foreground group-hover:text-primary mb-2 transition-colors" />
                    <h3 className="text-sm font-bold text-card-foreground">View on the Map</h3>
                    <p className="text-[10px] text-muted-foreground mt-1">See your projects highlighted on the ecosystem map</p>
                  </button>
                </>
              )}

              {/* Production with NO matched projects → Add project (primary) */}
              {role === "production" && matchedCount === 0 && (
                <>
                  <button
                    onClick={() => navigate("/plants")}
                    className="bg-card border-2 border-primary rounded-xl p-5 text-left hover:bg-primary/5 transition-colors group"
                  >
                    <Hammer className="h-5 w-5 text-primary mb-2" />
                    <h3 className="text-sm font-bold text-card-foreground group-hover:text-primary transition-colors">
                      Add your first project
                    </h3>
                    <p className="text-[10px] text-muted-foreground mt-1">
                      Set up your plant in the Plant Builder to start modelling
                    </p>
                  </button>
                  <button
                    onClick={() => navigate("/")}
                    className="bg-card border border-border rounded-xl p-5 text-left hover:border-primary/30 transition-colors group"
                  >
                    <MapPin className="h-5 w-5 text-muted-foreground group-hover:text-primary mb-2 transition-colors" />
                    <h3 className="text-sm font-bold text-card-foreground">Explore the Map</h3>
                    <p className="text-[10px] text-muted-foreground mt-1">Discover projects and potential partners worldwide</p>
                  </button>
                </>
              )}

              {role === "offtaker" && (
                <>
                  <button
                    onClick={() => navigate("/")}
                    className="bg-card border-2 border-primary rounded-xl p-5 text-left hover:bg-primary/5 transition-colors group"
                  >
                    <ShoppingCart className="h-5 w-5 text-primary mb-2" />
                    <h3 className="text-sm font-bold text-card-foreground group-hover:text-primary transition-colors">Find producers</h3>
                    <p className="text-[10px] text-muted-foreground mt-1">Browse production projects matching your fuel needs</p>
                  </button>
                  <button
                    onClick={() => navigate("/")}
                    className="bg-card border border-border rounded-xl p-5 text-left hover:border-primary/30 transition-colors group"
                  >
                    <MapPin className="h-5 w-5 text-muted-foreground group-hover:text-primary mb-2 transition-colors" />
                    <h3 className="text-sm font-bold text-card-foreground">Explore the Map</h3>
                    <p className="text-[10px] text-muted-foreground mt-1">Discover the global green fuel ecosystem</p>
                  </button>
                </>
              )}

              {role === "infrastructure" && (
                <>
                  <button
                    onClick={() => navigate("/")}
                    className="bg-card border-2 border-primary rounded-xl p-5 text-left hover:bg-primary/5 transition-colors group"
                  >
                    <BarChart3 className="h-5 w-5 text-primary mb-2" />
                    <h3 className="text-sm font-bold text-card-foreground group-hover:text-primary transition-colors">Verify your data</h3>
                    <p className="text-[10px] text-muted-foreground mt-1">Review and validate your infrastructure asset details</p>
                  </button>
                  <button
                    onClick={() => navigate("/")}
                    className="bg-card border border-border rounded-xl p-5 text-left hover:border-primary/30 transition-colors group"
                  >
                    <MapPin className="h-5 w-5 text-muted-foreground group-hover:text-primary mb-2 transition-colors" />
                    <h3 className="text-sm font-bold text-card-foreground">Explore the Map</h3>
                    <p className="text-[10px] text-muted-foreground mt-1">Connect with producers on the ecosystem map</p>
                  </button>
                </>
              )}
            </div>
          </div>
          );
        })()}
      </div>
    </div>
  );
};

export { KycVerification };
export default KycVerification;
