import React, { useState, useEffect } from 'react';
import { Plus, Search, Filter, CheckCircle, XCircle, Clock, FileText } from 'lucide-react';

interface RFQ {
  id: string;
  molecule: string;
  volume_mtpd: number;
  max_price_eur_kg: number | null;
  delivery_start: string;
  delivery_end: string;
  location: string | null;
  buyer_name: string;
  status: string;
  created_at: string;
  compliance_requirements: string[] | null;
}

const RFQManagementPage: React.FC = () => {
  const [rfqs, setRfqs] = useState<RFQ[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [filter, setFilter] = useState<string>('all');

  // Form state
  const [formData, setFormData] = useState({
    molecule: 'H2',
    volume_mtpd: '',
    max_price_eur_kg: '',
    delivery_start: '',
    delivery_end: '',
    location: '',
    buyer_name: '',
    buyer_contact: '',
    compliance_requirements: [] as string[]
  });

  useEffect(() => {
    fetchRFQs();
  }, [filter]);

  const fetchRFQs = async () => {
    try {
      const url = filter === 'all' 
        ? '/api/v1/trader/rfqs'
        : `/api/v1/trader/rfqs?status=${filter}`;
      
      const response = await fetch(url);
      const data = await response.json();
      setRfqs(data.rfqs || []);
    } catch (error) {
      console.error('Error fetching RFQs:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    try {
      const response = await fetch('/api/v1/trader/rfqs/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...formData,
          volume_mtpd: parseFloat(formData.volume_mtpd),
          max_price_eur_kg: formData.max_price_eur_kg ? parseFloat(formData.max_price_eur_kg) : null,
          compliance_requirements: formData.compliance_requirements.length > 0 
            ? formData.compliance_requirements 
            : null
        })
      });

      if (response.ok) {
        setShowCreateModal(false);
        fetchRFQs();
        // Reset form
        setFormData({
          molecule: 'H2',
          volume_mtpd: '',
          max_price_eur_kg: '',
          delivery_start: '',
          delivery_end: '',
          location: '',
          buyer_name: '',
          buyer_contact: '',
          compliance_requirements: []
        });
      }
    } catch (error) {
      console.error('Error creating RFQ:', error);
    }
  };

  const getStatusBadge = (status: string) => {
    const badges: Record<string, { bg: string; text: string; icon: React.ReactNode }> = {
      draft: { bg: 'bg-gray-100', text: 'text-gray-700', icon: <FileText className="w-4 h-4" /> },
      open: { bg: 'bg-blue-100', text: 'text-blue-700', icon: <Clock className="w-4 h-4" /> },
      matched: { bg: 'bg-yellow-100', text: 'text-yellow-700', icon: <Clock className="w-4 h-4" /> },
      accepted: { bg: 'bg-green-100', text: 'text-green-700', icon: <CheckCircle className="w-4 h-4" /> },
      contracted: { bg: 'bg-emerald-100', text: 'text-emerald-700', icon: <CheckCircle className="w-4 h-4" /> },
      fulfilled: { bg: 'bg-green-100', text: 'text-green-700', icon: <CheckCircle className="w-4 h-4" /> },
      rejected: { bg: 'bg-red-100', text: 'text-red-700', icon: <XCircle className="w-4 h-4" /> },
      cancelled: { bg: 'bg-gray-100', text: 'text-gray-500', icon: <XCircle className="w-4 h-4" /> },
      expired: { bg: 'bg-gray-100', text: 'text-gray-500', icon: <XCircle className="w-4 h-4" /> },
      withdrawn: { bg: 'bg-gray-100', text: 'text-gray-500', icon: <XCircle className="w-4 h-4" /> }
    };

    const badge = badges[status] || badges.draft;
    
    return (
      <span className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium ${badge.bg} ${badge.text}`}>
        {badge.icon}
        {status.charAt(0).toUpperCase() + status.slice(1)}
      </span>
    );
  };

  // Summary stats
  const stats = {
    total: rfqs.length,
    open: rfqs.filter(r => r.status === 'open').length,
    matched: rfqs.filter(r => r.status === 'matched').length,
    contracted: rfqs.filter(r => r.status === 'contracted' || r.status === 'accepted').length
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">RFQ Management</h1>
          <p className="text-gray-600 mt-1">Create and manage buyer requests for green molecules</p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          <Plus className="w-5 h-5" />
          Create RFQ
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white p-6 rounded-lg shadow-sm border">
          <div className="text-gray-600 text-sm font-medium">Total RFQs</div>
          <div className="text-3xl font-bold text-gray-900 mt-2">{stats.total}</div>
        </div>
        <div className="bg-white p-6 rounded-lg shadow-sm border">
          <div className="text-blue-600 text-sm font-medium">Open</div>
          <div className="text-3xl font-bold text-blue-600 mt-2">{stats.open}</div>
        </div>
        <div className="bg-white p-6 rounded-lg shadow-sm border">
          <div className="text-yellow-600 text-sm font-medium">Matched</div>
          <div className="text-3xl font-bold text-yellow-600 mt-2">{stats.matched}</div>
        </div>
        <div className="bg-white p-6 rounded-lg shadow-sm border">
          <div className="text-green-600 text-sm font-medium">Contracted</div>
          <div className="text-3xl font-bold text-green-600 mt-2">{stats.contracted}</div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-2">
        {['all', 'draft', 'open', 'matched', 'accepted', 'contracted'].map((status) => (
          <button
            key={status}
            onClick={() => setFilter(status)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              filter === status
                ? 'bg-blue-100 text-blue-700'
                : 'bg-white text-gray-600 hover:bg-gray-50'
            }`}
          >
            {status.charAt(0).toUpperCase() + status.slice(1)}
          </button>
        ))}
      </div>

      {/* RFQ List */}
      <div className="bg-white rounded-lg shadow-sm border">
        {loading ? (
          <div className="p-8 text-center text-gray-500">Loading RFQs...</div>
        ) : rfqs.length === 0 ? (
          <div className="p-8 text-center">
            <FileText className="w-12 h-12 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-600">No RFQs found</p>
            <button
              onClick={() => setShowCreateModal(true)}
              className="mt-4 text-blue-600 hover:text-blue-700 font-medium"
            >
              Create your first RFQ
            </button>
          </div>
        ) : (
          <div className="divide-y">
            {rfqs.map((rfq) => (
              <div key={rfq.id} className="p-6 hover:bg-gray-50 transition-colors">
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <h3 className="text-lg font-semibold text-gray-900">
                        {rfq.molecule} - {rfq.volume_mtpd} MTPD
                      </h3>
                      {getStatusBadge(rfq.status)}
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-3 text-sm">
                      <div>
                        <span className="text-gray-500">Buyer:</span>
                        <div className="font-medium text-gray-900">{rfq.buyer_name}</div>
                      </div>
                      <div>
                        <span className="text-gray-500">Max Price:</span>
                        <div className="font-medium text-gray-900">
                          {rfq.max_price_eur_kg ? `€${rfq.max_price_eur_kg.toFixed(2)}/kg` : 'Not specified'}
                        </div>
                      </div>
                      <div>
                        <span className="text-gray-500">Delivery:</span>
                        <div className="font-medium text-gray-900">
                          {rfq.delivery_start} to {rfq.delivery_end}
                        </div>
                      </div>
                      <div>
                        <span className="text-gray-500">Location:</span>
                        <div className="font-medium text-gray-900">{rfq.location || 'Any'}</div>
                      </div>
                    </div>
                    {rfq.compliance_requirements && rfq.compliance_requirements.length > 0 && (
                      <div className="mt-3">
                        <span className="text-sm text-gray-500">Requirements:</span>
                        <div className="flex gap-2 mt-1">
                          {rfq.compliance_requirements.map((req, i) => (
                            <span key={i} className="px-2 py-1 bg-blue-50 text-blue-700 text-xs rounded">
                              {req}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Create Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto p-6">
            <h2 className="text-xl font-bold mb-4">Create New RFQ</h2>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Molecule</label>
                  <select
                    value={formData.molecule}
                    onChange={(e) => setFormData({ ...formData, molecule: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg"
                    required
                  >
                    <option value="H2">H2 (Hydrogen)</option>
                    <option value="NH3">NH3 (Ammonia)</option>
                    <option value="CH3OH">CH3OH (Methanol)</option>
                    <option value="SAF">SAF (Sustainable Aviation Fuel)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Volume (MTPD)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={formData.volume_mtpd}
                    onChange={(e) => setFormData({ ...formData, volume_mtpd: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Max Price (€/kg) - Optional</label>
                <input
                  type="number"
                  step="0.01"
                  value={formData.max_price_eur_kg}
                  onChange={(e) => setFormData({ ...formData, max_price_eur_kg: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg"
                  placeholder="Leave empty for no limit"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Delivery Start</label>
                  <input
                    type="date"
                    value={formData.delivery_start}
                    onChange={(e) => setFormData({ ...formData, delivery_start: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Delivery End</label>
                  <input
                    type="date"
                    value={formData.delivery_end}
                    onChange={(e) => setFormData({ ...formData, delivery_end: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Location - Optional</label>
                <input
                  type="text"
                  value={formData.location}
                  onChange={(e) => setFormData({ ...formData, location: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg"
                  placeholder="e.g., Hamburg, Germany"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Buyer Name</label>
                <input
                  type="text"
                  value={formData.buyer_name}
                  onChange={(e) => setFormData({ ...formData, buyer_name: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Buyer Contact - Optional</label>
                <input
                  type="email"
                  value={formData.buyer_contact}
                  onChange={(e) => setFormData({ ...formData, buyer_contact: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg"
                  placeholder="email@company.com"
                />
              </div>

              <div className="flex gap-2 justify-end pt-4">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 border rounded-lg hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                  Create RFQ
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default RFQManagementPage;
