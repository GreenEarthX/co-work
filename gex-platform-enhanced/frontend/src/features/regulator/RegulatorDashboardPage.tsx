import React, { useState, useEffect } from 'react';
import { Shield, CheckCircle, AlertCircle, FileCheck, Eye, Search, Filter } from 'lucide-react';

interface Project {
  id: string;
  name: string;
  molecule: string;
  producer: string;
  compliance_status: 'compliant' | 'pending' | 'non_compliant';
  certifications: string[];
  last_audit: string;
  next_review: string;
  risk_level: 'low' | 'medium' | 'high';
}

export function RegulatorDashboardPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadProjects();
  }, []);

  const loadProjects = async () => {
    setLoading(true);
    try {
      // Simulate API call
      setProjects([
        {
          id: '1',
          name: 'Hamburg H2 Plant',
          molecule: 'H2',
          producer: 'Hamburg H2 GmbH',
          compliance_status: 'compliant',
          certifications: ['RED III', '45V'],
          last_audit: '2026-01-15',
          next_review: '2026-07-15',
          risk_level: 'low'
        },
        {
          id: '2',
          name: 'Rotterdam NH3 Terminal',
          molecule: 'NH3',
          producer: 'Port of Rotterdam',
          compliance_status: 'pending',
          certifications: ['RED III'],
          last_audit: '2025-11-20',
          next_review: '2026-05-20',
          risk_level: 'medium'
        },
        {
          id: '3',
          name: 'Marseille SAF Plant',
          molecule: 'SAF',
          producer: 'Total Energies',
          compliance_status: 'non_compliant',
          certifications: [],
          last_audit: '2025-09-10',
          next_review: '2026-03-10',
          risk_level: 'high'
        }
      ]);
    } catch (error) {
      console.error('Failed to load projects:', error);
    }
    setLoading(false);
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'compliant':
        return <CheckCircle className="w-4 h-4 text-green-600" />;
      case 'pending':
        return <AlertCircle className="w-4 h-4 text-yellow-600" />;
      case 'non_compliant':
        return <AlertCircle className="w-4 h-4 text-red-600" />;
      default:
        return <Shield className="w-4 h-4 text-gray-400" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'compliant':
        return 'bg-green-50 text-green-700 border-green-200';
      case 'pending':
        return 'bg-yellow-50 text-yellow-700 border-yellow-200';
      case 'non_compliant':
        return 'bg-red-50 text-red-700 border-red-200';
      default:
        return 'bg-gray-50 text-gray-700 border-gray-200';
    }
  };

  const getRiskColor = (risk: string) => {
    switch (risk) {
      case 'low':
        return 'bg-green-100 text-green-800';
      case 'medium':
        return 'bg-yellow-100 text-yellow-800';
      case 'high':
        return 'bg-red-100 text-red-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const filteredProjects = projects.filter(project => 
    filter === 'all' || project.compliance_status === filter
  );

  const complianceStats = {
    total: projects.length,
    compliant: projects.filter(p => p.compliance_status === 'compliant').length,
    pending: projects.filter(p => p.compliance_status === 'pending').length,
    non_compliant: projects.filter(p => p.compliance_status === 'non_compliant').length
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
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black text-gray-900">Regulatory Dashboard</h1>
          <p className="text-sm text-gray-600 mt-1">Project compliance monitoring and verification</p>
        </div>
        <div className="flex items-center gap-3">
          <button className="px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 flex items-center gap-2">
            <FileCheck className="w-4 h-4" />
            New Audit
          </button>
        </div>
      </div>

      {/* Compliance Overview */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-center gap-3">
            <Shield className="w-8 h-8 text-blue-600" />
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wider font-semibold">Total Projects</p>
              <p className="text-2xl font-black text-gray-900">{complianceStats.total}</p>
            </div>
          </div>
        </div>
        
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-center gap-3">
            <CheckCircle className="w-8 h-8 text-green-600" />
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wider font-semibold">Compliant</p>
              <p className="text-2xl font-black text-green-600">{complianceStats.compliant}</p>
            </div>
          </div>
        </div>
        
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-center gap-3">
            <AlertCircle className="w-8 h-8 text-yellow-600" />
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wider font-semibold">Pending Review</p>
              <p className="text-2xl font-black text-yellow-600">{complianceStats.pending}</p>
            </div>
          </div>
        </div>
        
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-center gap-3">
            <AlertCircle className="w-8 h-8 text-red-600" />
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wider font-semibold">Non-Compliant</p>
              <p className="text-2xl font-black text-red-600">{complianceStats.non_compliant}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-gray-500" />
          <select 
            value={filter} 
            onChange={(e) => setFilter(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm"
          >
            <option value="all">All Status</option>
            <option value="compliant">Compliant</option>
            <option value="pending">Pending Review</option>
            <option value="non_compliant">Non-Compliant</option>
          </select>
        </div>
        <div className="flex-1 max-w-md">
          <div className="relative">
            <Search className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 transform -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search projects..."
              className="w-full pl-10 pr-4 py-2 border border-gray-200 rounded-lg text-sm"
            />
          </div>
        </div>
      </div>

      {/* Projects Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-bold text-gray-900">Project Compliance Status</h2>
        </div>
        
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Project
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Producer
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Compliance Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Certifications
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Risk Level
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Last Audit
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {filteredProjects.map(project => (
                <tr key={project.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4">
                    <div>
                      <div className="font-medium text-gray-900">{project.name}</div>
                      <div className="text-sm text-gray-500">{project.molecule}</div>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-900">
                    {project.producer}
                  </td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full border text-xs font-medium ${getStatusColor(project.compliance_status)}`}>
                      {getStatusIcon(project.compliance_status)}
                      {project.compliance_status.replace('_', ' ').toUpperCase()}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex flex-wrap gap-1">
                      {project.certifications.map(cert => (
                        <span key={cert} className="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs font-medium">
                          {cert}
                        </span>
                      ))}
                      {project.certifications.length === 0 && (
                        <span className="text-sm text-gray-500">None</span>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${getRiskColor(project.risk_level)}`}>
                      {project.risk_level.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-900">
                    {project.last_audit}
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-2">
                      <button className="p-1 text-gray-400 hover:text-blue-600">
                        <Eye className="w-4 h-4" />
                      </button>
                      <button className="p-1 text-gray-400 hover:text-green-600">
                        <FileCheck className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}