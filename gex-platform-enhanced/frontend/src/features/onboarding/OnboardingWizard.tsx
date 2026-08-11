import React, { useState } from 'react';
import {
  CheckCircle, AlertCircle, TrendingUp, DollarSign, Award,
  FileText, ArrowRight, ArrowLeft, Download, Sparkles
} from 'lucide-react';
import { useUserRole } from '@/contexts/UserRoleContext';
import type { UserRole } from '@/contexts/UserRoleContext';

interface WizardStep {
  number: number;
  title: string;
  description: string;
}

const steps: WizardStep[] = [
  { number: 1, title: "Project Basics", description: "Tell us about your project" },
  { number: 2, title: "Economics", description: "Estimate costs and revenue" },
  { number: 3, title: "Certification", description: "Check subsidy eligibility" },
  { number: 4, title: "Your Report", description: "Get viability assessment" }
];

/**
 * Offtaker demand intake data — collected instead of producer steps 1-3.
 * Captures: what molecule, how much, where delivered, spec, cert scheme,
 * price threshold, and key logistics constraints.
 */
interface OfftakerIntakeData {
  molecule: string;
  demand_mtpy: string;
  delivery_point: string;
  delivery_country: string;
  required_from_year: number;
  required_to_year: number;
  spec_requirements: string;
  certification_schemes: string[];  // e.g. ['RED_III', 'FuelEU', 'CertifHy']
  price_ceiling_eur_kg: string;
  min_contract_tenor_years: string;
  storage_type: string;            // e.g. 'port terminal', 'pipeline', 'ship-to-ship'
  logistics_constraints: string;
}

const OFFTAKER_CERT_OPTIONS = [
  { value: 'RED_III',   label: 'RED III (EU renewable fuels)' },
  { value: 'FuelEU',   label: 'FuelEU Maritime' },
  { value: 'CertifHy', label: 'CertifHy (hydrogen)' },
  { value: 'CORSIA',   label: 'CORSIA (aviation SAF)' },
  { value: 'ReFuelEU', label: 'ReFuelEU Aviation' },
  { value: 'ISCC',     label: 'ISCC Plus' },
];

type EntryObjective =
  | 'PROJECT_REALITY'
  | 'BUY_FUEL'
  | 'INSURE_PROJECT'
  | 'CERTIFY_RFNBO';

const ENTRY_OPTIONS: Array<{
  id: EntryObjective;
  title: string;
  description: string;
  helper: string;
  Icon: React.ElementType;
}> = [
  {
    id: 'PROJECT_REALITY',
    title: 'Is this project real enough to pursue?',
    description: 'Run the viability path for a producer or sponsor team.',
    helper: 'Best for project sponsors trying to validate market, financing, and certification.',
    Icon: TrendingUp,
  },
  {
    id: 'BUY_FUEL',
    title: 'Can I buy this fuel?',
    description: 'Define demand, logistics, and certification needs first.',
    helper: 'Best for offtakers seeking qualified supply and contract readiness.',
    Icon: DollarSign,
  },
  {
    id: 'INSURE_PROJECT',
    title: 'Can I insure this project?',
    description: 'Start from molecule risk, coverage gaps, and evidence quality.',
    helper: 'Best for insurers and risk engineers reviewing hazard and coverage readiness.',
    Icon: AlertCircle,
  },
  {
    id: 'CERTIFY_RFNBO',
    title: 'Can I certify this as RFNBO?',
    description: 'Start from pathway viability and missing evidence.',
    helper: 'Best for certifiers and compliance teams checking eligibility.',
    Icon: Award,
  },
];

const ENTRY_MOLECULES = ['e-Methane', 'e-Methanol', 'e-NH3', 'HVO', 'SAF', 'e-Gasoline', 'e-LG', 'e-Naphtha'] as const;

// ── Step 1 professional intake: controlled jurisdictions + RFNBO-gating inputs ──
const JURISDICTIONS: Array<{ group: string; countries: string[] }> = [
  { group: 'European Union', countries: ['Germany', 'France', 'Italy', 'Spain', 'Netherlands', 'Belgium', 'Portugal', 'Denmark', 'Sweden', 'Finland', 'Poland', 'Austria', 'Ireland', 'Greece', 'Romania', 'Czechia', 'Other EU'] },
  { group: 'Other Europe', countries: ['United Kingdom', 'Norway', 'Switzerland'] },
  { group: 'Americas', countries: ['United States', 'Canada', 'Chile', 'Brazil'] },
  { group: 'Africa & MENA', countries: ['Morocco', 'Egypt', 'Saudi Arabia', 'UAE', 'South Africa'] },
  { group: 'Asia-Pacific', countries: ['Australia', 'India', 'Japan'] },
  { group: 'Other', countries: ['Other'] },
];
const EU_SET = new Set(JURISDICTIONS[0].countries);

const POWER_BASIS_OPTIONS = [
  { value: 'off_grid', label: 'Off-grid / behind-the-meter (dedicated renewables)' },
  { value: 'ppa', label: 'Grid + additional-renewables PPA' },
  { value: 'grid', label: 'Grid power (guarantees of origin)' },
  { value: 'hybrid', label: 'Hybrid' },
];

const OFFTAKE_STATUS_OPTIONS = [
  { value: 'none', label: 'None yet — exploring' },
  { value: 'discussion', label: 'In discussion' },
  { value: 'loi', label: 'LOI / term sheet' },
  { value: 'binding', label: 'Binding offtake agreement' },
];

// Live "clues" — each ties an input to what GEX will actually do with it. Honest,
// specific, and a window into the depth behind the doorway (eligibility → gates
// → capital release). Empty string => no clue yet.
const MOLECULE_NOTES: Record<string, string> = {
  'e-Methanol': 'e-Methanol is “organic basic chemicals” (NACE 20.14) — on the EU restricted-sector list, so EU public/concessional capital is available only via the EU-Taxonomy carve-out. GEX screens exactly this.',
  'e-NH3': 'Green ammonia is “fertilisers & nitrogen” (NACE 20.15) — restricted-sector by default; unlocked for EU capital through the EU-Taxonomy carve-out. GEX screens it for you.',
  'SAF': 'SAF runs through ReFuelEU / CORSIA and RFNBO (RED III). GEX tracks the certification chain and grades the evidence behind each claim.',
  'e-Methane': 'e-Methane must evidence RFNBO status (RED III) and a compliant CO₂ source. GEX carries both as capital-release conditions, not checkboxes.',
  'e-Gasoline': 'A drop-in e-fuel — eligibility hinges on RFNBO power and CO₂ sourcing. GEX maps the evidence a certifier and a lender each need.',
  'e-Naphtha': 'e-Naphtha is a chemical feedstock — likely restricted-sector; EU capital via the Taxonomy carve-out. GEX screens the pathway.',
  'e-LG': 'Liquefied e-gas — RFNBO status plus CO₂ provenance drive eligibility. GEX tracks both through to the certificate.',
  'HVO': 'HVO is a biofuel — RED III feedstock sustainability and ILUC rules dominate. GEX grades the chain-of-custody evidence.',
};
function moleculeNote(m: string): string {
  return MOLECULE_NOTES[m] || 'GEX will screen this pathway’s RFNBO / RED III eligibility and the evidence it needs.';
}
function jurisdictionNote(c: string): string {
  if (!c) return '';
  if (EU_SET.has(c)) return `In the EU, RED III (RFNBO), the EU Taxonomy and state-aid limits set eligibility. GEX screens the restricted-sector list and the Taxonomy carve-out for ${c === 'Other EU' ? 'your EU member state' : c}.`;
  if (c === 'United States') return 'In the US, 45V / 45Z drive the incentive stack. GEX maps the equivalent eligibility and the evidence it rests on.';
  if (c === 'United Kingdom') return 'The UK runs its own RTFO / SAF mandate rather than RED III. GEX maps the applicable regime and its proofs.';
  return `GEX will map ${c}’s renewable-fuel regime and the evidence required to bank a project there.`;
}
function powerNote(p: string): string {
  if (p === 'off_grid') return 'Dedicated off-grid renewables simplify additionality and drop grid-connection gates — a cleaner RFNBO story.';
  if (p === 'ppa') return 'A PPA supports additionality, but RED III temporal (hourly from 2030) and geographic correlation still apply. GEX tracks them as gates.';
  if (p === 'grid') return 'Grid power needs cancelled guarantees of origin plus temporal/geographic correlation to count as renewable — the hardest RFNBO test.';
  if (p === 'hybrid') return 'A hybrid supply means correlation is evidenced per source. GEX keeps the accounting auditable.';
  return '';
}
function offtakeNote(o: string): string {
  if (o === 'none') return 'Offtake is the bankability anchor — lenders size debt off contracted volume, tenor and buyer credit. GEX treats it as a capital-release condition, and shows announced vs committed honestly.';
  if (o === 'discussion') return 'Early interest is directional, not bankable. GEX distinguishes “indicative” from “committed” so nobody over-reads it.';
  if (o === 'loi') return 'An LOI / term sheet is progress but conditional. GEX tracks the conditions precedent that turn it into bankable offtake.';
  if (o === 'binding') return 'A binding offtake is a strong bankability signal. GEX grades the buyer’s credit and the contract’s CPs.';
  return '';
}

// ── Step 3 (certification) clues — same discipline: tie each input to a real gate ──
function renewableNote(pct: number): string {
  if (pct >= 100) return 'Fully renewable power is the cleanest RFNBO story — you still need cancelled guarantees of origin plus temporal (hourly from 2030) and geographic correlation. GEX carries each as a gate.';
  if (pct >= 90) return 'Near-fully renewable — but RED III counts renewable electricity only where correlation and additionality are evidenced. GEX flags the shortfall hours.';
  return 'Below ~90% renewable, RFNBO status is at risk — grey grid hours don’t count. GEX shows exactly which hours fail correlation.';
}
function ghgNote(target: number): string {
  if (target === null || target === undefined || Number.isNaN(target)) return '';
  return 'RFNBO needs roughly a 70% GHG saving vs the fossil comparator (~28.2 gCO₂e/MJ). GEX runs your pathway’s LCA against the current Delegated Act — the threshold is an input that moves with fuel and vintage, not a constant.';
}
function certsNotes(certs: string[], country: string): string[] {
  const notes: string[] = [];
  const isEU = EU_SET.has(country);
  if (certs.includes('RED_III') || certs.includes('RFNBO')) notes.push('RED III / RFNBO turns on additionality plus temporal & geographic power correlation — GEX carries each as a capital-release condition, not a checkbox.');
  if (certs.includes('45V')) {
    if (isEU) notes.push('45V is a US production credit — for an EU project it doesn’t apply; RED III / RFNBO is your track. GEX won’t let a mismatched scheme inflate the read.');
    else notes.push('45V pays by GHG tier (kg CO₂e/kg H₂) and needs US siting and a placed-in-service window — GEX checks the tier and the timing.');
  }
  if (certs.includes('CORSIA')) notes.push('CORSIA applies to aviation SAF — GEX maps it to ReFuelEU Aviation where relevant.');
  return notes;
}

const ENTRY_ROLE_PRESETS: Record<EntryObjective, UserRole> = {
  PROJECT_REALITY: {
    company_type: 'PRODUCER',
    service_type: null,
    business_function: 'FINANCE_TREASURY',
    company_name: 'Prospective Producer',
    user_name: 'Project Lead',
  },
  BUY_FUEL: {
    company_type: 'OFFTAKER',
    service_type: null,
    business_function: 'COMMERCIAL',
    company_name: 'Prospective Offtaker',
    user_name: 'Procurement Lead',
  },
  INSURE_PROJECT: {
    company_type: 'THIRD_PARTY',
    service_type: 'INSURER',
    business_function: 'FINANCE_TREASURY',
    company_name: 'Prospective Insurer',
    user_name: 'Risk Lead',
  },
  CERTIFY_RFNBO: {
    company_type: 'THIRD_PARTY',
    service_type: 'CERTIFIER',
    business_function: 'COMPLIANCE_LEGAL',
    company_name: 'Prospective Certifier',
    user_name: 'Certification Lead',
  },
};

function mapEntryMoleculeToWizardValue(molecule: string): string {
  return molecule;
}

const OnboardingWizard: React.FC = () => {
  const { setRole } = useUserRole();
  const [currentStep, setCurrentStep] = useState(1);
  const [entryStarted, setEntryStarted] = useState(false);
  const [entryObjective, setEntryObjective] = useState<EntryObjective>('PROJECT_REALITY');
  const [entryMolecule, setEntryMolecule] = useState<(typeof ENTRY_MOLECULES)[number]>('e-Methane');
  const [loading, setLoading] = useState(false);

  // ── Offtaker intake state ──────────────────────────────────────────────────
  const [offtakerData, setOfftakerData] = useState<OfftakerIntakeData>({
    molecule: entryMolecule,
    demand_mtpy: '',
    delivery_point: '',
    delivery_country: '',
    required_from_year: 2027,
    required_to_year: 2042,
    spec_requirements: '',
    certification_schemes: ['RED_III'],
    price_ceiling_eur_kg: '',
    min_contract_tenor_years: '10',
    storage_type: '',
    logistics_constraints: '',
  });
  const [offtakerSubmitted, setOfftakerSubmitted] = useState(false);

  // ── Producer wizard state ──────────────────────────────────────────────────
  const [step1Data, setStep1Data] = useState({
    molecule: mapEntryMoleculeToWizardValue(entryMolecule),
    capacity_mtpd: '',
    location: '',
    country: '',
    power_basis: '',
    offtake_status: '',
    production_start_year: 2027,
    production_end_year: 2042
  });

  const [step2Data, setStep2Data] = useState({
    estimated_capex_eur: '',
    estimated_opex_eur_kg: '',
    target_offtake_price_eur_kg: '',
    electricity_source: 'renewable',
    feedstock_source: 'water'
  });

  const [step3Data, setStep3Data] = useState({
    electricity_renewable_percentage: 100,
    ghg_intensity_target: 0.45,
    target_certifications: ['RED_III', '45V'],
    existing_certifications: []
  });

  const [contactEmail, setContactEmail] = useState('');
  const [demandResult, setDemandResult] = useState<any>(null);
  const [bankabilityResult, setBankabilityResult] = useState<any>(null);
  const [certificationResult, setCertificationResult] = useState<any>(null);
  const [finalReport, setFinalReport] = useState<any>(null);

  // Determine which journey branch to render after the decision-first entry
  const isOfftaker = entryObjective === 'BUY_FUEL';
  const isSpecialistPath = entryObjective === 'INSURE_PROJECT' || entryObjective === 'CERTIFY_RFNBO';

  // Step 0: decision-first entry
  if (!entryStarted) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-teal-50 p-6">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-8">
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white border border-slate-200 text-slate-700 mb-4">
              <Sparkles className="w-4 h-4 text-teal-600" />
              <span className="text-sm font-medium">Decision-First Entry</span>
            </div>
            <h1 className="text-4xl font-bold text-slate-900 mb-2">What are you trying to figure out today?</h1>
            <p className="text-lg text-slate-600 max-w-2xl mx-auto">
              Start with the decision, not the role. GEX will shape the next path around the answer you need.
            </p>
          </div>

          <div className="bg-white rounded-3xl shadow-xl border border-slate-200 p-8 space-y-8">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 mb-4">
                Choose Your Objective
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {ENTRY_OPTIONS.map(({ id, title, description, helper, Icon }) => {
                  const selected = entryObjective === id;
                  return (
                    <button
                      key={id}
                      type="button"
                      onClick={() => setEntryObjective(id)}
                      className={`rounded-2xl border p-5 text-left transition-all ${
                        selected
                          ? 'border-teal-500 bg-teal-50 shadow-sm'
                          : 'border-slate-200 bg-white hover:border-slate-300'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
                          selected ? 'bg-teal-600 text-white' : 'bg-slate-100 text-slate-600'
                        }`}>
                          <Icon className="w-5 h-5" />
                        </div>
                        <div className="min-w-0">
                          <div className="text-base font-bold text-slate-900">{title}</div>
                          <div className="text-sm text-slate-600 mt-1">{description}</div>
                          <div className="text-xs text-slate-500 mt-2 leading-relaxed">{helper}</div>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 mb-3">
                Which Molecule?
              </label>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {ENTRY_MOLECULES.map((molecule) => (
                  <button
                    key={molecule}
                    type="button"
                    onClick={() => setEntryMolecule(molecule)}
                    className={`rounded-xl border px-4 py-3 text-sm font-semibold transition-colors ${
                      entryMolecule === molecule
                        ? 'border-teal-500 bg-teal-50 text-teal-700'
                        : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                    }`}
                  >
                    {molecule}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center justify-between gap-4 rounded-2xl border border-slate-200 bg-slate-50 px-5 py-4">
              <div>
                <div className="text-sm font-semibold text-slate-900">
                  {ENTRY_OPTIONS.find((option) => option.id === entryObjective)?.title}
                </div>
                <div className="text-xs text-slate-500 mt-1">
                  Molecule context: {entryMolecule}
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setRole(ENTRY_ROLE_PRESETS[entryObjective]);
                  setCurrentStep(1);
                  setLoading(false);
                  setOfftakerSubmitted(false);
                  setOfftakerData({
                    molecule: entryMolecule,
                    demand_mtpy: '',
                    delivery_point: '',
                    delivery_country: '',
                    required_from_year: 2027,
                    required_to_year: 2042,
                    spec_requirements: '',
                    certification_schemes: ['RED_III'],
                    price_ceiling_eur_kg: '',
                    min_contract_tenor_years: '10',
                    storage_type: '',
                    logistics_constraints: '',
                  });
                  setStep1Data({
                    molecule: mapEntryMoleculeToWizardValue(entryMolecule),
                    capacity_mtpd: '',
                    location: '',
                    country: '',
                    production_start_year: 2027,
                    production_end_year: 2042,
                  });
                  setStep2Data({
                    estimated_capex_eur: '',
                    estimated_opex_eur_kg: '',
                    target_offtake_price_eur_kg: '',
                    electricity_source: 'renewable',
                    feedstock_source: 'water',
                  });
                  setStep3Data({
                    electricity_renewable_percentage: 100,
                    ghg_intensity_target: 0.45,
                    target_certifications: ['RED_III', '45V'],
                    existing_certifications: [],
                  });
                  setContactEmail('');
                  setDemandResult(null);
                  setBankabilityResult(null);
                  setCertificationResult(null);
                  setFinalReport(null);
                  setEntryStarted(true);
                }}
                className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800"
              >
                Continue
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }
  // If the user is an offtaker, render the demand intake form instead of the producer wizard
  if (isOfftaker) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-teal-50 to-cyan-100 p-6">
        <div className="max-w-2xl mx-auto">
          <div className="bg-white rounded-2xl shadow-xl p-8">
            <div className="mb-6">
              <span className="inline-block px-3 py-1 rounded-full bg-teal-100 text-teal-700 text-xs font-semibold mb-3">
                Offtaker Intake
              </span>
              <h1 className="text-2xl font-bold text-gray-900">Tell us what you need to buy</h1>
              <p className="text-sm text-gray-500 mt-1">
                Describe your demand so GreenEarthX can match you with qualifying supply, run bankability
                checks on counterparties, and prepare certification-ready documentation.
              </p>
            </div>

            {offtakerSubmitted ? (
              <div className="text-center py-10">
                <CheckCircle className="w-12 h-12 text-teal-600 mx-auto mb-4" />
                <h2 className="text-xl font-bold text-gray-900 mb-2">Demand profile submitted</h2>
                <p className="text-sm text-gray-500 mb-6">
                  Your intake has been registered. The platform will match qualifying supply
                  and notify you when bankable candidates are available.
                </p>
                <button
                  onClick={() => window.location.href = '/marketplace'}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-teal-600 text-white text-sm font-semibold hover:bg-teal-700"
                >
                  Browse Supply Offers <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <div className="space-y-5">
                {/* Molecule + volume */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-gray-600 mb-1">Molecule required</label>
                    <select
                      value={offtakerData.molecule}
                      onChange={e => setOfftakerData(d => ({ ...d, molecule: e.target.value }))}
                      className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400"
                    >
                      {ENTRY_MOLECULES.map(m => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-600 mb-1">Demand volume (mt/year)</label>
                    <input
                      type="number"
                      placeholder="e.g. 50000"
                      value={offtakerData.demand_mtpy}
                      onChange={e => setOfftakerData(d => ({ ...d, demand_mtpy: e.target.value }))}
                      className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400"
                    />
                  </div>
                </div>

                {/* Delivery */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-gray-600 mb-1">Delivery point / port</label>
                    <input
                      type="text"
                      placeholder="e.g. Port of Hamburg"
                      value={offtakerData.delivery_point}
                      onChange={e => setOfftakerData(d => ({ ...d, delivery_point: e.target.value }))}
                      className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-600 mb-1">Storage / handling type</label>
                    <input
                      type="text"
                      placeholder="e.g. port terminal, pipeline, STS"
                      value={offtakerData.storage_type}
                      onChange={e => setOfftakerData(d => ({ ...d, storage_type: e.target.value }))}
                      className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400"
                    />
                  </div>
                </div>

                {/* Contract window */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-gray-600 mb-1">Required from (year)</label>
                    <input
                      type="number"
                      value={offtakerData.required_from_year}
                      onChange={e => setOfftakerData(d => ({ ...d, required_from_year: parseInt(e.target.value) }))}
                      className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-600 mb-1">Min contract tenor (years)</label>
                    <input
                      type="number"
                      placeholder="e.g. 10"
                      value={offtakerData.min_contract_tenor_years}
                      onChange={e => setOfftakerData(d => ({ ...d, min_contract_tenor_years: e.target.value }))}
                      className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400"
                    />
                  </div>
                </div>

                {/* Price ceiling */}
                <div>
                  <label className="block text-xs font-semibold text-gray-600 mb-1">Price ceiling (€/kg)</label>
                  <input
                    type="number"
                    placeholder="e.g. 3.50"
                    value={offtakerData.price_ceiling_eur_kg}
                    onChange={e => setOfftakerData(d => ({ ...d, price_ceiling_eur_kg: e.target.value }))}
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400"
                  />
                </div>

                {/* Certification schemes */}
                <div>
                  <label className="block text-xs font-semibold text-gray-600 mb-2">Required certification schemes</label>
                  <div className="flex flex-wrap gap-2">
                    {OFFTAKER_CERT_OPTIONS.map(opt => {
                      const checked = offtakerData.certification_schemes.includes(opt.value);
                      return (
                        <button
                          key={opt.value}
                          type="button"
                          onClick={() => setOfftakerData(d => ({
                            ...d,
                            certification_schemes: checked
                              ? d.certification_schemes.filter(s => s !== opt.value)
                              : [...d.certification_schemes, opt.value],
                          }))}
                          className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                            checked
                              ? 'bg-teal-600 text-white border-teal-600'
                              : 'bg-white text-gray-600 border-gray-200 hover:border-teal-400'
                          }`}
                        >
                          {opt.label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Spec requirements */}
                <div>
                  <label className="block text-xs font-semibold text-gray-600 mb-1">Product spec requirements</label>
                  <textarea
                    rows={2}
                    placeholder="e.g. purity ≥99.5%, max moisture 10ppm, ISO 14687 Grade C"
                    value={offtakerData.spec_requirements}
                    onChange={e => setOfftakerData(d => ({ ...d, spec_requirements: e.target.value }))}
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400 resize-none"
                  />
                </div>

                {/* Logistics constraints */}
                <div>
                  <label className="block text-xs font-semibold text-gray-600 mb-1">Logistics constraints</label>
                  <textarea
                    rows={2}
                    placeholder="e.g. terminal limited to 10,000t NH3 tanks, ship-compatible with class C type C"
                    value={offtakerData.logistics_constraints}
                    onChange={e => setOfftakerData(d => ({ ...d, logistics_constraints: e.target.value }))}
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400 resize-none"
                  />
                </div>

                <button
                  disabled={loading || !offtakerData.demand_mtpy || !offtakerData.delivery_point}
                  onClick={async () => {
                    setLoading(true);
                    try {
                      await fetch('/api/v1/onboarding/offtaker-intake', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(offtakerData),
                      });
                    } catch { /* best-effort — show success regardless */ }
                    setOfftakerSubmitted(true);
                    setLoading(false);
                  }}
                  className="w-full py-3 rounded-xl bg-teal-600 text-white text-sm font-bold hover:bg-teal-700 disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {loading ? 'Submitting…' : <>Submit demand profile <ArrowRight className="w-4 h-4" /></>}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (isSpecialistPath) {
    const isInsurerPath = entryObjective === 'INSURE_PROJECT';

    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-indigo-50 p-6">
        <div className="max-w-3xl mx-auto">
          <div className="bg-white rounded-3xl shadow-xl border border-slate-200 p-8">
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-slate-100 text-slate-700 mb-5">
              {isInsurerPath ? <AlertCircle className="w-4 h-4 text-amber-600" /> : <Award className="w-4 h-4 text-indigo-600" />}
              <span className="text-sm font-medium">
                {isInsurerPath ? 'Insurer Risk Path' : 'Certification Path'}
              </span>
            </div>

            <h1 className="text-3xl font-bold text-slate-900 mb-3">
              {isInsurerPath ? 'Start from risk and evidence, not from a generic wizard.' : 'Start from pathway viability and missing evidence.'}
            </h1>
            <p className="text-slate-600 leading-7 mb-8">
              GEX now captures your objective first. For {entryMolecule}, the next step is a specialist workflow that should open on the evidence trail, molecule-specific blockers, and the single next decision.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 mb-2">Molecule</div>
                <div className="text-lg font-bold text-slate-900">{entryMolecule}</div>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 mb-2">Primary View</div>
                <div className="text-lg font-bold text-slate-900">
                  {isInsurerPath ? 'Coverage + Hazard' : 'Eligibility + Evidence'}
                </div>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 mb-2">Next Decision</div>
                <div className="text-lg font-bold text-slate-900">
                  {isInsurerPath ? 'Can this risk be placed?' : 'Can this pathway be certified?'}
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-5 mb-8">
              <h2 className="text-sm font-bold text-slate-900 mb-3">What GEX should show next</h2>
              <div className="space-y-2 text-sm text-slate-600">
                <p>1. The molecule-specific blocker at the top of the screen.</p>
                <p>2. The latest verified evidence and who supplied it.</p>
                <p>3. One next action owned by one institution.</p>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row gap-3">
              <button
                type="button"
                onClick={() => window.location.href = '/login'}
                className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800"
              >
                Sign In To Continue
                <ArrowRight className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={() => setEntryStarted(false)}
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 px-5 py-3 text-sm font-semibold text-slate-600 hover:bg-slate-50"
              >
                Choose Another Path
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Step 1: Submit and check market demand
  const submitStep1 = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/v1/onboarding/step1/market-demand', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...step1Data,
          capacity_mtpd: parseFloat(step1Data.capacity_mtpd),
          production_start_year: parseInt(step1Data.production_start_year.toString()),
          production_end_year: parseInt(step1Data.production_end_year.toString())
        })
      });
      
      const data = await response.json();
      setDemandResult(data);
      setCurrentStep(2);
    } catch (error) {
      console.error('Error checking market demand:', error);
      alert('Failed to check market demand. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Step 2: Submit and check bankability
  const submitStep2 = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/v1/onboarding/step2/bankability-check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          basics: {
            ...step1Data,
            capacity_mtpd: parseFloat(step1Data.capacity_mtpd),
            production_start_year: parseInt(step1Data.production_start_year.toString()),
            production_end_year: parseInt(step1Data.production_end_year.toString())
          },
          economics: {
            ...step2Data,
            estimated_capex_eur: parseFloat(step2Data.estimated_capex_eur),
            estimated_opex_eur_kg: parseFloat(step2Data.estimated_opex_eur_kg),
            target_offtake_price_eur_kg: parseFloat(step2Data.target_offtake_price_eur_kg)
          }
        })
      });
      
      const data = await response.json();
      setBankabilityResult(data);
      setCurrentStep(3);
    } catch (error) {
      console.error('Error checking bankability:', error);
      alert('Failed to check bankability. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Step 3: Submit and check certification
  const submitStep3 = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/v1/onboarding/step3/certification-eligibility', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          basics: {
            ...step1Data,
            capacity_mtpd: parseFloat(step1Data.capacity_mtpd),
            production_start_year: parseInt(step1Data.production_start_year.toString()),
            production_end_year: parseInt(step1Data.production_end_year.toString())
          },
          economics: {
            ...step2Data,
            estimated_capex_eur: parseFloat(step2Data.estimated_capex_eur),
            estimated_opex_eur_kg: parseFloat(step2Data.estimated_opex_eur_kg),
            target_offtake_price_eur_kg: parseFloat(step2Data.target_offtake_price_eur_kg)
          },
          certification: step3Data
        })
      });
      
      const data = await response.json();
      setCertificationResult(data);
      
      // Generate final report
      await generateFinalReport();
    } catch (error) {
      console.error('Error checking certification:', error);
      alert('Failed to check certification. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Generate final report
  const generateFinalReport = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/v1/onboarding/complete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          step1: {
            ...step1Data,
            capacity_mtpd: parseFloat(step1Data.capacity_mtpd),
            production_start_year: parseInt(step1Data.production_start_year.toString()),
            production_end_year: parseInt(step1Data.production_end_year.toString())
          },
          step2: {
            ...step2Data,
            estimated_capex_eur: parseFloat(step2Data.estimated_capex_eur),
            estimated_opex_eur_kg: parseFloat(step2Data.estimated_opex_eur_kg),
            target_offtake_price_eur_kg: parseFloat(step2Data.target_offtake_price_eur_kg)
          },
          step3: step3Data,
          contact_email: contactEmail || null
        })
      });
      
      const data = await response.json();
      setFinalReport(data.report);
      setCurrentStep(4);
    } catch (error) {
      console.error('Error generating report:', error);
      alert('Failed to generate report. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Progress bar
  const ProgressBar = () => (
    <div className="mb-8">
      <div className="flex justify-between mb-2">
        {steps.map((step) => (
          <div key={step.number} className="flex-1 text-center">
            <div className={`inline-flex items-center justify-center w-10 h-10 rounded-full ${
              currentStep >= step.number 
                ? 'bg-blue-600 text-white' 
                : 'bg-gray-200 text-gray-600'
            }`}>
              {currentStep > step.number ? <CheckCircle className="w-5 h-5" /> : step.number}
            </div>
            <div className={`text-xs mt-2 ${currentStep >= step.number ? 'text-blue-600 font-medium' : 'text-gray-500'}`}>
              {step.title}
            </div>
          </div>
        ))}
      </div>
      <div className="relative pt-1">
        <div className="overflow-hidden h-2 text-xs flex rounded bg-gray-200">
          <div 
            style={{ width: `${(currentStep / steps.length) * 100}%` }}
            className="shadow-none flex flex-col text-center whitespace-nowrap text-white justify-center bg-blue-600 transition-all duration-500"
          />
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-full mb-4">
            <Sparkles className="w-5 h-5" />
            <span className="text-sm font-medium">Project orientation — indicative, not a verdict</span>
          </div>
          <h1 className="text-4xl font-bold text-gray-900 mb-2">
            Where does your green-fuel project stand today?
          </h1>
          <p className="text-lg text-gray-600">
            A first, directional read on eligibility, demand and financing — we show what’s known,
            what’s assumed, and what you’d need to prove.
          </p>
        </div>

        {/* Progress */}
        <ProgressBar />

        {/* Main Content Card */}
        <div className="bg-white rounded-2xl shadow-xl p-8">
          
          {/* STEP 1: Project Basics */}
          {currentStep === 1 && (
            <div>
              <h2 className="text-2xl font-bold text-gray-900 mb-2">Tell us about your project</h2>
              <p className="text-gray-600 mb-6">
                A few facts. Each one tells GEX something specific about eligibility, power and offtake —
                watch the notes appear as you fill them in.
              </p>

              <div className="space-y-6">
                {/* Molecule / pathway */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    What molecule / pathway are you producing?
                  </label>
                  <select
                    value={step1Data.molecule}
                    onChange={(e) => setStep1Data({ ...step1Data, molecule: e.target.value })}
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  >
                    {ENTRY_MOLECULES.map((molecule) => (
                      <option key={molecule} value={molecule}>{molecule}</option>
                    ))}
                  </select>
                </div>

                {/* Jurisdiction (controlled — sets the regime) + city */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Country <span className="text-gray-400 font-normal">— sets the regulatory regime</span>
                    </label>
                    <select
                      value={step1Data.country}
                      onChange={(e) => setStep1Data({ ...step1Data, country: e.target.value })}
                      className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                      required
                    >
                      <option value="">Select country…</option>
                      {JURISDICTIONS.map((g) => (
                        <optgroup key={g.group} label={g.group}>
                          {g.countries.map((c) => (
                            <option key={c} value={c}>{c}</option>
                          ))}
                        </optgroup>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Location (City) <span className="text-gray-400 font-normal">— optional</span>
                    </label>
                    <input
                      type="text"
                      value={step1Data.location}
                      onChange={(e) => setStep1Data({ ...step1Data, location: e.target.value })}
                      className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                      placeholder="e.g., Hamburg"
                    />
                  </div>
                </div>

                {/* Power basis + offtake status — the RFNBO / bankability gates */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Power basis <span className="text-gray-400 font-normal">— drives RFNBO status</span>
                    </label>
                    <select
                      value={step1Data.power_basis}
                      onChange={(e) => setStep1Data({ ...step1Data, power_basis: e.target.value })}
                      className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    >
                      <option value="">Select power basis…</option>
                      {POWER_BASIS_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Offtake status <span className="text-gray-400 font-normal">— the bankability anchor</span>
                    </label>
                    <select
                      value={step1Data.offtake_status}
                      onChange={(e) => setStep1Data({ ...step1Data, offtake_status: e.target.value })}
                      className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    >
                      <option value="">Select offtake status…</option>
                      {OFFTAKE_STATUS_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* Scale + timing */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Daily capacity <span className="text-gray-400 font-normal">— tonnes of product / day (MTPD)</span>
                    </label>
                    <input
                      type="number"
                      value={step1Data.capacity_mtpd}
                      onChange={(e) => setStep1Data({ ...step1Data, capacity_mtpd: e.target.value })}
                      className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                      placeholder="e.g., 50"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Target production start
                    </label>
                    <input
                      type="number"
                      value={step1Data.production_start_year}
                      onChange={(e) => setStep1Data({ ...step1Data, production_start_year: parseInt(e.target.value) })}
                      className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                      min="2025"
                      max="2040"
                    />
                  </div>
                </div>
              </div>

              {/* Live clues — what GEX reads from each answer (a window into the depth behind the doorway) */}
              {(() => {
                const clues = [
                  moleculeNote(step1Data.molecule),
                  jurisdictionNote(step1Data.country),
                  powerNote(step1Data.power_basis),
                  offtakeNote(step1Data.offtake_status),
                ].filter(Boolean);
                return clues.length ? (
                  <div className="mt-6 rounded-lg border border-blue-100 bg-blue-50/70 p-4">
                    <div className="flex items-center gap-2 text-blue-800 font-medium text-sm mb-2">
                      <Sparkles className="w-4 h-4" /> What GEX reads from this
                    </div>
                    <ul className="space-y-2 text-sm text-gray-700">
                      {clues.map((c, i) => (
                        <li key={i} className="flex gap-2">
                          <span className="text-blue-500 mt-0.5">•</span>
                          <span>{c}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null;
              })()}

              <p className="mt-4 text-xs text-gray-500 leading-relaxed">
                This is a first orientation, not a verdict — indicative only. Behind this doorway, GEX turns
                each answer into evidence-graded gates, a lender-readable capital-release model, and a full
                audit trail — nothing it can’t stand behind.
              </p>

              <button
                onClick={submitStep1}
                disabled={loading || !step1Data.capacity_mtpd || !step1Data.country}
                className="mt-6 w-full flex items-center justify-center gap-2 px-6 py-4 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed font-medium text-lg"
              >
                {loading ? 'Analysing…' : 'See your first read'}
                <ArrowRight className="w-5 h-5" />
              </button>
            </div>
          )}

          {/* STEP 2: Economics + Demand Result */}
          {currentStep === 2 && (
            <div>
              {/* Show demand result first */}
              {demandResult && (
                <div className="mb-8 p-6 bg-gradient-to-r from-green-50 to-emerald-50 border border-green-200 rounded-lg">
                  <div className="flex items-start gap-3">
                    <TrendingUp className="w-6 h-6 text-green-600 mt-1" />
                    <div className="flex-1">
                      <h3 className="text-lg font-bold text-green-900 mb-2">
                        Market Demand: {demandResult.market_demand.level.replace('_', ' ').toUpperCase()}
                      </h3>
                      <div className="grid grid-cols-3 gap-4 mb-3">
                        <div>
                          <div className="text-sm text-green-700">Active Buyers</div>
                          <div className="text-2xl font-bold text-green-900">
                            {demandResult.market_demand.active_buyers}
                          </div>
                        </div>
                        <div>
                          <div className="text-sm text-green-700">Market Price</div>
                          <div className="text-2xl font-bold text-green-900">
                            €{demandResult.market_demand.market_price_eur_kg.toFixed(2)}/kg
                          </div>
                        </div>
                        <div>
                          <div className="text-sm text-green-700">Trend</div>
                          <div className="text-2xl font-bold text-green-900 capitalize">
                            {demandResult.market_demand.trend}
                          </div>
                        </div>
                      </div>
                      <p className="text-sm text-green-800">
                        {demandResult.next_step_recommendation}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Your first read — eligibility / RFNBO power / offtake, from Step 1 answers */}
              {demandResult && (demandResult.eligibility || demandResult.power_basis || demandResult.offtake) && (
                <div className="mb-8 p-6 bg-slate-50 border border-slate-200 rounded-lg">
                  <div className="flex items-center gap-2 mb-4">
                    <Sparkles className="w-5 h-5 text-blue-600" />
                    <h3 className="text-lg font-bold text-slate-900">
                      Your first read <span className="text-sm font-normal text-slate-500">— indicative, from your Step 1 answers</span>
                    </h3>
                  </div>
                  <div className="space-y-4">
                    {demandResult.eligibility && (
                      <div className="flex items-start gap-3">
                        <Award className="w-5 h-5 text-blue-500 mt-0.5 flex-shrink-0" />
                        <div>
                          <div className="text-sm font-medium text-slate-800 flex flex-wrap items-center gap-2">
                            Eligibility · {demandResult.eligibility.jurisdiction}
                            {demandResult.eligibility.restricted_sector && (
                              <span className="text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-800">
                                restricted-sector{demandResult.eligibility.carve_out_available ? ' · Taxonomy carve-out' : ''}
                              </span>
                            )}
                          </div>
                          <div className="text-sm text-slate-600 mt-0.5">{demandResult.eligibility.note}</div>
                        </div>
                      </div>
                    )}
                    {demandResult.power_basis && demandResult.power_basis.value !== 'not_stated' && (
                      <div className="flex items-start gap-3">
                        <TrendingUp className="w-5 h-5 text-blue-500 mt-0.5 flex-shrink-0" />
                        <div>
                          <div className="text-sm font-medium text-slate-800 flex items-center gap-2">
                            RFNBO power
                            <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 capitalize">
                              {String(demandResult.power_basis.rfnbo_strength).replace('_', ' ')}
                            </span>
                          </div>
                          <div className="text-sm text-slate-600 mt-0.5">{demandResult.power_basis.note}</div>
                        </div>
                      </div>
                    )}
                    {demandResult.offtake && demandResult.offtake.value !== 'not_stated' && (
                      <div className="flex items-start gap-3">
                        <DollarSign className="w-5 h-5 text-blue-500 mt-0.5 flex-shrink-0" />
                        <div>
                          <div className="text-sm font-medium text-slate-800 flex items-center gap-2">
                            Offtake
                            <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 capitalize">
                              {String(demandResult.offtake.status).replace('_', ' ')}
                            </span>
                          </div>
                          <div className="text-sm text-slate-600 mt-0.5">{demandResult.offtake.note}</div>
                        </div>
                      </div>
                    )}
                  </div>
                  <p className="mt-4 text-xs text-slate-400">
                    Indicative only — GEX turns each of these into an evidence-graded gate as the project progresses.
                  </p>
                </div>
              )}

              <h2 className="text-2xl font-bold text-gray-900 mb-2">Project Economics</h2>
              <p className="text-gray-600 mb-6">We'll calculate your project's bankability</p>

              <div className="space-y-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Estimated Total CAPEX (€)
                  </label>
                  <input
                    type="number"
                    value={step2Data.estimated_capex_eur}
                    onChange={(e) => setStep2Data({...step2Data, estimated_capex_eur: e.target.value})}
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                    placeholder="e.g., 200000000"
                    required
                  />
                  <p className="text-sm text-gray-500 mt-1">
                    Example: €200M = 200000000
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Operating Cost (€/kg)
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      value={step2Data.estimated_opex_eur_kg}
                      onChange={(e) => setStep2Data({...step2Data, estimated_opex_eur_kg: e.target.value})}
                      className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                      placeholder="e.g., 2.50"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Target Sale Price (€/kg)
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      value={step2Data.target_offtake_price_eur_kg}
                      onChange={(e) => setStep2Data({...step2Data, target_offtake_price_eur_kg: e.target.value})}
                      className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                      placeholder="e.g., 6.00"
                      required
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Electricity Source
                    </label>
                    <select
                      value={step2Data.electricity_source}
                      onChange={(e) => setStep2Data({...step2Data, electricity_source: e.target.value})}
                      className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="renewable">Dedicated Renewable (Wind/Solar)</option>
                      <option value="grid">Grid Mix</option>
                      <option value="nuclear">Nuclear</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Feedstock Source
                    </label>
                    <select
                      value={step2Data.feedstock_source}
                      onChange={(e) => setStep2Data({...step2Data, feedstock_source: e.target.value})}
                      className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="water">Water (for electrolysis)</option>
                      <option value="biomass">Biomass</option>
                      <option value="waste">Waste/Residues</option>
                      <option value="co2">Captured CO2</option>
                    </select>
                  </div>
                </div>
              </div>

              <div className="flex gap-4 mt-8">
                <button
                  onClick={() => setCurrentStep(1)}
                  className="flex items-center gap-2 px-6 py-3 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  <ArrowLeft className="w-5 h-5" />
                  Back
                </button>
                <button
                  onClick={submitStep2}
                  disabled={loading || !step2Data.estimated_capex_eur || !step2Data.estimated_opex_eur_kg || !step2Data.target_offtake_price_eur_kg}
                  className="flex-1 flex items-center justify-center gap-2 px-6 py-4 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 font-medium text-lg"
                >
                  {loading ? 'Calculating Bankability...' : 'Check Bankability'}
                  <ArrowRight className="w-5 h-5" />
                </button>
              </div>
            </div>
          )}

          {/* STEP 3: Certification + Bankability Result */}
          {currentStep === 3 && (
            <div>
              {/* Show bankability result */}
              {bankabilityResult && (
                <div className="mb-8 p-6 bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg">
                  <div className="flex items-start gap-3">
                    <DollarSign className="w-6 h-6 text-blue-600 mt-1" />
                    <div className="flex-1">
                      <h3 className="text-lg font-bold text-blue-900 mb-2">
                        Bankability: {bankabilityResult.bankability.level.replace('_', ' ').toUpperCase()}
                      </h3>
                      <div className="grid grid-cols-3 gap-4 mb-3">
                        <div>
                          <div className="text-sm text-blue-700">DSCR</div>
                          <div className="text-2xl font-bold text-blue-900">
                            {bankabilityResult.financial_metrics.dscr.toFixed(2)}x
                          </div>
                        </div>
                        <div>
                          <div className="text-sm text-blue-700">Annual CFADS</div>
                          <div className="text-2xl font-bold text-blue-900">
                            €{(bankabilityResult.financial_metrics.annual_cfads / 1000000).toFixed(1)}M
                          </div>
                        </div>
                        <div>
                          <div className="text-sm text-blue-700">Structure</div>
                          <div className="text-sm font-bold text-blue-900">
                            {bankabilityResult.financing_structure.senior_debt}/
                            {bankabilityResult.financing_structure.junior_debt}/
                            {bankabilityResult.financing_structure.equity}
                          </div>
                        </div>
                      </div>
                      <p className="text-sm text-blue-800">
                        {bankabilityResult.next_step_recommendation}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              <h2 className="text-2xl font-bold text-gray-900 mb-2">Certification &amp; eligibility</h2>
              <p className="text-gray-600 mb-6">
                What your pathway would need to prove — indicative, not an eligibility ruling. Watch the notes as you go.
              </p>

              <div className="space-y-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Renewable Electricity (%)
                  </label>
                  <input
                    type="number"
                    min="0"
                    max="100"
                    value={step3Data.electricity_renewable_percentage}
                    onChange={(e) => setStep3Data({...step3Data, electricity_renewable_percentage: parseFloat(e.target.value)})}
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                  />
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={step3Data.electricity_renewable_percentage}
                    onChange={(e) => setStep3Data({...step3Data, electricity_renewable_percentage: parseFloat(e.target.value)})}
                    className="w-full mt-2"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Target GHG Intensity (kg CO2e/kg fuel)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={step3Data.ghg_intensity_target}
                    onChange={(e) => setStep3Data({...step3Data, ghg_intensity_target: parseFloat(e.target.value)})}
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                    placeholder="e.g., 0.45"
                  />
                  <p className="text-sm text-gray-500 mt-1">
                    Lower is better. RFNBO needs ~70% saving vs fossil (~28.2 gCO₂e/MJ); 45V pays by GHG tier.
                    GEX checks your LCA against the live Delegated Act.
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-3">
                    Target Certifications
                  </label>
                  <div className="space-y-2">
                    {['RED_III', '45V', 'RFNBO', 'CORSIA'].map((cert) => (
                      <label key={cert} className="flex items-center gap-3 p-3 border rounded-lg hover:bg-gray-50 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={step3Data.target_certifications.includes(cert)}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setStep3Data({
                                ...step3Data,
                                target_certifications: [...step3Data.target_certifications, cert]
                              });
                            } else {
                              setStep3Data({
                                ...step3Data,
                                target_certifications: step3Data.target_certifications.filter(c => c !== cert)
                              });
                            }
                          }}
                          className="w-5 h-5 text-blue-600"
                        />
                        <div className="flex-1">
                          <div className="font-medium">{cert}</div>
                          <div className="text-sm text-gray-500">
                            {cert === 'RED_III' && 'EU Renewable Energy Directive'}
                            {cert === '45V' && 'US Production Tax Credit (H2)'}
                            {cert === 'RFNBO' && 'EU Renewable Fuels Standard'}
                            {cert === 'CORSIA' && 'Aviation Carbon Offsetting'}
                          </div>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>
              </div>

              {/* Live clues — what GEX reads from your certification inputs */}
              {(() => {
                const clues = [
                  renewableNote(step3Data.electricity_renewable_percentage),
                  ghgNote(step3Data.ghg_intensity_target),
                  ...certsNotes(step3Data.target_certifications, step1Data.country),
                ].filter(Boolean);
                return clues.length ? (
                  <div className="mt-6 rounded-lg border border-blue-100 bg-blue-50/70 p-4">
                    <div className="flex items-center gap-2 text-blue-800 font-medium text-sm mb-2">
                      <Sparkles className="w-4 h-4" /> What GEX reads from this
                    </div>
                    <ul className="space-y-2 text-sm text-gray-700">
                      {clues.map((c, i) => (
                        <li key={i} className="flex gap-2">
                          <span className="text-blue-500 mt-0.5">•</span>
                          <span>{c}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null;
              })()}

              <p className="mt-4 text-xs text-gray-500 leading-relaxed">
                Indicative only — a first read of what your pathway would need to prove, not an eligibility ruling.
                GEX turns each of these into an evidence-graded certification gate, checked against the live rules.
              </p>

              <div className="flex gap-4 mt-6">
                <button
                  onClick={() => setCurrentStep(2)}
                  className="flex items-center gap-2 px-6 py-3 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  <ArrowLeft className="w-5 h-5" />
                  Back
                </button>
                <button
                  onClick={submitStep3}
                  disabled={loading || step3Data.target_certifications.length === 0}
                  className="flex-1 flex items-center justify-center gap-2 px-6 py-4 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 font-medium text-lg"
                >
                  {loading ? 'Building your report…' : 'See your indicative report'}
                  <ArrowRight className="w-5 h-5" />
                </button>
              </div>
            </div>
          )}

          {/* STEP 4: Final Report */}
          {currentStep === 4 && finalReport && (
            <div>
              {/* Lead with the decisive reads — eligibility / RFNBO power / offtake */}
              {(() => {
                const r = finalReport.readiness || finalReport.market_assessment || {};
                const elig = r.eligibility;
                const power = r.rfnbo_power || r.power_basis;
                const offtake = r.offtake;
                if (!elig && !power && !offtake) return null;
                // Coaching — every read carries a concrete next move, not just a verdict.
                const eligMove = elig && (
                  elig.restricted_sector
                    ? (elig.carve_out_available
                        ? 'Assemble the EU-Taxonomy alignment pack — substantial contribution + DNSH. GEX hands you the checklist and grades each item.'
                        : 'Confirm a Taxonomy route before any drawdown. GEX flags exactly which criterion is blocking and how to clear it.')
                    : 'You are clear on jurisdiction — keep it evidenced as RED III and the delegated acts move. GEX tracks that for you.'
                );
                const powerMove = power && power.value !== 'not_stated' && (
                  String(power.rfnbo_strength).includes('strong')
                    ? 'Lock your PPA / additionality evidence — it is your RFNBO backbone. GEX pins it to the certification gate.'
                    : 'Move toward a compliant PPA — additionality plus temporal & geographic correlation. GEX shows what qualifies before you sign.'
                );
                const offtakeMove = offtake && offtake.value !== 'not_stated' && (
                  offtake.status === 'binding'
                    ? 'Strong signal. GEX grades the buyer credit and the contract CPs so a lender can actually rely on it.'
                    : 'Firm this toward a binding offtake — the single biggest bankability lever. GEX tracks every CP to financial close.'
                );
                const Move = ({ text }: { text: any }) => (
                  <div className="text-sm text-blue-700 mt-1.5 flex items-start gap-1.5">
                    <ArrowRight className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                    <span><span className="font-semibold">Your next move:</span> {text}</span>
                  </div>
                );
                return (
                  <div className="mb-6 p-6 bg-slate-50 border border-slate-200 rounded-2xl">
                    <div className="flex items-center gap-2 mb-1">
                      <Sparkles className="w-5 h-5 text-blue-600" />
                      <h3 className="text-lg font-bold text-slate-900">Where you stand — and your next moves</h3>
                    </div>
                    <p className="text-sm text-slate-500 mb-4">
                      Eligibility, RFNBO power and offtake are what decide viability. Here's your read on each — and the one move that advances it. GEX turns every one into an evidence-graded gate.
                    </p>
                    <div className="space-y-4">
                      {elig && (
                        <div className="flex items-start gap-3">
                          <Award className="w-5 h-5 text-blue-500 mt-0.5 flex-shrink-0" />
                          <div>
                            <div className="text-sm font-medium text-slate-800 flex flex-wrap items-center gap-2">
                              Eligibility · {elig.jurisdiction}
                              {elig.restricted_sector && (
                                <span className="text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-800">
                                  restricted-sector{elig.carve_out_available ? ' · Taxonomy carve-out' : ''}
                                </span>
                              )}
                            </div>
                            <div className="text-sm text-slate-600 mt-0.5">{elig.note}</div>
                            {eligMove && <Move text={eligMove} />}
                          </div>
                        </div>
                      )}
                      {power && power.value !== 'not_stated' && (
                        <div className="flex items-start gap-3">
                          <TrendingUp className="w-5 h-5 text-blue-500 mt-0.5 flex-shrink-0" />
                          <div>
                            <div className="text-sm font-medium text-slate-800 flex items-center gap-2">
                              RFNBO power
                              <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 capitalize">
                                {String(power.rfnbo_strength).replace('_', ' ')}
                              </span>
                            </div>
                            <div className="text-sm text-slate-600 mt-0.5">{power.note}</div>
                            {powerMove && <Move text={powerMove} />}
                          </div>
                        </div>
                      )}
                      {offtake && offtake.value !== 'not_stated' && (
                        <div className="flex items-start gap-3">
                          <DollarSign className="w-5 h-5 text-blue-500 mt-0.5 flex-shrink-0" />
                          <div>
                            <div className="text-sm font-medium text-slate-800 flex items-center gap-2">
                              Offtake
                              <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 capitalize">
                                {String(offtake.status).replace('_', ' ')}
                              </span>
                            </div>
                            <div className="text-sm text-slate-600 mt-0.5">{offtake.note}</div>
                            {offtakeMove && <Move text={offtakeMove} />}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })()}

              {/* Indicative orientation score — demoted, honest (not a verdict) */}
              <div className="mb-8 p-5 bg-white border border-gray-200 rounded-2xl flex items-center gap-6">
                <div className="text-center flex-shrink-0">
                  <div className="text-4xl font-bold text-slate-800">
                    {finalReport.viability_score}<span className="text-xl text-slate-400">/100</span>
                  </div>
                  <div className="text-xs text-slate-500 capitalize">
                    {finalReport.viability_level.replace(/_/g, ' ')}
                  </div>
                </div>
                <div className="flex-1">
                  <div className="text-xs uppercase tracking-wide text-slate-400 mb-1">
                    Orientation signal · a light directional read — not GEX's internal grade
                  </div>
                  <p className="text-slate-700 text-sm">{finalReport.recommendation}</p>
                  <p className="text-xs text-slate-400 mt-1.5">
                    Inside, GEX doesn't score you — it grades the evidence behind every gate, and follows each to financial close.
                  </p>
                </div>
              </div>

              {/* Certification Results */}
              {certificationResult && certificationResult.eligible_certifications.length > 0 && (
                <div className="mb-6 p-6 bg-green-50 border border-green-200 rounded-lg">
                  <h3 className="text-lg font-bold text-green-900 mb-4 flex items-center gap-2">
                    <CheckCircle className="w-5 h-5" />
                    Eligible Certifications ({certificationResult.eligible_certifications.length})
                  </h3>
                  <div className="space-y-3">
                    {certificationResult.eligible_certifications.map((cert: any, i: number) => (
                      <div key={i} className="flex justify-between items-center p-3 bg-white rounded border border-green-200">
                        <div>
                          <div className="font-medium text-gray-900">{cert.name}</div>
                          <div className="text-sm text-gray-600">
                            €{(cert.annual_value / 1000000).toFixed(1)}M annually
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="text-lg font-bold text-green-600">
                            €{cert.subsidy_value_eur_kg.toFixed(2)}/kg
                          </div>
                          {cert.tier && <div className="text-sm text-gray-600">{cert.tier}</div>}
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-4 pt-4 border-t border-green-200">
                    <div className="flex justify-between items-center">
                      <span className="font-medium text-green-900">Total Annual Subsidy Value:</span>
                      <span className="text-2xl font-bold text-green-600">
                        €{(certificationResult.total_annual_subsidy / 1000000).toFixed(1)}M
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {/* Ineligible Certifications */}
              {certificationResult && certificationResult.ineligible_certifications.length > 0 && (
                <div className="mb-6 p-6 bg-yellow-50 border border-yellow-200 rounded-lg">
                  <h3 className="text-lg font-bold text-yellow-900 mb-4 flex items-center gap-2">
                    <AlertCircle className="w-5 h-5" />
                    Optimization Opportunities
                  </h3>
                  {certificationResult.ineligible_certifications.map((cert: any, i: number) => (
                    <div key={i} className="mb-3 last:mb-0">
                      <div className="font-medium text-gray-900 mb-2">{cert.name}</div>
                      <ul className="text-sm text-gray-700 space-y-1">
                        {cert.how_to_qualify.map((req: string, j: number) => (
                          <li key={j} className="flex items-start gap-2">
                            <span className="text-yellow-600">→</span>
                            <span>{req}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              )}

              {/* Next Steps */}
              <div className="mb-6">
                <h3 className="text-lg font-bold text-gray-900 mb-4">Your next moves</h3>
                <div className="space-y-3">
                  {finalReport.next_steps.map((step: any, i: number) => (
                    <div key={i} className={`p-4 rounded-lg border ${
                      step.priority === 'high' 
                        ? 'bg-red-50 border-red-200' 
                        : 'bg-blue-50 border-blue-200'
                    }`}>
                      <div className="flex items-start gap-3">
                        <div className={`px-2 py-1 rounded text-xs font-medium ${
                          step.priority === 'high' 
                            ? 'bg-red-600 text-white' 
                            : 'bg-blue-600 text-white'
                        }`}>
                          {step.priority.toUpperCase()}
                        </div>
                        <div className="flex-1">
                          <div className="font-medium text-gray-900">{step.action}</div>
                          <div className="text-sm text-gray-600 mt-1">{step.benefit}</div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* What GEX does next — the enticement */}
              <div
                className="mb-6 p-6 rounded-2xl text-white"
                style={{ background: 'linear-gradient(135deg, #005c9e 0%, #0a3d62 100%)' }}
              >
                <h3 className="text-lg font-bold mb-1">This orientation is the doorway — here's what happens inside GEX</h3>
                <p className="text-sm text-blue-100 mb-4">
                  Everything above was a read from four answers. GEX takes the same project and carries it, evidenced, all the way to the money.
                </p>
                <div className="grid gap-3 sm:grid-cols-3 mb-5">
                  <div className="flex items-start gap-2">
                    <CheckCircle className="w-5 h-5 text-emerald-300 mt-0.5 flex-shrink-0" />
                    <div>
                      <div className="text-sm font-semibold">Every claim becomes evidence</div>
                      <div className="text-xs text-blue-100">Each read above turns into an evidence-graded gate, tracked from today to financial close.</div>
                    </div>
                  </div>
                  <div className="flex items-start gap-2">
                    <TrendingUp className="w-5 h-5 text-emerald-300 mt-0.5 flex-shrink-0" />
                    <div>
                      <div className="text-sm font-semibold">Protect your cheapest capital</div>
                      <div className="text-xs text-blue-100">Clear eligibility and Taxonomy early so concessional and DFI money stays on the table.</div>
                    </div>
                  </div>
                  <div className="flex items-start gap-2">
                    <FileText className="w-5 h-5 text-emerald-300 mt-0.5 flex-shrink-0" />
                    <div>
                      <div className="text-sm font-semibold">A lender-readable pack</div>
                      <div className="text-xs text-blue-100">Not a data room — the story lenders and DFIs sign against, cutting weeks off diligence.</div>
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => window.location.href = '/projects/new'}
                  className="inline-flex items-center gap-2 px-6 py-3 bg-white text-[#005c9e] rounded-lg hover:bg-blue-50 font-semibold"
                >
                  Build your project on GEX
                  <ArrowRight className="w-5 h-5" />
                </button>
              </div>

              {/* Contact Form */}
              <div className="mb-6 p-6 bg-gray-50 border border-gray-200 rounded-lg">
                <h3 className="text-lg font-bold text-gray-900 mb-4">Save Your Report</h3>
                <div className="flex gap-4">
                  <input
                    type="email"
                    value={contactEmail}
                    onChange={(e) => setContactEmail(e.target.value)}
                    placeholder="your.email@company.com"
                    className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                  />
                  <button
                    className="px-6 py-3 bg-gray-800 text-white rounded-lg hover:bg-gray-900 font-medium"
                  >
                    Email Report
                  </button>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="grid grid-cols-2 gap-4">
                <button
                  onClick={() => window.print()}
                  className="flex items-center justify-center gap-2 px-6 py-4 border-2 border-blue-600 text-blue-600 rounded-lg hover:bg-blue-50 font-medium"
                >
                  <Download className="w-5 h-5" />
                  Download PDF
                </button>
                <button
                  onClick={() => window.location.href = '/producer/dashboard'}
                  className="flex items-center justify-center gap-2 px-6 py-4 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium"
                >
                  <FileText className="w-5 h-5" />
                  Create Full Project Profile
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Footer Help */}
        <div className="text-center mt-8 text-gray-600">
          <p className="text-sm">
            Questions? <a href="mailto:support@greenearth.com" className="text-blue-600 hover:underline">Contact our team</a>
          </p>
        </div>
      </div>
    </div>
  );
};

export default OnboardingWizard;
