import React, { useState, useEffect } from 'react';
import { TrendingUp, Activity, CheckCircle, AlertCircle } from 'lucide-react';

interface ProductionReading {
  timestamp: string;
  volume_produced: number;
  ghg_intensity: number;
  availability_pct: number;
}

interface Delivery {
  delivery_id: string;
  volume_mt: number;
  quality_verified: boolean;
  title_transferred: boolean;
  payment_received: boolean;
  invoice_amount: number;
}

export default function ProductionDashboard() {
  const [readings, setReadings] = useState<ProductionReading[]>([]);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [availability, setAvailability] = useState<number>(0);

  useEffect(() => {
    // Fetch production data
    fetch('/api/v1/greenmesh/production/proj_hamburg_h2')
      .then(res => res.json())
      .then(data => setReadings(data.readings));

    // Fetch deliveries
    fetch('/api/v1/greenmesh/deliveries/proj_hamburg_h2')
      .then(res => res.json())
      .then(data => setDeliveries(data.deliveries));

    // Fetch availability
    fetch('/api/v1/greenmesh/availability/proj_hamburg_h2')
      .then(res => res.json())
      .then(data => setAvailability(data.availability_pct));
  }, []);

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-black text-gray-900">Production Monitoring</h1>
          <p className="text-sm text-gray-600 mt-1">Real-time facility performance</p>
        </div>

        {/* Metrics Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          {/* Current Production */}
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
                <Activity className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Current Production
                </p>
                <p className="text-2xl font-black text-gray-900">
                  {readings[0]?.volume_produced || 0} MT/day
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-gray-600">GHG Intensity:</span>
              <span className="font-semibold text-gray-900">
                {readings[0]?.ghg_intensity || 0} kg CO₂e/kg
              </span>
            </div>
          </div>

          {/* Availability */}
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-green-50 flex items-center justify-center">
                <TrendingUp className="w-5 h-5 text-green-600" />
              </div>
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Availability
                </p>
                <p className="text-2xl font-black text-gray-900">
                  {availability.toFixed(1)}%
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 text-sm">
              {availability >= 90 ? (
                <>
                  <CheckCircle className="w-4 h-4 text-green-600" />
                  <span className="text-green-600 font-medium">Meets guarantee</span>
                </>
              ) : (
                <>
                  <AlertCircle className="w-4 h-4 text-orange-600" />
                  <span className="text-orange-600 font-medium">Below 90% target</span>
                </>
              )}
            </div>
          </div>

          {/* Deliveries */}
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-purple-50 flex items-center justify-center">
                <CheckCircle className="w-5 h-5 text-purple-600" />
              </div>
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Deliveries
                </p>
                <p className="text-2xl font-black text-gray-900">
                  {deliveries.length}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-gray-600">Awaiting payment:</span>
              <span className="font-semibold text-gray-900">
                {deliveries.filter(d => !d.payment_received).length}
              </span>
            </div>
          </div>
        </div>

        {/* Deliveries Table */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200">
            <h2 className="text-lg font-bold text-gray-900">Recent Deliveries</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Delivery ID
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Volume
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Quality
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Title
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Payment
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Amount
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {deliveries.map(delivery => (
                  <tr key={delivery.delivery_id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 text-sm font-medium text-gray-900">
                      {delivery.delivery_id}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600">
                      {delivery.volume_mt.toLocaleString()} MT
                    </td>
                    <td className="px-6 py-4">
                      {delivery.quality_verified ? (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-green-50 text-green-700 text-xs font-medium">
                          <CheckCircle className="w-3 h-3" />
                          Verified
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-gray-100 text-gray-600 text-xs font-medium">
                          Pending
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      {delivery.title_transferred ? (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-blue-50 text-blue-700 text-xs font-medium">
                          <CheckCircle className="w-3 h-3" />
                          Transferred
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-gray-100 text-gray-600 text-xs font-medium">
                          Pending
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      {delivery.payment_received ? (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-green-50 text-green-700 text-xs font-medium">
                          <CheckCircle className="w-3 h-3" />
                          Received
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-orange-50 text-orange-700 text-xs font-medium">
                          <AlertCircle className="w-3 h-3" />
                          Awaiting
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-sm font-semibold text-gray-900">
                      €{(delivery.invoice_amount / 1000000).toFixed(1)}M
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}