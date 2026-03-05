import React, { useState, useEffect } from 'react';
import { CheckCircle, AlertCircle, Clock, Upload, Eye, FileText } from 'lucide-react';

interface EvidenceItem {
  key: string;
  status: 'NOT_STARTED' | 'IN_PROGRESS' | 'SUBMITTED' | 'UNDER_REVIEW' | 'VERIFIED' | 'REJECTED' | 'EXPIRED';
  submitted_by?: string;
  verified_by?: string;
  submitted_at?: string;
  verified_at?: string;
  document_url?: string;
  notes?: string;
}

interface Gate {
  id: string;
  name: string;
  total_evidence: number;
  verified_count: number;
  completion_pct: number;
  is_complete: boolean;
  blocking_items: string[];
  evidence_items: EvidenceItem[];
}

interface ProducerBankabilityView {
  project_id: string;
  visible_gates: Gate[];
  overall_completion: number;
  unlocked_capital: string[];
  next_milestone: string;
}

export function ProducerBankabilityView({ projectId }: { projectId: string }) {
  const [bankabilityData, setBankabilityData] = useState<ProducerBankabilityView | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedGate, setSelectedGate] = useState<Gate | null>(null);

  useEffect(() => {
    loadBankabilityData();
  }, [projectId]);

  const loadBankabilityData = async () => {
    setLoading(true);
    try {
      const response = await fetch(`/api/v1/bankability/projects/${projectId}/bankability/PRODUCER`);
      if (response.ok) {
        const data = await response.json();
        setBankabilityData(data);
      } else {
        // Fallback to demo data for now
        setBankabilityData({
          project_id: projectId,
          visible_gates: [
            {
              id: 'G0_SITE_RIGHTS',
              name: 'Site Rights Secured',
              total_evidence: 4,
              verified_count: 3,
              completion_pct: 75,
              is_complete: false,
              blocking_items: ['environmental_impact_assessment'],
              evidence_items: [
                { key: 'land_option_executed', status: 'VERIFIED' },
                { key: 'zoning_clearance', status: 'VERIFIED' },
                { key: 'title_search', status: 'VERIFIED' },
                { key: 'environmental_impact_assessment', status: 'IN_PROGRESS' }
              ]
            },
            {
              id: 'G1_GRID_UTILITIES_REALITY',
              name: 'Grid Connection Secured',
              total_evidence: 3,
              verified_count: 2,
              completion_pct: 67,
              is_complete: false,
              blocking_items: ['grid_connection_agreement'],
              evidence_items: [
                { key: 'grid_capacity_study', status: 'VERIFIED' },
                { key: 'utility_interconnection_approved', status: 'VERIFIED' },
                { key: 'grid_connection_agreement', status: 'SUBMITTED' }
              ]
            },
            {
              id: 'G5_EPC_RISK_PRICED',
              name: 'EPC Risk Assessed',
              total_evidence: 5,
              verified_count: 4,
              completion_pct: 80,
              is_complete: false,
              blocking_items: ['performance_guarantees'],
              evidence_items: [
                { key: 'epc_contract_executed', status: 'VERIFIED' },
                { key: 'fixed_price_guarantee', status: 'VERIFIED' },
                { key: 'completion_guarantees', status: 'VERIFIED' },
                { key: 'technology_warranties', status: 'VERIFIED' },
                { key: 'performance_guarantees', status: 'UNDER_REVIEW' }
              ]
            }
          ],
          overall_completion: 74,
          unlocked_capital: ['GRANTS_TA', 'SEED_VC_ANGEL'],
          next_milestone: 'Complete G0 for Strategic Equity unlock'
        });
      }
    } catch (error) {
      console.error('Failed to load bankability data:', error);
    }
    setLoading(false);
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'VERIFIED':
        return <CheckCircle className="w-4 h-4 text-green-600" />;
      case 'SUBMITTED':
      case 'UNDER_REVIEW':
        return <Clock className="w-4 h-4 text-yellow-600" />;
      case 'REJECTED':
      case 'EXPIRED':
        return <AlertCircle className="w-4 h-4 text-red-600" />;
      default:
        return <Clock className="w-4 h-4 text-gray-400" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'VERIFIED':
        return 'text-green-700 bg-green-50';
      case 'SUBMITTED':
      case 'UNDER_REVIEW':
        return 'text-yellow-700 bg-yellow-50';
      case 'REJECTED':
      case 'EXPIRED':
        return 'text-red-700 bg-red-50';
      default:
        return 'text-gray-600 bg-gray-50';
    }
  };

  const getGateColor = (gate: Gate) => {
    if (gate.is_complete) return 'border-green-200 bg-green-50';
    if (gate.completion_pct >= 75) return 'border-yellow-200 bg-yellow-50';
    return 'border-gray-200 bg-white';
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
        <div className="text-gray-400 text-4xl mb-2">📋</div>
        <p className="text-gray-600">No bankability data available</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header with Overall Progress */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-xl font-bold text-gray-900">Project Bankability Progress</h2>
            <p className="text-sm text-gray-600">Producer evidence requirements</p>
          </div>
          <div className="text-right">
            <div className="text-3xl font-black text-blue-600">{bankabilityData.overall_completion}%</div>
            <div className="text-sm text-gray-500">Overall Complete</div>
          </div>
        </div>
        
        <div className="bg-gray-200 rounded-full h-2 mb-4">
          <div 
            className="bg-blue-600 h-2 rounded-full transition-all duration-500"
            style={{ width: `${bankabilityData.overall_completion}%` }}
          ></div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <p className="text-sm text-gray-600">Unlocked Capital:</p>
            <div className="flex flex-wrap gap-2 mt-1">
              {bankabilityData.unlocked_capital.map(capital => (
                <span key={capital} className="px-2 py-1 bg-green-100 text-green-700 rounded text-xs font-medium">
                  {capital.replace(/_/g, ' ')}
                </span>
              ))}
            </div>
          </div>
          <div>
            <p className="text-sm text-gray-600">Next Milestone:</p>
            <p className="text-sm font-medium text-gray-900 mt-1">{bankabilityData.next_milestone}</p>
          </div>
        </div>
      </div>

      {/* Gates Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {bankabilityData.visible_gates.map(gate => (
          <div 
            key={gate.id} 
            className={`rounded-xl border-2 p-6 cursor-pointer transition-all hover:shadow-lg ${getGateColor(gate)}`}
            onClick={() => setSelectedGate(gate)}
          >
            <div className="flex items-start justify-between mb-4">
              <div className="flex-1">
                <h3 className="font-bold text-gray-900 mb-1">{gate.name}</h3>
                <p className="text-sm text-gray-600">
                  {gate.verified_count} of {gate.total_evidence} evidence items verified
                </p>
              </div>
              <div className="text-right">
                <div className="text-lg font-bold text-gray-900">{gate.completion_pct}%</div>
                {gate.is_complete ? (
                  <CheckCircle className="w-6 h-6 text-green-600 mt-1" />
                ) : (
                  <Clock className="w-6 h-6 text-yellow-600 mt-1" />
                )}
              </div>
            </div>

            <div className="bg-gray-200 rounded-full h-1.5 mb-4">
              <div 
                className={`h-1.5 rounded-full transition-all duration-500 ${
                  gate.is_complete ? 'bg-green-600' : 'bg-yellow-500'
                }`}
                style={{ width: `${gate.completion_pct}%` }}
              ></div>
            </div>

            {gate.blocking_items.length > 0 && (
              <div className="flex items-center gap-2 text-sm text-red-600">
                <AlertCircle className="w-4 h-4" />
                <span>{gate.blocking_items.length} item(s) blocking</span>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Gate Detail Modal */}
      {selectedGate && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b border-gray-200">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-bold text-gray-900">{selectedGate.name}</h2>
                  <p className="text-sm text-gray-600">{selectedGate.id}</p>
                </div>
                <button 
                  onClick={() => setSelectedGate(null)}
                  className="text-gray-400 hover:text-gray-600"
                >
                  ✕
                </button>
              </div>
            </div>
            
            <div className="p-6">
              <div className="space-y-4">
                {selectedGate.evidence_items.map(evidence => (
                  <div key={evidence.key} className="flex items-center justify-between p-4 border border-gray-200 rounded-lg">
                    <div className="flex items-center gap-3">
                      {getStatusIcon(evidence.status)}
                      <div>
                        <div className="font-medium text-gray-900">
                          {evidence.key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                        </div>
                        <div className={`text-xs px-2 py-1 rounded font-medium mt-1 inline-block ${getStatusColor(evidence.status)}`}>
                          {evidence.status.replace(/_/g, ' ')}
                        </div>
                      </div>
                    </div>
                    
                    <div className="flex gap-2">
                      {evidence.document_url && (
                        <button className="p-2 text-gray-400 hover:text-blue-600">
                          <FileText className="w-4 h-4" />
                        </button>
                      )}
                      {evidence.status === 'NOT_STARTED' || evidence.status === 'REJECTED' ? (
                        <button className="p-2 text-gray-400 hover:text-green-600">
                          <Upload className="w-4 h-4" />
                        </button>
                      ) : (
                        <button className="p-2 text-gray-400 hover:text-blue-600">
                          <Eye className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              
              <div className="mt-6 pt-4 border-t border-gray-200">
                <button 
                  onClick={() => setSelectedGate(null)}
                  className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}