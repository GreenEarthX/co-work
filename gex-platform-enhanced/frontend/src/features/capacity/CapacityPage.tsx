import { useState, useEffect } from 'react'
import { Box, Save, Trash2 } from 'lucide-react'
import { capacitiesAPI } from '@/lib/api'

export function CapacityPage() {
  const [capacities, setCapacities] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [formData, setFormData] = useState({
    project_name: '',
    molecule: 'H2',
    capacity_mtpd: '',
    start_date: '',
    end_date: '',
  })

  // Load capacities on mount
  useEffect(() => {
    loadCapacities()
  }, [])

  const loadCapacities = async () => {
    try {
      const response = await capacitiesAPI.list()
      setCapacities(response.capacities || [])
    } catch (error) {
      console.error('Failed to load capacities:', error)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)

    try {
      const data = {
        ...formData,
        capacity_mtpd: parseFloat(formData.capacity_mtpd),
      }
      
      await capacitiesAPI.create(data)
      
      // Reset form
      setFormData({
        project_name: '',
        molecule: 'H2',
        capacity_mtpd: '',
        start_date: '',
        end_date: '',
      })
      
      // Reload list
      await loadCapacities()
      
      alert('✅ Capacity created successfully!')
    } catch (error) {
      console.error('Failed to create capacity:', error)
      alert('❌ Failed to create capacity')
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this capacity?')) return

    try {
      await capacitiesAPI.delete(id)
      await loadCapacities()
    } catch (error) {
      console.error('Failed to delete capacity:', error)
    }
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Create Form */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-lg bg-brand/10 flex items-center justify-center">
            <Box className="w-5 h-5 text-brand" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-gray-900">Production Capacity</h2>
            <p className="text-sm text-gray-500">Define your production baseline</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Project Name
              </label>
              <input
                type="text"
                required
                value={formData.project_name}
                onChange={(e) => setFormData({ ...formData, project_name: e.target.value })}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand focus:border-transparent"
                placeholder="e.g., Hanover Green H2"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Molecule
              </label>
              <select
                value={formData.molecule}
                onChange={(e) => setFormData({ ...formData, molecule: e.target.value })}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand focus:border-transparent"
              >
                <option value="H2">H2 (Hydrogen)</option>
                <option value="NH3">NH3 (Ammonia)</option>
                <option value="SAF">SAF (Sustainable Aviation Fuel)</option>
                <option value="eMeOH">eMeOH (e-Methanol)</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Capacity (MTPD)
              </label>
              <input
                type="number"
                required
                step="0.1"
                value={formData.capacity_mtpd}
                onChange={(e) => setFormData({ ...formData, capacity_mtpd: e.target.value })}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand focus:border-transparent"
                placeholder="50.0"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Start Date
              </label>
              <input
                type="date"
                required
                value={formData.start_date}
                onChange={(e) => setFormData({ ...formData, start_date: e.target.value })}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand focus:border-transparent"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                End Date (optional)
              </label>
              <input
                type="date"
                value={formData.end_date}
                onChange={(e) => setFormData({ ...formData, end_date: e.target.value })}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand focus:border-transparent"
              />
            </div>
          </div>

          <div className="flex gap-3">
            <button
              type="submit"
              disabled={loading}
              className="flex items-center gap-2 px-6 py-2 bg-brand text-white rounded-lg hover:bg-brand-dark transition-colors disabled:opacity-50"
            >
              <Save className="w-4 h-4" />
              {loading ? 'Creating...' : 'Create Capacity'}
            </button>
          </div>
        </form>
      </div>

      {/* Capacities List */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="text-lg font-bold text-gray-900 mb-4">
          Existing Capacities ({capacities.length})
        </h3>

        {capacities.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            No capacities yet. Create your first one above!
          </div>
        ) : (
          <div className="space-y-3">
            {capacities.map((capacity) => (
              <div
                key={capacity.id}
                className="flex items-center justify-between p-4 border border-gray-200 rounded-lg hover:bg-gray-50"
              >
                <div className="flex-1">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-brand/10 flex items-center justify-center">
                      <Box className="w-5 h-5 text-brand" />
                    </div>
                    <div>
                      <h4 className="font-semibold text-gray-900">{capacity.project_name}</h4>
                      <p className="text-sm text-gray-500">
                        {capacity.molecule} • {capacity.capacity_mtpd} MTPD • {capacity.start_date}
                      </p>
                    </div>
                  </div>
                </div>

                <button
                  onClick={() => handleDelete(capacity.id)}
                  className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}