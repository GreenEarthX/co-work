import React, { useState, useEffect } from 'react';
import { Plus, Filter, Search, Eye, Edit, MapPin, DollarSign, Calendar } from 'lucide-react';

interface Project {
  id: string;
  name: string;
  molecule: string;
  location: string;
  capacity_mtpd: number;
  capex_eur: number;
  status: string;
  completion_date: string;
}

export function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);

  useEffect(() => {
    loadProjects();
  }, []);

  const loadProjects = async () => {
    setLoading(true);
    try {
      // Try multiple API endpoints to get project data
      const [capResponse, projResponse] = await Promise.all([
        fetch('/api/v1/capacities/list').catch(() => ({ json: () => ({ capacities: [] }) })),
        fetch('/api/v1/projects/list').catch(() => ({ json: () => ({ projects: [] }) }))
      ]);

      const capData = await capResponse.json();
      const projData = await projResponse.json();
      
      // Use capacity data as primary source if available
      if (capData.capacities && capData.capacities.length > 0) {
        const projectsFromCapacity = capData.capacities.map((cap: any) => ({
          id: cap.id || `cap_${Math.random()}`,
          name: cap.project_name || cap.name,
          molecule: cap.molecule || 'H2',
          location: cap.location || 'Unknown',
          capacity_mtpd: cap.capacity_mtpd || 0,
          capex_eur: cap.capex_eur || 0,
          status: cap.status || 'development',
          completion_date: cap.completion_date || '2027-12-31'
        }));
        setProjects(projectsFromCapacity);
      } else if (projData.projects && projData.projects.length > 0) {
        setProjects(projData.projects);
      } else {
        // Fallback demo data
        setProjects([
          {
            id: '1',
            name: 'Hamburg H2 Plant', 
            molecule: 'H2',
            location: 'Hamburg, Germany',
            capacity_mtpd: 100,
            capex_eur: 200000000,
            status: 'operating',
            completion_date: '2026-05-01'
          },
          {
            id: '2',
            name: 'Rotterdam NH3 Terminal',
            molecule: 'NH3', 
            location: 'Rotterdam, Netherlands',
            capacity_mtpd: 150,
            capex_eur: 350000000,
            status: 'construction',
            completion_date: '2026-12-01'
          }
        ]);
      }
    } catch (error) {
      console.error('Failed to load projects:', error);
    }
    setLoading(false);
  };

  const filteredProjects = projects.filter(project => 
    filter === 'all' || project.molecule === filter
  );

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
          <h1 className="text-2xl font-black text-gray-900">Projects & Assets</h1>
          <p className="text-sm text-gray-600 mt-1">Manage your green fuel projects</p>
        </div>
        <button className="px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 flex items-center gap-2">
          <Plus className="w-4 h-4" />
          New Project
        </button>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-gray-500" />
          <select value={filter} onChange={(e) => setFilter(e.target.value)} className="px-3 py-2 border border-gray-200 rounded-lg">
            <option value="all">All Molecules</option>
            <option value="H2">Hydrogen</option>
            <option value="NH3">Ammonia</option>
            <option value="SAF">SAF</option>
          </select>
        </div>
        <div className="flex-1 max-w-md">
          <div className="relative">
            <Search className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 transform -translate-y-1/2" />
            <input type="text" placeholder="Search projects..." className="w-full pl-10 pr-4 py-2 border border-gray-200 rounded-lg" />
          </div>
        </div>
      </div>

      {/* Projects Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filteredProjects.map(project => (
          <div key={project.id} className="bg-white rounded-xl border border-gray-200 p-6 hover:shadow-lg transition-shadow">
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
                  <span className="text-lg font-bold text-blue-600">{project.molecule}</span>
                </div>
                <div>
                  <h3 className="font-bold text-gray-900">{project.name}</h3>
                  <div className="flex items-center gap-1 text-sm text-gray-500">
                    <MapPin className="w-3 h-3" />
                    {project.location}
                  </div>
                </div>
              </div>
              <div className="flex gap-1">
                <button onClick={() => setSelectedProject(project)} className="p-1 text-gray-400 hover:text-blue-600">
                  <Eye className="w-4 h-4" />
                </button>
                <button className="p-1 text-gray-400 hover:text-blue-600">
                  <Edit className="w-4 h-4" />
                </button>
              </div>
            </div>

            <div className="space-y-3 mb-4">
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Capacity</span>
                <span className="font-semibold">{project.capacity_mtpd} MTPD</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">CAPEX</span>
                <span className="font-semibold">€{(project.capex_eur / 1000000).toFixed(0)}M</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Status</span>
                <span className="font-semibold capitalize">{project.status}</span>
              </div>
            </div>

            <div className="flex gap-2">
              <button onClick={() => setSelectedProject(project)} className="flex-1 px-3 py-2 bg-blue-50 text-blue-700 rounded-lg text-sm font-medium hover:bg-blue-100">
                View Details
              </button>
              <button className="px-3 py-2 border border-gray-200 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-50">
                Manage
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Project Detail Modal */}
      {selectedProject && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl max-w-2xl w-full">
            <div className="p-6 border-b border-gray-200">
              <div className="flex items-center justify-between">
                <h2 className="text-xl font-bold text-gray-900">{selectedProject.name}</h2>
                <button onClick={() => setSelectedProject(null)} className="text-gray-400 hover:text-gray-600">✕</button>
              </div>
            </div>
            <div className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <span className="text-gray-600 text-sm">Molecule:</span>
                  <div className="font-medium">{selectedProject.molecule}</div>
                </div>
                <div>
                  <span className="text-gray-600 text-sm">Location:</span>
                  <div className="font-medium">{selectedProject.location}</div>
                </div>
                <div>
                  <span className="text-gray-600 text-sm">Capacity:</span>
                  <div className="font-medium">{selectedProject.capacity_mtpd} MTPD</div>
                </div>
                <div>
                  <span className="text-gray-600 text-sm">CAPEX:</span>
                  <div className="font-medium">€{(selectedProject.capex_eur / 1000000).toFixed(0)}M</div>
                </div>
              </div>
              <div className="flex gap-3 pt-4 border-t">
                <button className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">Manage Project</button>
                <button onClick={() => setSelectedProject(null)} className="px-4 py-2 border border-gray-200 rounded-lg hover:bg-gray-50">Close</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}