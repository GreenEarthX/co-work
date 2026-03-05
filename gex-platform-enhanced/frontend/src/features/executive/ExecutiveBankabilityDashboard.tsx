import React, { useState, useEffect } from 'react';
import { TrendingUp, AlertTriangle, CheckCircle, DollarSign, Users, Activity, Target, Eye } from 'lucide-react';

interface ProjectBankabilityKPI {
  project_id: string;
  project_name: string;
  current_state: string;
  overall_completion_pct: number;
  total_evidence: number;
  total_verified: number;
  regression_detected: boolean;
  total_unlocked_capital: string;
  next_milestone: string;
  persona_progress: {
    [persona: string]: {
      gates_complete: number;
      total_gates: number;
      completion_pct: number;
      blocking_items: number;
    };
  };
}

interface PortfolioSummary {
  total_projects: number;
  total_portfolio_value: string;
  total_unlocked: string;
  average_completion: number;
  projects_with_regressions: number;
  capital_pipeline: {
    stage: string;
    amount: string;
    projects: number;
  }[];
}

export function ExecutiveBankabilityDashboard() {
  const [portfolioData, setPortfolioData] = useState<PortfolioSummary | null>(null);
  const [projectKPIs, setProjectKPIs] = useState<ProjectBankabilityKPI[]>([]);
  const [selectedProject, setSelectedProject] = useState<ProjectBankabilityKPI | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadExecutiveData();
  }, []);

  const loadExecutiveData = async () => {
    setLoading(true);
    try {
      // In real implementation, this would fetch from /api/v1/bankability/executive/portfolio
      // For now, using demo data
      setPortfolioData({
        total_projects: 8,
        total_portfolio_value: '€1.2B',
        total_unlocked: '€342M',
        average_completion: 67,
        projects_with_regressions: 1,
        capital_pipeline: [
          { stage: 'Grants & TA', amount: '€15M', projects: 8 },
          { stage: 'Seed/Angel', amount: '€45M', projects: 6 },
          { stage: 'Project Equity', amount: '€280M', projects: 4 },
          { stage: 'Senior Debt', amount: '€650M', projects: 2 },
          { stage: 'Debt Drawdown', amount: '€850M', projects: 1 }
        ]
      });

      setProjectKPIs([
        {
          project_id: 'proj_hamburg_h2',
          project_name: 'Hamburg H2 Plant',
          current_state: 'STRUCTURALLY_BANKABLE',
          overall_completion_pct: 82,
          total_evidence: 48,
          total_verified: 39,
          regression_detected: false,
          total_unlocked_capital: '€85M',
          next_milestone: 'Complete G10 for Financial Close',
          persona_progress: {
            PRODUCER: { gates_complete: 4, total_gates: 6, completion_pct: 67, blocking_items: 2 },
            FINANCE: { gates_complete: 3, total_gates: 5, completion_pct: 60, blocking_items: 3 },
            REGULATOR: { gates_complete: 3, total_gates: 4, completion_pct: 75, blocking_items: 1 },
          }
        },
        {
          project_id: 'proj_rotterdam_nh3',
          project_name: 'Rotterdam NH3 Terminal',
          current_state: 'BUILDABLE',
          overall_completion_pct: 65,
          total_evidence: 48,
          total_verified: 31,
          regression_detected: true,
          total_unlocked_capital: '€42M',
          next_milestone: 'Resolve insurance coverage gap',
          persona_progress: {
            PRODUCER: { gates_complete: 3, total_gates: 6, completion_pct: 50, blocking_items: 3 },
            FINANCE: { gates_complete: 2, total_gates: 5, completion_pct: 40, blocking_items: 5 },
            REGULATOR: { gates_complete: 2, total_gates: 4, completion_pct: 50, blocking_items: 2 },
          }
        },
        {
          project_id: 'proj_marseille_saf',
          project_name: 'Marseille SAF Plant',
          current_state: 'COMMERCIALLY_PLAUSIBLE',
          overall_completion_pct: 45,
          total_evidence: 48,
          total_verified: 22,
          regression_detected: false,
          total_unlocked_capital: '€12M',
          next_milestone: 'Complete G4 off-take agreements',
          persona_progress: {
            PRODUCER: { gates_complete: 2, total_gates: 6, completion_pct: 33, blocking_items: 4 },
            FINANCE: { gates_complete: 1, total_gates: 5, completion_pct: 20, blocking_items: 7 },
            REGULATOR: { gates_complete: 1, total_gates: 4, completion_pct: 25, blocking_items: 3 },
          }
        }
      ]);

    } catch (error) {
      console.error('Failed to load executive data:', error);
    }
    setLoading(false);
  };

  const getStateColor = (state: string) => {
    const colors = {
      'SPECULATIVE': 'bg-gray-100 text-gray-700',
      'TECHNICALLY_PLAUSIBLE': 'bg-blue-100 text-blue-700',
      'COMMERCIALLY_PLAUSIBLE': 'bg-purple-100 text-purple-700',
      'BUILDABLE': 'bg-yellow-100 text-yellow-700',
      'STRUCTURALLY_BANKABLE': 'bg-green-100 text-green-700',
      'CREDIT_APPROVED': 'bg-emerald-100 text-emerald-700',
      'FINANCEABLE': 'bg-teal-100 text-teal-700',
      'OPERATIONAL': 'bg-indigo-100 text-indigo-700'
    };
    return colors[state as keyof typeof colors] || 'bg-gray-100 text-gray-700';
  };

  const getPersonaIcon = (persona: string) => {
    const icons = {
      'PRODUCER': <Activity className="w-4 h-4" />,
      'FINANCE': <DollarSign className="w-4 h-4" />,
      'REGULATOR': <CheckCircle className="w-4 h-4" />
    };
    return icons[persona as keyof typeof icons] || <Users className="w-4 h-4" />;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Executive Summary */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h1 className="text-2xl font-black text-gray-900 mb-6">Portfolio Bankability Dashboard</h1>
        
        {portfolioData && (
          <div className="grid grid-cols-1 md:grid-cols-5 gap-6 mb-6">
            <div className="text-center">
              <div className="text-3xl font-black text-blue-600">{portfolioData.total_projects}</div>
              <div className="text-sm text-gray-600">Active Projects</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-black text-green-600">{portfolioData.total_portfolio_value}</div>
              <div className="text-sm text-gray-600">Portfolio Value</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-black text-emerald-600">{portfolioData.total_unlocked}</div>
              <div className="text-sm text-gray-600">Capital Unlocked</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-black text-purple-600">{portfolioData.average_completion}%</div>
              <div className="text-sm text-gray-600">Avg Completion</div>
            </div>
            <div className="text-center">
              <div className={`text-3xl font-black ${portfolioData.projects_with_regressions > 0 ? 'text-red-600' : 'text-gray-400'}`}>
                {portfolioData.projects_with_regressions}
              </div>
              <div className="text-sm text-gray-600">Risk Alerts</div>
            </div>
          </div>
        )}

        {/* Capital Pipeline */}
        {portfolioData && (
          <div className="bg-gray-50 rounded-lg p-4">
            <h3 className="font-bold text-gray-900 mb-3 flex items-center gap-2">
              <Target className="w-5 h-5" />
              Capital Pipeline
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
              {portfolioData.capital_pipeline.map((stage, index) => (
                <div key={stage.stage} className="text-center">
                  <div className="text-lg font-bold text-gray-900">{stage.amount}</div>
                  <div className="text-sm text-gray-600">{stage.stage}</div>
                  <div className="text-xs text-gray-500">{stage.projects} projects</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Projects Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
        {projectKPIs.map(project => (
          <div 
            key={project.project_id}
            className={`bg-white rounded-xl border-2 p-6 cursor-pointer transition-all hover:shadow-lg ${
              project.regression_detected ? 'border-red-200 bg-red-50' : 'border-gray-200'
            }`}
            onClick={() => setSelectedProject(project)}
          >
            {/* Project Header */}
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="font-bold text-gray-900">{project.project_name}</h3>
                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStateColor(project.current_state)}`}>
                  {project.current_state.replace(/_/g, ' ')}
                </span>
              </div>
              {project.regression_detected && (
                <AlertTriangle className="w-5 h-5 text-red-600" />
              )}
            </div>

            {/* Overall Progress */}
            <div className="mb-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-gray-700">Overall Progress</span>
                <span className="text-sm font-medium text-gray-900">{project.overall_completion_pct}%</span>
              </div>
              <div className="bg-gray-200 rounded-full h-2">
                <div 
                  className="bg-blue-600 h-2 rounded-full"
                  style={{ width: `${project.overall_completion_pct}%` }}
                ></div>
              </div>
              <div className="text-xs text-gray-600 mt-1">
                {project.total_verified} of {project.total_evidence} evidence verified
              </div>
            </div>

            {/* Persona Progress */}
            <div className="space-y-2 mb-4">
              {Object.entries(project.persona_progress).map(([persona, progress]) => (
                <div key={persona} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    {getPersonaIcon(persona)}
                    <span className="font-medium text-gray-700">{persona}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-gray-600">{progress.completion_pct}%</span>
                    {progress.blocking_items > 0 && (
                      <span className="px-1.5 py-0.5 bg-red-100 text-red-700 rounded text-xs">
                        {progress.blocking_items}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Financial Summary */}
            <div className="border-t border-gray-200 pt-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">Unlocked Capital</span>
                <span className="font-bold text-green-600">{project.total_unlocked_capital}</span>
              </div>
              <div className="text-xs text-gray-500 mt-1 truncate">
                Next: {project.next_milestone}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Project Detail Modal */}
      {selectedProject && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b border-gray-200">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-bold text-gray-900">{selectedProject.project_name}</h2>
                  <div className="flex items-center gap-3 mt-2">
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStateColor(selectedProject.current_state)}`}>
                      {selectedProject.current_state.replace(/_/g, ' ')}
                    </span>
                    {selectedProject.regression_detected && (
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">
                        <AlertTriangle className="w-3 h-3 mr-1" />
                        Regression Detected
                      </span>
                    )}
                  </div>
                </div>
                <button 
                  onClick={() => setSelectedProject(null)}
                  className="text-gray-400 hover:text-gray-600"
                >
                  ✕
                </button>
              </div>
            </div>
            
            <div className="p-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Overall Metrics */}
                <div>
                  <h3 className="font-bold text-gray-900 mb-4">Project Metrics</h3>
                  <div className="space-y-3">
                    <div className="flex justify-between">
                      <span className="text-gray-600">Overall Completion:</span>
                      <span className="font-bold">{selectedProject.overall_completion_pct}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Evidence Verified:</span>
                      <span className="font-bold">{selectedProject.total_verified}/{selectedProject.total_evidence}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Unlocked Capital:</span>
                      <span className="font-bold text-green-600">{selectedProject.total_unlocked_capital}</span>
                    </div>
                    <div className="text-sm text-gray-600 pt-2 border-t">
                      <span className="font-medium">Next Milestone:</span><br />
                      {selectedProject.next_milestone}
                    </div>
                  </div>
                </div>

                {/* Persona Breakdown */}
                <div>
                  <h3 className="font-bold text-gray-900 mb-4">Team Progress</h3>
                  <div className="space-y-4">
                    {Object.entries(selectedProject.persona_progress).map(([persona, progress]) => (
                      <div key={persona} className="p-3 bg-gray-50 rounded-lg">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            {getPersonaIcon(persona)}
                            <span className="font-medium">{persona}</span>
                          </div>
                          <span className="font-bold">{progress.completion_pct}%</span>
                        </div>
                        <div className="bg-gray-200 rounded-full h-1.5 mb-2">
                          <div 
                            className="bg-blue-600 h-1.5 rounded-full"
                            style={{ width: `${progress.completion_pct}%` }}
                          ></div>
                        </div>
                        <div className="flex justify-between text-xs text-gray-600">
                          <span>{progress.gates_complete}/{progress.total_gates} gates</span>
                          {progress.blocking_items > 0 && (
                            <span className="text-red-600">{progress.blocking_items} blocking</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="mt-6 pt-4 border-t border-gray-200 flex gap-3">
                <button 
                  onClick={() => setSelectedProject(null)}
                  className="flex-1 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg font-medium hover:bg-gray-200"
                >
                  Close
                </button>
                <button className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 flex items-center justify-center gap-2">
                  <Eye className="w-4 h-4" />
                  View Details
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}