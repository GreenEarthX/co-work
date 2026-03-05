import React, { useState, useEffect } from 'react';
import { Play, Filter, RotateCcw, Target, MapPin, Calendar, DollarSign } from 'lucide-react';

interface MatchingParams {
  molecule: string;
  volume_min: number;
  volume_max: number;
  price_max: number;
  delivery_start: string;
  delivery_end: string;
  location: string;
  purity_min: number;
  ghg_max: number;
}

interface Match {
  id: string;
  supplier: string;
  buyer: string;
  molecule: string;
  volume_mt: number;
  price_eur_kg: number;
  match_score: number;
  location: string;
  delivery_date: string;
}

export function MatchingPage() {
  const [params, setParams] = useState<MatchingParams>({
    molecule: 'H2',
    volume_min: 1000,
    volume_max: 50000,
    price_max: 8.0,
    delivery_start: '2026-06-01',
    delivery_end: '2027-12-31',
    location: 'Hamburg',
    purity_min: 99.5,
    ghg_max: 1.0
  });

  const [matches, setMatches] = useState<Match[]>([]);
  const [isMatching, setIsMatching] = useState(false);
  const [showResults, setShowResults] = useState(false);

  const runMatching = async () => {
    setIsMatching(true);
    setShowResults(false);

    // Simulate matching algorithm
    setTimeout(() => {
      const mockMatches: Match[] = [
        {
          id: 'match_001',
          supplier: 'Hamburg H2 Plant',
          buyer: 'BASF SE',
          molecule: params.molecule,
          volume_mt: 25000,
          price_eur_kg: 6.5,
          match_score: 95,
          location: 'Hamburg Port',
          delivery_date: '2026-09-01'
        },
        {
          id: 'match_002',
          supplier: 'Bremen Wind H2',
          buyer: 'Lufthansa',
          molecule: params.molecule,
          volume_mt: 15000,
          price_eur_kg: 7.2,
          match_score: 87,
          location: 'Bremen',
          delivery_date: '2026-11-15'
        },
        {
          id: 'match_003',
          supplier: 'North Sea Offshore',
          buyer: 'Shell',
          molecule: params.molecule,
          volume_mt: 40000,
          price_eur_kg: 5.8,
          match_score: 78,
          location: 'Rotterdam',
          delivery_date: '2027-01-01'
        }
      ];

      setMatches(mockMatches);
      setIsMatching(false);
      setShowResults(true);
    }, 3000);
  };

  const resetParams = () => {
    setParams({
      molecule: 'H2',
      volume_min: 1000,
      volume_max: 50000,
      price_max: 8.0,
      delivery_start: '2026-06-01',
      delivery_end: '2027-12-31',
      location: 'Hamburg',
      purity_min: 99.5,
      ghg_max: 1.0
    });
    setMatches([]);
    setShowResults(false);
  };

  const getScoreColor = (score: number) => {
    if (score >= 90) return 'text-green-600 bg-green-50';
    if (score >= 75) return 'text-yellow-600 bg-yellow-50';
    return 'text-red-600 bg-red-50';
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black text-gray-900">Intelligent Matching</h1>
          <p className="text-sm text-gray-600 mt-1">Find optimal supply-demand matches</p>
        </div>
        <div className="flex gap-3">
          <button 
            onClick={resetParams}
            className="px-4 py-2 border border-gray-200 text-gray-700 rounded-lg font-medium hover:bg-gray-50 flex items-center gap-2"
          >
            <RotateCcw className="w-4 h-4" />
            Reset
          </button>
          <button 
            onClick={runMatching}
            disabled={isMatching}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 flex items-center gap-2 disabled:opacity-50"
          >
            <Play className="w-4 h-4" />
            {isMatching ? 'Matching...' : 'Run Matching'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Parameters Panel */}
        <div className="lg:col-span-1">
          <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-6">
            <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
              <Filter className="w-5 h-5" />
              Matching Parameters
            </h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Molecule</label>
                <select 
                  value={params.molecule} 
                  onChange={(e) => setParams({...params, molecule: e.target.value})}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg"
                >
                  <option value="H2">Hydrogen (H2)</option>
                  <option value="NH3">Ammonia (NH3)</option>
                  <option value="SAF">Sustainable Aviation Fuel</option>
                  <option value="eMeOH">e-Methanol</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Volume Range (MT)</label>
                <div className="grid grid-cols-2 gap-2">
                  <input 
                    type="number" 
                    placeholder="Min"
                    value={params.volume_min}
                    onChange={(e) => setParams({...params, volume_min: Number(e.target.value)})}
                    className="px-3 py-2 border border-gray-200 rounded-lg" 
                  />
                  <input 
                    type="number" 
                    placeholder="Max"
                    value={params.volume_max}
                    onChange={(e) => setParams({...params, volume_max: Number(e.target.value)})}
                    className="px-3 py-2 border border-gray-200 rounded-lg" 
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Max Price (€/kg)</label>
                <input 
                  type="number" 
                  step="0.1"
                  value={params.price_max}
                  onChange={(e) => setParams({...params, price_max: Number(e.target.value)})}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg" 
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Delivery Period</label>
                <div className="grid grid-cols-2 gap-2">
                  <input 
                    type="date"
                    value={params.delivery_start}
                    onChange={(e) => setParams({...params, delivery_start: e.target.value})}
                    className="px-3 py-2 border border-gray-200 rounded-lg" 
                  />
                  <input 
                    type="date"
                    value={params.delivery_end}
                    onChange={(e) => setParams({...params, delivery_end: e.target.value})}
                    className="px-3 py-2 border border-gray-200 rounded-lg" 
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Location</label>
                <input 
                  type="text"
                  value={params.location}
                  onChange={(e) => setParams({...params, location: e.target.value})}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg" 
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Min Purity (%)</label>
                <input 
                  type="number" 
                  step="0.1"
                  value={params.purity_min}
                  onChange={(e) => setParams({...params, purity_min: Number(e.target.value)})}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg" 
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Max GHG Intensity</label>
                <input 
                  type="number" 
                  step="0.1"
                  value={params.ghg_max}
                  onChange={(e) => setParams({...params, ghg_max: Number(e.target.value)})}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg" 
                />
              </div>
            </div>
          </div>
        </div>

        {/* Results Panel */}
        <div className="lg:col-span-2">
          {isMatching ? (
            <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
              <div className="relative w-32 h-32 mx-auto mb-6">
                {/* Radar Animation */}
                <div className="absolute inset-0 border-2 border-blue-200 rounded-full"></div>
                <div className="absolute inset-2 border border-blue-300 rounded-full"></div>
                <div className="absolute inset-4 border border-blue-400 rounded-full"></div>
                <div className="absolute inset-6 bg-blue-500 rounded-full"></div>
                <div className="absolute inset-0 border-t-2 border-blue-600 rounded-full animate-spin"></div>
                <Target className="absolute inset-0 m-auto w-8 h-8 text-blue-600" />
              </div>
              <h3 className="text-lg font-bold text-gray-900 mb-2">Scanning Market</h3>
              <p className="text-gray-600">Analyzing supply and demand patterns...</p>
            </div>
          ) : showResults ? (
            <div className="space-y-4">
              <div className="bg-white rounded-xl border border-gray-200 p-6">
                <h2 className="text-lg font-bold text-gray-900 mb-4">
                  Found {matches.length} Matches
                </h2>
                <div className="space-y-4">
                  {matches.map(match => (
                    <div key={match.id} className="border border-gray-200 rounded-lg p-4">
                      <div className="flex items-start justify-between mb-3">
                        <div>
                          <div className="font-medium text-gray-900">
                            {match.supplier} → {match.buyer}
                          </div>
                          <div className="text-sm text-gray-500">{match.molecule}</div>
                        </div>
                        <div className={`px-3 py-1 rounded-full text-sm font-medium ${getScoreColor(match.match_score)}`}>
                          {match.match_score}% Match
                        </div>
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                        <div className="flex items-center gap-1">
                          <Target className="w-4 h-4 text-gray-400" />
                          <span>{match.volume_mt.toLocaleString()} MT</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <DollarSign className="w-4 h-4 text-gray-400" />
                          <span>€{match.price_eur_kg}/kg</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <MapPin className="w-4 h-4 text-gray-400" />
                          <span>{match.location}</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <Calendar className="w-4 h-4 text-gray-400" />
                          <span>{match.delivery_date}</span>
                        </div>
                      </div>
                      <div className="mt-3 flex gap-2">
                        <button className="px-3 py-1 bg-blue-50 text-blue-700 rounded text-sm font-medium hover:bg-blue-100">
                          View Details
                        </button>
                        <button className="px-3 py-1 bg-green-50 text-green-700 rounded text-sm font-medium hover:bg-green-100">
                          Create Contract
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
              <div className="text-gray-400 text-6xl mb-4">🎯</div>
              <h3 className="text-lg font-bold text-gray-900 mb-2">Ready to Find Matches</h3>
              <p className="text-gray-600 mb-4">Configure your parameters and run the matching algorithm</p>
              <button 
                onClick={runMatching}
                className="px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700"
              >
                Start Matching
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}