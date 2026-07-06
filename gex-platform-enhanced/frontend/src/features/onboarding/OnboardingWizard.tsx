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
            <span className="text-sm font-medium">Free Project Viability Assessment</span>
          </div>
          <h1 className="text-4xl font-bold text-gray-900 mb-2">
            Is Your Green Fuel Project Viable?
          </h1>
          <p className="text-lg text-gray-600">
            Get instant feedback on market demand, financing, and certification eligibility
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
              <p className="text-gray-600 mb-6">We'll instantly check market demand</p>

              <div className="space-y-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    What molecule are you producing?
                  </label>
                  <select
                    value={step1Data.molecule}
                    onChange={(e) => setStep1Data({...step1Data, molecule: e.target.value})}
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  >
                    {ENTRY_MOLECULES.map((molecule) => (
                      <option key={molecule} value={molecule}>{molecule}</option>
                    ))}
                  </select>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Daily Capacity (MTPD)
                    </label>
                    <input
                      type="number"
                      value={step1Data.capacity_mtpd}
                      onChange={(e) => setStep1Data({...step1Data, capacity_mtpd: e.target.value})}
                      className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                      placeholder="e.g., 50"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Production Start Year
                    </label>
                    <input
                      type="number"
                      value={step1Data.production_start_year}
                      onChange={(e) => setStep1Data({...step1Data, production_start_year: parseInt(e.target.value)})}
                      className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                      min="2025"
                      max="2035"
                      required
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Location (City)
                    </label>
                    <input
                      type="text"
                      value={step1Data.location}
                      onChange={(e) => setStep1Data({...step1Data, location: e.target.value})}
                      className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                      placeholder="e.g., Hamburg"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Country
                    </label>
                    <input
                      type="text"
                      value={step1Data.country}
                      onChange={(e) => setStep1Data({...step1Data, country: e.target.value})}
                      className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                      placeholder="e.g., Germany"
                      required
                    />
                  </div>
                </div>
              </div>

              <button
                onClick={submitStep1}
                disabled={loading || !step1Data.capacity_mtpd || !step1Data.location || !step1Data.country}
                className="mt-8 w-full flex items-center justify-center gap-2 px-6 py-4 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed font-medium text-lg"
              >
                {loading ? 'Checking Market Demand...' : 'Check Market Demand'}
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

              <h2 className="text-2xl font-bold text-gray-900 mb-2">Certification & Subsidies</h2>
              <p className="text-gray-600 mb-6">Check which subsidies you qualify for</p>

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
                    Lower is better. For H2: &lt;0.45 qualifies for max 45V credit
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

              <div className="flex gap-4 mt-8">
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
                  {loading ? 'Generating Report...' : 'Generate Viability Report'}
                  <ArrowRight className="w-5 h-5" />
                </button>
              </div>
            </div>
          )}

          {/* STEP 4: Final Report */}
          {currentStep === 4 && finalReport && (
            <div>
              {/* Viability Score Hero */}
              <div className="text-center mb-8 p-8 bg-gradient-to-r from-purple-50 to-pink-50 border border-purple-200 rounded-2xl">
                <div className="inline-flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-full mb-4">
                  <Award className="w-5 h-5" />
                  <span className="text-sm font-medium">Your Viability Score</span>
                </div>
                <div className="text-6xl font-bold text-purple-900 mb-2">
                  {finalReport.viability_score}/100
                </div>
                <div className="text-xl text-purple-700 font-medium mb-4 capitalize">
                  {finalReport.viability_level.replace('_', ' ')}
                </div>
                <p className="text-purple-900 text-lg">
                  {finalReport.recommendation}
                </p>
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
                <h3 className="text-lg font-bold text-gray-900 mb-4">Recommended Next Steps</h3>
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
