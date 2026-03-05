import React, { useState } from 'react';
import { 
  CheckCircle, AlertCircle, TrendingUp, DollarSign, Award, 
  FileText, ArrowRight, ArrowLeft, Download, Sparkles 
} from 'lucide-react';

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

const OnboardingWizard: React.FC = () => {
  const [currentStep, setCurrentStep] = useState(1);
  const [loading, setLoading] = useState(false);
  
  // Form data
  const [step1Data, setStep1Data] = useState({
    molecule: 'H2',
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
  
  // Results from each step
  const [demandResult, setDemandResult] = useState<any>(null);
  const [bankabilityResult, setBankabilityResult] = useState<any>(null);
  const [certificationResult, setCertificationResult] = useState<any>(null);
  const [finalReport, setFinalReport] = useState<any>(null);

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
                    <option value="H2">H2 - Hydrogen</option>
                    <option value="NH3">NH3 - Ammonia</option>
                    <option value="SAF">SAF - Sustainable Aviation Fuel</option>
                    <option value="CH3OH">CH3OH - Methanol</option>
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
