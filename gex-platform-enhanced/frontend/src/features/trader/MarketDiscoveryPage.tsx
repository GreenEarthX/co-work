import React, { useState, useEffect } from 'react';
import { Search, Filter, TrendingUp, MapPin, Calendar, DollarSign, Award, FileText } from 'lucide-react';

interface Offer {
  id: string;
  molecule: string;
  volume_mtpd: number;
  price_eur_kg: number;
  delivery_start: string;
  delivery_end: string;
  location: string;
  offer_type: string;
  producer_info: {
    project_name: string;
    location: string;
  };
  compliance_certifications: string[];
  total_value_eur: number;
  tenor_years: number;
}

interface MarketStats {
  total_offers: number;
  total_volume_mtpd: number;
  avg_price_eur_kg: number;
  min_price_eur_kg: number;
  max_price_eur_kg: number;
  molecules_available: string[];
}

const MarketDiscoveryPage: React.FC = () => {
  const [offers, setOffers] = useState<Offer[]>([]);
  const [stats, setStats] = useState<MarketStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [showFilters, setShowFilters] = useState(true);
  const [selectedOffer, setSelectedOffer] = useState<Offer | null>(null);

  // Filters
  const [filters, setFilters] = useState({
    molecule: '',
    minPrice: '',
    maxPrice: '',
    minVolume: '',
    location: '',
    certification: '',
    sortBy: 'price',
    sortOrder: 'asc'
  });

  useEffect(() => {
    fetchOffers();
  }, [filters]);

  const fetchOffers = async () => {
    try {
      setLoading(true);
      
      const params = new URLSearchParams();
      if (filters.molecule) params.append('molecule', filters.molecule);
      if (filters.minPrice) params.append('min_price', filters.minPrice);
      if (filters.maxPrice) params.append('max_price', filters.maxPrice);
      if (filters.minVolume) params.append('min_volume', filters.minVolume);
      if (filters.location) params.append('location', filters.location);
      if (filters.certification) params.append('certification', filters.certification);
      if (filters.sortBy) params.append('sort_by', filters.sortBy);
      if (filters.sortOrder) params.append('sort_order', filters.sortOrder);

      const response = await fetch(`/api/v1/trader/market/offers?${params}`);
      const data = await response.json();
      
      setOffers(data.offers || []);
      setStats(data.stats || null);
    } catch (error) {
      console.error('Error fetching offers:', error);
    } finally {
      setLoading(false);
    }
  };

  const clearFilters = () => {
    setFilters({
      molecule: '',
      minPrice: '',
      maxPrice: '',
      minVolume: '',
      location: '',
      certification: '',
      sortBy: 'price',
      sortOrder: 'asc'
    });
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-EU', {
      style: 'currency',
      currency: 'EUR',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(value);
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Market Discovery</h1>
          <p className="text-gray-600 mt-1">Browse and discover green molecules from verified producers</p>
        </div>
        <button
          onClick={() => setShowFilters(!showFilters)}
          className="flex items-center gap-2 px-4 py-2 border rounded-lg hover:bg-gray-50"
        >
          <Filter className="w-5 h-5" />
          {showFilters ? 'Hide Filters' : 'Show Filters'}
        </button>
      </div>

      {/* Market Stats */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
          <div className="bg-white p-4 rounded-lg shadow-sm border">
            <div className="text-gray-600 text-sm font-medium">Total Offers</div>
            <div className="text-2xl font-bold text-gray-900 mt-1">{stats.total_offers}</div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow-sm border">
            <div className="text-gray-600 text-sm font-medium">Available Volume</div>
            <div className="text-2xl font-bold text-blue-600 mt-1">{stats.total_volume_mtpd.toFixed(1)} MTPD</div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow-sm border">
            <div className="text-gray-600 text-sm font-medium">Avg Price</div>
            <div className="text-2xl font-bold text-green-600 mt-1">€{stats.avg_price_eur_kg.toFixed(2)}/kg</div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow-sm border">
            <div className="text-gray-600 text-sm font-medium">Price Range</div>
            <div className="text-2xl font-bold text-gray-900 mt-1">
              €{stats.min_price_eur_kg.toFixed(2)} - €{stats.max_price_eur_kg.toFixed(2)}
            </div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow-sm border">
            <div className="text-gray-600 text-sm font-medium">Molecules</div>
            <div className="text-2xl font-bold text-purple-600 mt-1">{stats.molecules_available.length}</div>
          </div>
        </div>
      )}

      <div className="flex gap-6">
        {/* Filters Sidebar */}
        {showFilters && (
          <div className="w-64 flex-shrink-0 space-y-4">
            <div className="bg-white p-4 rounded-lg shadow-sm border space-y-4">
              <div className="flex justify-between items-center">
                <h3 className="font-semibold text-gray-900">Filters</h3>
                <button
                  onClick={clearFilters}
                  className="text-sm text-blue-600 hover:text-blue-700"
                >
                  Clear All
                </button>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Molecule</label>
                <select
                  value={filters.molecule}
                  onChange={(e) => setFilters({ ...filters, molecule: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg text-sm"
                >
                  <option value="">All Molecules</option>
                  <option value="H2">H2 (Hydrogen)</option>
                  <option value="NH3">NH3 (Ammonia)</option>
                  <option value="CH3OH">CH3OH (Methanol)</option>
                  <option value="SAF">SAF</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Price Range (€/kg)</label>
                <div className="flex gap-2">
                  <input
                    type="number"
                    step="0.1"
                    placeholder="Min"
                    value={filters.minPrice}
                    onChange={(e) => setFilters({ ...filters, minPrice: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg text-sm"
                  />
                  <input
                    type="number"
                    step="0.1"
                    placeholder="Max"
                    value={filters.maxPrice}
                    onChange={(e) => setFilters({ ...filters, maxPrice: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg text-sm"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Min Volume (MTPD)</label>
                <input
                  type="number"
                  step="1"
                  placeholder="Any volume"
                  value={filters.minVolume}
                  onChange={(e) => setFilters({ ...filters, minVolume: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg text-sm"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Location</label>
                <input
                  type="text"
                  placeholder="e.g., Germany"
                  value={filters.location}
                  onChange={(e) => setFilters({ ...filters, location: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg text-sm"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Certification</label>
                <select
                  value={filters.certification}
                  onChange={(e) => setFilters({ ...filters, certification: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg text-sm"
                >
                  <option value="">Any Certification</option>
                  <option value="RED III">RED III</option>
                  <option value="RFNBO">RFNBO</option>
                  <option value="45V">45V (US)</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Sort By</label>
                <select
                  value={filters.sortBy}
                  onChange={(e) => setFilters({ ...filters, sortBy: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg text-sm"
                >
                  <option value="price">Price</option>
                  <option value="volume">Volume</option>
                  <option value="delivery_start">Delivery Date</option>
                </select>
              </div>
            </div>
          </div>
        )}

        {/* Offers Grid */}
        <div className="flex-1">
          {loading ? (
            <div className="bg-white rounded-lg shadow-sm border p-8 text-center">
              <div className="text-gray-500">Loading offers...</div>
            </div>
          ) : offers.length === 0 ? (
            <div className="bg-white rounded-lg shadow-sm border p-8 text-center">
              <FileText className="w-12 h-12 text-gray-400 mx-auto mb-4" />
              <p className="text-gray-600">No offers match your criteria</p>
              <button
                onClick={clearFilters}
                className="mt-4 text-blue-600 hover:text-blue-700 font-medium"
              >
                Clear filters
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {offers.map((offer) => (
                <div
                  key={offer.id}
                  className="bg-white rounded-lg shadow-sm border p-6 hover:shadow-md transition-shadow cursor-pointer"
                  onClick={() => setSelectedOffer(offer)}
                >
                  <div className="flex justify-between items-start mb-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-xl font-bold text-gray-900">{offer.molecule}</h3>
                        <span className={`px-2 py-1 rounded text-xs font-medium ${
                          offer.offer_type === 'firm' 
                            ? 'bg-green-100 text-green-700' 
                            : 'bg-yellow-100 text-yellow-700'
                        }`}>
                          {offer.offer_type}
                        </span>
                      </div>
                      <p className="text-sm text-gray-600 mt-1">{offer.producer_info.project_name}</p>
                    </div>
                    <div className="text-right">
                      <div className="text-2xl font-bold text-blue-600">
                        €{offer.price_eur_kg.toFixed(2)}
                      </div>
                      <div className="text-sm text-gray-500">per kg</div>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3 mb-4 text-sm">
                    <div className="flex items-center gap-2">
                      <TrendingUp className="w-4 h-4 text-gray-400" />
                      <div>
                        <div className="text-gray-500">Volume</div>
                        <div className="font-semibold">{offer.volume_mtpd} MTPD</div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Calendar className="w-4 h-4 text-gray-400" />
                      <div>
                        <div className="text-gray-500">Delivery</div>
                        <div className="font-semibold">{offer.tenor_years.toFixed(1)} years</div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <MapPin className="w-4 h-4 text-gray-400" />
                      <div>
                        <div className="text-gray-500">Location</div>
                        <div className="font-semibold">{offer.location || 'N/A'}</div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <DollarSign className="w-4 h-4 text-gray-400" />
                      <div>
                        <div className="text-gray-500">Total Value</div>
                        <div className="font-semibold">{formatCurrency(offer.total_value_eur)}</div>
                      </div>
                    </div>
                  </div>

                  {offer.compliance_certifications && offer.compliance_certifications.length > 0 && (
                    <div className="flex flex-wrap gap-2 mb-4">
                      {offer.compliance_certifications.map((cert, i) => (
                        <span key={i} className="inline-flex items-center gap-1 px-2 py-1 bg-green-50 text-green-700 text-xs rounded">
                          <Award className="w-3 h-3" />
                          {cert}
                        </span>
                      ))}
                    </div>
                  )}

                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      alert('Request Quote functionality coming soon!');
                    }}
                    className="w-full py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                  >
                    Request Quote
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Offer Detail Modal */}
      {selectedOffer && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg max-w-3xl w-full max-h-[90vh] overflow-y-auto p-6">
            <div className="flex justify-between items-start mb-4">
              <div>
                <h2 className="text-2xl font-bold text-gray-900">{selectedOffer.molecule} Offer</h2>
                <p className="text-gray-600 mt-1">{selectedOffer.producer_info.project_name}</p>
              </div>
              <button
                onClick={() => setSelectedOffer(null)}
                className="text-gray-400 hover:text-gray-600 text-2xl"
              >
                ✕
              </button>
            </div>

            <div className="space-y-6">
              <div className="bg-blue-50 p-4 rounded-lg">
                <div className="text-sm text-gray-600 mb-1">Price per kilogram</div>
                <div className="text-4xl font-bold text-blue-600">€{selectedOffer.price_eur_kg.toFixed(2)}</div>
                <div className="text-sm text-gray-600 mt-2">
                  Total contract value: {formatCurrency(selectedOffer.total_value_eur)}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-sm font-medium text-gray-600 mb-1">Volume</div>
                  <div className="text-xl font-bold">{selectedOffer.volume_mtpd} MTPD</div>
                </div>
                <div>
                  <div className="text-sm font-medium text-gray-600 mb-1">Delivery Period</div>
                  <div className="text-xl font-bold">{selectedOffer.tenor_years.toFixed(1)} years</div>
                  <div className="text-sm text-gray-500">
                    {selectedOffer.delivery_start} to {selectedOffer.delivery_end}
                  </div>
                </div>
              </div>

              <div>
                <div className="text-sm font-medium text-gray-600 mb-1">Location</div>
                <div className="text-lg">{selectedOffer.location || 'Not specified'}</div>
              </div>

              {selectedOffer.compliance_certifications && selectedOffer.compliance_certifications.length > 0 && (
                <div>
                  <div className="text-sm font-medium text-gray-600 mb-2">Compliance Certifications</div>
                  <div className="flex flex-wrap gap-2">
                    {selectedOffer.compliance_certifications.map((cert, i) => (
                      <span key={i} className="px-3 py-2 bg-green-50 text-green-700 rounded-lg font-medium">
                        {cert}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex gap-3 pt-4">
                <button
                  onClick={() => alert('Request Quote functionality coming soon!')}
                  className="flex-1 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium"
                >
                  Request Quote
                </button>
                <button
                  onClick={() => setSelectedOffer(null)}
                  className="px-6 py-3 border rounded-lg hover:bg-gray-50"
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
};

export default MarketDiscoveryPage;
