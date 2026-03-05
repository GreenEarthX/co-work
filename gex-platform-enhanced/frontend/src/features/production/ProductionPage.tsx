import React, { useState, useEffect } from 'react';
import { Filter, Search, Plus, Trash2, Edit, Eye } from 'lucide-react';

interface ProductionBatch {
  id: string;
  project_name: string;
  molecule: string;
  batch_number: string;
  volume_mt: number;
  production_date: string;
  quality_status: 'pending' | 'approved' | 'rejected';
  ghg_intensity: number;
  purity_pct: number;
}

export function ProductionPage() {
  const [batches, setBatches] = useState<ProductionBatch[]>([]);
  const [projects, setProjects] = useState<string[]>([]);
  const [selectedProject, setSelectedProject] = useState<string>('all');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadProductionData();
  }, []);

  const loadProductionData = async () => {
    setLoading(true);
    try {
      // Get projects from capacity API
      const capResponse = await fetch('/api/v1/capacities/list');
      if (capResponse.ok) {
        const capData = await capResponse.json();
        const projectNames = [...new Set(capData.capacities?.map((c: any) => c.project_name) || [])];
        setProjects(projectNames);
      }

      // Mock production batches (in real app, this would come from production API)
      setBatches([
        {
          id: 'batch_001',
          project_name: 'Hamburg H2 Plant',
          molecule: 'H2',
          batch_number: 'HH2-2026-001',
          volume_mt: 25.5,
          production_date: '2026-02-25',
          quality_status: 'approved',
          ghg_intensity: 0.35,
          purity_pct: 99.8
        },
        {
          id: 'batch_002', 
          project_name: 'Hamburg H2 Plant',
          molecule: 'H2',
          batch_number: 'HH2-2026-002',
          volume_mt: 24.8,
          production_date: '2026-02-26',
          quality_status: 'pending',
          ghg_intensity: 0.38,
          purity_pct: 99.7
        },
        {
          id: 'batch_003',
          project_name: 'Rotterdam NH3 Terminal',
          molecule: 'NH3',
          batch_number: 'RNH3-2026-001',
          volume_mt: 45.2,
          production_date: '2026-02-24',
          quality_status: 'approved',
          ghg_intensity: 0.42,
          purity_pct: 99.9
        }
      ]);
    } catch (error) {
      console.error('Failed to load production data:', error);
    }
    setLoading(false);
  };

  const filteredBatches = batches.filter(batch => 
    selectedProject === 'all' || batch.project_name === selectedProject
  );

  const getQualityStatusColor = (status: string) => {
    switch (status) {
      case 'approved': return 'bg-green-100 text-green-800';
      case 'pending': return 'bg-yellow-100 text-yellow-800';
      case 'rejected': return 'bg-red-100 text-red-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const handleDeleteBatch = (batchId: string) => {
    if (confirm('Are you sure you want to delete this batch?')) {
      setBatches(batches.filter(b => b.id !== batchId));
    }
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
          <h1 className="text-2xl font-black text-gray-900">Production Management</h1>
          <p className="text-sm text-gray-600 mt-1">Monitor production batches and quality control</p>
        </div>
        <button className="px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 flex items-center gap-2">
          <Plus className="w-4 h-4" />
          New Batch
        </button>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-gray-500" />
          <select 
            value={selectedProject} 
            onChange={(e) => setSelectedProject(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg"
          >
            <option value="all">All Projects</option>
            {projects.map(project => (
              <option key={project} value={project}>{project}</option>
            ))}
          </select>
        </div>
        <div className="flex-1 max-w-md">
          <div className="relative">
            <Search className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 transform -translate-y-1/2" />
            <input type="text" placeholder="Search batches..." className="w-full pl-10 pr-4 py-2 border border-gray-200 rounded-lg" />
          </div>
        </div>
      </div>

      {/* Production Summary */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="text-2xl font-black text-blue-600">{filteredBatches.length}</div>
          <div className="text-sm text-gray-600">Total Batches</div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="text-2xl font-black text-green-600">
            {filteredBatches.reduce((sum, b) => sum + b.volume_mt, 0).toFixed(1)}
          </div>
          <div className="text-sm text-gray-600">Total Volume (MT)</div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="text-2xl font-black text-green-600">
            {filteredBatches.filter(b => b.quality_status === 'approved').length}
          </div>
          <div className="text-sm text-gray-600">Approved Batches</div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="text-2xl font-black text-yellow-600">
            {filteredBatches.filter(b => b.quality_status === 'pending').length}
          </div>
          <div className="text-sm text-gray-600">Pending Review</div>
        </div>
      </div>

      {/* Batches Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-bold text-gray-900">Production Batches</h2>
        </div>
        
        {filteredBatches.length === 0 ? (
          <div className="p-8 text-center text-gray-500">
            No production batches found for the selected project.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Batch</th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Project</th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Volume</th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Quality</th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase">GHG</th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Purity</th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Date</th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {filteredBatches.map(batch => (
                  <tr key={batch.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4">
                      <div className="font-medium text-gray-900">{batch.batch_number}</div>
                      <div className="text-sm text-gray-500">{batch.molecule}</div>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">{batch.project_name}</td>
                    <td className="px-6 py-4 text-sm font-medium text-gray-900">{batch.volume_mt} MT</td>
                    <td className="px-6 py-4">
                      <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${getQualityStatusColor(batch.quality_status)}`}>
                        {batch.quality_status.charAt(0).toUpperCase() + batch.quality_status.slice(1)}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">{batch.ghg_intensity} kg/kg</td>
                    <td className="px-6 py-4 text-sm text-gray-900">{batch.purity_pct}%</td>
                    <td className="px-6 py-4 text-sm text-gray-900">{batch.production_date}</td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <button className="p-1 text-gray-400 hover:text-blue-600">
                          <Eye className="w-4 h-4" />
                        </button>
                        <button className="p-1 text-gray-400 hover:text-green-600">
                          <Edit className="w-4 h-4" />
                        </button>
                        <button 
                          onClick={() => handleDeleteBatch(batch.id)}
                          className="p-1 text-gray-400 hover:text-red-600"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}