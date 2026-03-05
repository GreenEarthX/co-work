import React, { useState, useEffect } from 'react';
import { CheckCircle, AlertTriangle, DollarSign, Shield, FileCheck, TrendingUp, Lock, Unlock } from 'lucide-react';

interface CapitalType {
  type: string;
  name: string;
  amount: string;
  is_unlocked: boolean;
  gating_gates: string[];
  progress_pct: number;
}

interface FinanceGate {
  id: string;
  name: string;
  total_evidence: number;
  verified_count: number;
  completion_pct: number;
  is_complete: boolean;
  blocking_items: string[];
  icon: string;
  description: string;
}

interface FinanceBankabilityView {
  project_id: string;
  visible_gates: FinanceGate[];
  capital_status: CapitalType[];
  overall_completion: number;
  total_unlocked_amount: string;
  next_unlock_milestone: string;
  risk_alerts: string[];
}

export function FinanceBankabilityView({ projectId }: { projectId: string }) {
  const [bankabilityData, setBankabilityData] = useState<FinanceBankabilityView | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedCapital, setSelectedCapital] = useState<CapitalType | null>(null);

  useEffect(() => {
    loadBankabilityData();
  }, [projectId]);

  const loadBankabilityData = async () => {
    setLoading(true);
    try {
      const response = await fetch(`/api/v1/bankability/projects/${projectId}/bankability/FINANCE`);
      if (response.ok) {
        const data = await response.json();
        setBankabilityData(data);
      } else {
        // Demo data for finance persona
        setBankabilityData({
          project_id: projectId,
          visible_gates: [
            {
              id: 'G4_OFFTAKE_BANKABLE',
              name: 'Bankable Off-take Secured',
              total_evidence: 6,
              verified_count: 5,
              completion_pct: 83,
              is_complete: false,
              blocking_items: ['offtake_contract_10_year_term'],
              icon: '📋',
              description: 'Long-term take-or-pay contracts with investment-grade counterparties'
            },
            {
              id: 'G7_INSURANCE_BOUND',
              name: 'Insurance Coverage Bound',
              total_evidence: 4,
              verified_count: 3,
              completion_pct: 75,
              is_complete: false,
              blocking_items: ['political_risk_insurance'],
              icon: '🛡️',
              description: 'Comprehensive insurance coverage for construction and operational phases'
            },
            {
              id: 'G8_AUDIT_GRADE_MODEL',
              name: 'Audit-Grade Financial Model',
              total_evidence: 5,
              verified_count: 4,
              completion_pct: 80,
              is_complete: false,
              blocking_items: ['stress_test_certification'],
              icon: '📊',
              description: 'Third-party verified financial model with stress testing'
            },
            {
              id: 'G10_FINANCIAL_CLOSE_CP',
              name: 'Financial Close Ready',
              total_evidence: 8,
              verified_count: 2,
              completion_pct: 25,
              is_complete: false,
              blocking_items: ['senior_debt_commitment', 'equity_funding_confirmed'],
              icon: '💰',
              description: 'All funding commitments and legal documentation ready'
            }
          ],
          capital_status: [
            {
              type: 'PROJECT_EQUITY',
              name: 'Project Equity',
              amount: '€42M',
              is_unlocked: false,
              gating_gates: ['G4_OFFTAKE_BANKABLE', 'G7_INSURANCE_BOUND'],
              progress_pct: 79
            },
            {
              type: 'SENIOR_DEBT_COMMITMENT',
              name: 'Senior Debt',
              amount: '€98M',
              is_unlocked: false,
              gating_gates: ['G8_AUDIT_GRADE_MODEL', 'G10_FINANCIAL_CLOSE_CP'],
              progress_pct: 53
            },
            {
              type: 'DFI_MEZZ_GUARANTEES',
              name: 'DFI Guarantees',
              amount: '€25M',
              is_unlocked: true,
              gating_gates: ['G4_OFFTAKE_BANKABLE'],
              progress_pct: 100
            },
            {
              type: 'DEBT_DRAWDOWN',
              name: 'Debt Drawdown',
              amount: '€98M',
              is_unlocked: false,
              gating_gates: ['G10_FINANCIAL_CLOSE_CP'],
              progress_pct: 25
            }
          ],
          overall_completion: 66,
          total_unlocked_amount: '€25M',
          next_unlock_milestone: 'Complete G4 + G7 for €42M Project Equity',
          risk_alerts: [
            'Take-or-pay contract needs 10-year term extension',
            'Political risk insurance pending government approval'
          ]
        });
      }
    } catch (error) {
      console.error('Failed to load bankability data:', error);
    }
    setLoading(false);
  };

  const getGateIcon = (iconStr: string) => {
    const iconMap: { [key: string]: React.ReactNode } = {
      '📋': <FileCheck className="w-6 h-6" />,
      '🛡️': <Shield className="w-6 h-6" />,
      '📊': <TrendingUp className="w-6 h-6" />,
      '💰': <DollarSign className="w-6 h-6" />
    };
    return iconMap[iconStr] || <FileCheck className="w-6 h-6" />;
  };

  const getCapitalIcon = (type: string) => {
    if (type.includes('EQUITY')) return <TrendingUp className="w-5 h-5" />;
    if (type.includes('DEBT')) return <DollarSign className="w-5 h-5" />;
    if (type.includes('GUARANTEE')) return <Shield className="w-5 h-5" />;
    return <FileCheck className="w-5 h-5" />;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (!bankabilityData) {
    return (
      <div className="text-center py-12">
        <div className="text-gray-400 text-4xl mb-2">💼</div>
        <p className="text-gray-600">No finance bankability data available</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header with Financial Progress */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-xl font-bold text-gray-900">Financial Milestone Progress</h2>
            <p className="text-sm text-gray-600">Finance team evidence requirements</p>
          </div>
          <div className="text-right">
            <div className="text-3xl font-black text-green-600">{bankabilityData.total_unlocked_amount}</div>
            <div className="text-sm text-gray-500">Unlocked Capital</div>
          </div>
        </div>

        {/* Progress Summary */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div className="text-center">
            <div className="text-2xl font-bold text-blue-600">{bankabilityData.overall_completion}%</div>
            <div className="text-sm text-gray-600">Gates Complete</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-green-600">
              {bankabilityData.capital_status.filter(c => c.is_unlocked).length}
            </div>
            <div className="text-sm text-gray-600">Capital Types Unlocked</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-orange-600">{bankabilityData.risk_alerts.length}</div>
            <div className="text-sm text-gray-600">Risk Alerts</div>
          </div>
        </div>

        {/* Risk Alerts */}
        {bankabilityData.risk_alerts.length > 0 && (
          <div className="bg-orange-50 border border-orange-200 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="w-4 h-4 text-orange-600" />
              <span className="font-medium text-orange-800">Risk Alerts</span>
            </div>
            <ul className="space-y-1">
              {bankabilityData.risk_alerts.map((alert, index) => (
                <li key={index} className="text-sm text-orange-700">• {alert}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Next Milestone */}
        <div className="mt-4 p-4 bg-blue-50 rounded-lg">
          <div className="font-medium text-blue-900">Next Milestone:</div>
          <div className="text-sm text-blue-700">{bankabilityData.next_unlock_milestone}</div>
        </div>
      </div>

      {/* Capital Status Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-gray-200">
          <div className="p-6 border-b border-gray-200">
            <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2">
              <DollarSign className="w-5 h-5 text-green-600" />
              Capital Unlock Status
            </h3>
          </div>
          <div className="p-6 space-y-4">
            {bankabilityData.capital_status.map(capital => (
              <div 
                key={capital.type}
                className={`p-4 rounded-lg border-2 cursor-pointer transition-all hover:shadow-md ${
                  capital.is_unlocked 
                    ? 'border-green-200 bg-green-50' 
                    : 'border-gray-200 bg-white'
                }`}
                onClick={() => setSelectedCapital(capital)}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    {getCapitalIcon(capital.type)}
                    <div>
                      <div className="font-medium text-gray-900">{capital.name}</div>
                      <div className="text-lg font-bold text-green-600">{capital.amount}</div>
                    </div>
                  </div>
                  {capital.is_unlocked ? (
                    <Unlock className="w-6 h-6 text-green-600" />
                  ) : (
                    <Lock className="w-6 h-6 text-gray-400" />
                  )}
                </div>
                
                <div className="bg-gray-200 rounded-full h-2">
                  <div 
                    className={`h-2 rounded-full transition-all duration-500 ${
                      capital.is_unlocked ? 'bg-green-600' : 'bg-blue-500'
                    }`}
                    style={{ width: `${capital.progress_pct}%` }}
                  ></div>
                </div>
                <div className="text-xs text-gray-600 mt-1">{capital.progress_pct}% ready</div>
              </div>
            ))}
          </div>
        </div>

        {/* Finance Gates */}
        <div className="bg-white rounded-xl border border-gray-200">
          <div className="p-6 border-b border-gray-200">
            <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2">
              <FileCheck className="w-5 h-5 text-blue-600" />
              Financial Gates
            </h3>
          </div>
          <div className="p-6 space-y-4">
            {bankabilityData.visible_gates.map(gate => (
              <div 
                key={gate.id}
                className={`p-4 rounded-lg border-2 transition-all ${
                  gate.is_complete 
                    ? 'border-green-200 bg-green-50' 
                    : gate.completion_pct >= 75 
                    ? 'border-yellow-200 bg-yellow-50'
                    : 'border-gray-200 bg-white'
                }`}
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
                      {getGateIcon(gate.icon)}
                    </div>
                    <div className="flex-1">
                      <div className="font-medium text-gray-900">{gate.name}</div>
                      <div className="text-sm text-gray-600">{gate.description}</div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-bold text-gray-900">{gate.completion_pct}%</div>
                    {gate.is_complete ? (
                      <CheckCircle className="w-5 h-5 text-green-600 mt-1" />
                    ) : (
                      <div className="text-xs text-gray-500">{gate.verified_count}/{gate.total_evidence}</div>
                    )}
                  </div>
                </div>

                <div className="bg-gray-200 rounded-full h-1.5 mb-2">
                  <div 
                    className={`h-1.5 rounded-full transition-all duration-500 ${
                      gate.is_complete ? 'bg-green-600' : 'bg-blue-500'
                    }`}
                    style={{ width: `${gate.completion_pct}%` }}
                  ></div>
                </div>

                {gate.blocking_items.length > 0 && (
                  <div className="text-xs text-red-600">
                    Blocking: {gate.blocking_items.join(', ').replace(/_/g, ' ')}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Capital Detail Modal */}
      {selectedCapital && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl max-w-lg w-full">
            <div className="p-6 border-b border-gray-200">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  {getCapitalIcon(selectedCapital.type)}
                  <div>
                    <h2 className="text-xl font-bold text-gray-900">{selectedCapital.name}</h2>
                    <p className="text-2xl font-bold text-green-600">{selectedCapital.amount}</p>
                  </div>
                </div>
                <button 
                  onClick={() => setSelectedCapital(null)}
                  className="text-gray-400 hover:text-gray-600"
                >
                  ✕
                </button>
              </div>
            </div>
            
            <div className="p-6">
              <div className="mb-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-gray-700">Progress</span>
                  <span className="text-sm font-medium text-gray-900">{selectedCapital.progress_pct}%</span>
                </div>
                <div className="bg-gray-200 rounded-full h-2">
                  <div 
                    className={`h-2 rounded-full ${selectedCapital.is_unlocked ? 'bg-green-600' : 'bg-blue-500'}`}
                    style={{ width: `${selectedCapital.progress_pct}%` }}
                  ></div>
                </div>
              </div>

              <div className="mb-4">
                <p className="text-sm font-medium text-gray-700 mb-2">Required Gates:</p>
                <div className="space-y-1">
                  {selectedCapital.gating_gates.map(gateId => {
                    const gate = bankabilityData.visible_gates.find(g => g.id === gateId);
                    return (
                      <div key={gateId} className="flex items-center justify-between text-sm">
                        <span className="text-gray-600">{gate?.name || gateId}</span>
                        <span className={`font-medium ${gate?.is_complete ? 'text-green-600' : 'text-orange-600'}`}>
                          {gate?.completion_pct || 0}%
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>

              <button 
                onClick={() => setSelectedCapital(null)}
                className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}