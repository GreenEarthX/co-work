import { useState, useEffect } from 'react'
import { RefreshCw, Plus, Filter, ChevronRight, AlertTriangle } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { capacitiesAPI, offersAPI, tokensAPI, matchingAPI } from '@/lib/api'

interface ProjectFlow {
  name: string
  molecule: string
  stage1_capacity: number
  stage2_tokenised: number
  stage3_market: number
  stage3_matched: number
  capacityIds: string[]
}

export function DashboardPage() {
  const navigate = useNavigate()
  const [projects, setProjects] = useState<ProjectFlow[]>([])
  const [selectedProject, setSelectedProject] = useState<string>('all')
  const [loading, setLoading] = useState(true)
  const [errors, setErrors] = useState<string[]>([])
  const [aggregates, setAggregates] = useState({
    totalCapacity: 0,
    totalTokenised: 0,
    totalMarket: 0,
    totalMatches: 0,
    conversionRate: 0,
  })

  useEffect(() => { loadData() }, [])

  const loadData = async () => {
    setLoading(true)
    setErrors([])
    const errs: string[] = []

    // Load each API independently — don't let one failure kill the whole dashboard
    let capacities: any[] = []
    let tokens: any[] = []
    let offers: any[] = []
    let matches: any[] = []

    try {
      const res = await capacitiesAPI.list()
      capacities = res.capacities || res.data || (Array.isArray(res) ? res : [])
    } catch { errs.push('capacities') }

    try {
      const res = await tokensAPI.list()
      tokens = res.tokens || res.data || (Array.isArray(res) ? res : [])
    } catch { errs.push('tokens') }

    try {
      const res = await offersAPI.list()
      offers = res.offers || res.data || (Array.isArray(res) ? res : [])
    } catch { errs.push('offers') }

    try {
      const res = await matchingAPI.list()
      matches = res.matches || res.data || (Array.isArray(res) ? res : [])
    } catch { errs.push('matches') }

    // Build project map from whatever data we got
    const projectMap = new Map<string, ProjectFlow>()

    capacities.forEach((cap: any) => {
      const pname = cap.project_name || cap.name || 'Unknown Project'
      if (!projectMap.has(pname)) {
        projectMap.set(pname, {
          name: pname,
          molecule: cap.molecule || cap.product || 'H2',
          stage1_capacity: 0,
          stage2_tokenised: 0,
          stage3_market: 0,
          stage3_matched: 0,
          capacityIds: [],
        })
      }
      const proj = projectMap.get(pname)!
      proj.stage1_capacity += (cap.capacity_mtpd || cap.volume || 0)
      proj.capacityIds.push(cap.id)
    })

    // Map tokens to projects
    tokens.forEach((tok: any) => {
      const capId = tok.capacity_id
      for (const proj of projectMap.values()) {
        if (proj.capacityIds.includes(capId)) {
          proj.stage2_tokenised += (tok.volume_mt || tok.volume || 0)
          break
        }
      }
    })

    // Map offers to projects
    offers.forEach((off: any) => {
      const pname = off.project || off.project_name
      if (pname && projectMap.has(pname)) {
        const proj = projectMap.get(pname)!
        proj.stage3_market += parseFloat(off.volume || '0')
      }
    })

    const projectsArray = Array.from(projectMap.values())
    setProjects(projectsArray)
    setErrors(errs)

    const totalCap = projectsArray.reduce((s, p) => s + p.stage1_capacity, 0)
    const totalMarket = projectsArray.reduce((s, p) => s + p.stage3_market, 0)

    setAggregates({
      totalCapacity: totalCap,
      totalTokenised: projectsArray.reduce((s, p) => s + p.stage2_tokenised, 0),
      totalMarket: totalMarket,
      totalMatches: matches.length,
      conversionRate: totalCap > 0 ? (totalMarket / totalCap) * 100 : 0,
    })

    setLoading(false)
  }

  const filteredProjects = selectedProject === 'all'
    ? projects
    : projects.filter(p => p.name === selectedProject)

  return (
    <div className="space-y-6">
      {/* ONBOARDING BANNER */}
      <div className="p-6 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl border-2 border-blue-200">
        <div className="flex items-center justify-between">
          <div className="flex-1">
            <h2 className="text-2xl font-bold text-gray-900 mb-2">Planning a New Project?</h2>
            <p className="text-gray-700 mb-3 max-w-2xl">
              Get instant viability assessment including market demand,
              financing feasibility, and subsidy eligibility in 5 minutes!
            </p>
            <button
              onClick={() => navigate('/onboarding')}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 flex items-center gap-2"
            >
              <Plus className="w-4 h-4" />
              Start Project Viability Check
            </button>
          </div>
        </div>
      </div>

      {/* HEADER WITH FILTERS */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black text-gray-900">Dashboard</h1>
          <p className="text-sm text-gray-600 mt-1">Production flow &amp; conversion metrics</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-gray-400" />
            <select
              value={selectedProject}
              onChange={(e) => setSelectedProject(e.target.value)}
              className="px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium bg-white"
            >
              <option value="all">All Projects</option>
              {projects.map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
            </select>
          </div>
          <button onClick={loadData} disabled={loading} className="p-2 hover:bg-gray-100 rounded-lg">
            <RefreshCw className={`w-5 h-5 text-gray-600 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* API WARNINGS (non-blocking) */}
      {errors.length > 0 && (
        <div className="flex items-center gap-2 px-4 py-2 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-700">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span>Some data unavailable ({errors.join(', ')}). Showing what loaded successfully.</span>
        </div>
      )}

      {/* AGGREGATE KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {[
          { label: 'Total Capacity', value: `${aggregates.totalCapacity.toFixed(0)} MTPD`, color: 'text-blue-600' },
          { label: 'Tokenised', value: `${aggregates.totalTokenised.toFixed(0)} MT`, color: 'text-indigo-600' },
          { label: 'On Market', value: `${aggregates.totalMarket.toFixed(0)} MT`, color: 'text-green-600' },
          { label: 'Matches', value: `${aggregates.totalMatches}`, color: 'text-amber-600' },
          { label: 'Conversion', value: `${aggregates.conversionRate.toFixed(1)}%`, color: 'text-emerald-600' },
        ].map(kpi => (
          <div key={kpi.label} className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="text-xs font-bold text-gray-500 uppercase">{kpi.label}</div>
            <div className={`text-2xl font-black ${kpi.color} mt-1`}>{kpi.value}</div>
          </div>
        ))}
      </div>

      {/* LOADING STATE */}
      {loading && (
        <div className="text-center py-12 text-gray-500">
          <RefreshCw className="w-8 h-8 animate-spin mx-auto mb-3 text-blue-500" />
          Loading project data...
        </div>
      )}

      {/* EMPTY STATE */}
      {!loading && projects.length === 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <h3 className="text-lg font-bold text-gray-900 mb-2">No Projects Yet</h3>
          <p className="text-gray-600 mb-4">Create your first project to see it here.</p>
          <button onClick={() => navigate('/capacity')} className="px-6 py-2 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700">
            Create Capacity
          </button>
        </div>
      )}

      {/* PROJECT CARDS */}
      {filteredProjects.map((project) => (
        <div key={project.name} className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
          <div className="px-6 py-4 bg-gray-50 border-b border-gray-100 flex justify-between items-center">
            <div>
              <h2 className="text-xl font-black text-gray-900">{project.name}</h2>
              <span className="text-sm text-gray-500">{project.molecule}</span>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-right">
                <div className="text-xs text-gray-500 uppercase tracking-wider">Total Pipeline</div>
                <div className="text-3xl font-black text-blue-600">{project.stage1_capacity.toFixed(0)} <span className="text-sm">MTPD</span></div>
              </div>
              <button
                onClick={() => navigate(`/projects?name=${encodeURIComponent(project.name)}`)}
                className="p-2 hover:bg-gray-200 rounded-lg"
                title="View project details"
              >
                <ChevronRight className="w-5 h-5 text-gray-400" />
              </button>
            </div>
          </div>

          <div className="p-6">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
              {/* Stage 1: Capacity */}
              <div className="space-y-2">
                <div className="flex justify-between text-xs font-bold text-gray-500 uppercase">
                  <span>1. Capacity</span>
                  <span className="text-green-600">Created</span>
                </div>
                <div className="text-3xl font-black text-gray-900">{project.stage1_capacity.toFixed(0)}<span className="text-sm font-normal text-gray-400 ml-1">MTPD</span></div>
              </div>

              {/* Stage 2: Tokenised */}
              <div className="space-y-2">
                <div className="flex justify-between text-xs font-bold text-gray-500 uppercase">
                  <span>2. Tokenised</span>
                  <span className={project.stage2_tokenised > 0 ? 'text-blue-600' : 'text-gray-400'}>
                    {project.stage2_tokenised > 0 ? 'Active' : 'Pending'}
                  </span>
                </div>
                <div className="text-3xl font-black text-gray-900">
                  {project.stage2_tokenised > 0 ? project.stage2_tokenised.toFixed(0) : '—'}
                  <span className="text-sm font-normal text-gray-400 ml-1">MT</span>
                </div>
              </div>

              {/* Stage 3: Market */}
              <div className="space-y-2">
                <div className="flex justify-between text-xs font-bold text-gray-500 uppercase">
                  <span>3. On Market</span>
                  <span className={project.stage3_market > 0 ? 'text-green-600' : 'text-gray-400'}>
                    {project.stage3_market > 0 ? 'Live' : '—'}
                  </span>
                </div>
                <div className="text-3xl font-black text-gray-900">
                  {project.stage3_market > 0 ? project.stage3_market.toFixed(0) : '—'}
                  <span className="text-sm font-normal text-gray-400 ml-1">MT</span>
                </div>
              </div>

              {/* Stage 4: Matched */}
              <div className="space-y-2">
                <div className="flex justify-between text-xs font-bold text-gray-500 uppercase">
                  <span>4. Matched</span>
                  <span className="text-gray-400">{project.stage3_matched > 0 ? 'Active' : '—'}</span>
                </div>
                <div className="text-3xl font-black text-gray-900">
                  {project.stage3_matched > 0 ? project.stage3_matched.toFixed(0) : '—'}
                </div>
              </div>
            </div>

            {/* Conversion funnel bar */}
            <div className="mt-4 flex items-center gap-1 h-2">
              <div className="bg-blue-500 h-full rounded-l" style={{ width: '100%' }} title="Capacity" />
              <div className="bg-indigo-500 h-full" style={{ width: `${project.stage1_capacity > 0 ? (project.stage2_tokenised / project.stage1_capacity) * 100 : 0}%` }} title="Tokenised" />
              <div className="bg-green-500 h-full" style={{ width: `${project.stage1_capacity > 0 ? (project.stage3_market / project.stage1_capacity) * 100 : 0}%` }} title="Market" />
              <div className="bg-amber-500 h-full rounded-r" style={{ width: '0%' }} title="Matched" />
            </div>
          </div>
        </div>
      ))}

      {/* BANKING READINESS */}
      <div className="bg-gradient-to-br from-emerald-50 to-white rounded-xl border border-emerald-200 p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-lg font-bold text-gray-900">Banking Readiness</h3>
            <p className="text-sm text-gray-600">Institutional financing metrics across portfolio</p>
          </div>
          <button onClick={() => navigate('/finance-dashboard')} className="text-sm text-emerald-600 hover:underline font-semibold flex items-center gap-1">
            Finance Dashboard <ChevronRight className="w-4 h-4" />
          </button>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          {[
            { label: 'DSCR', value: '1.35x', pct: 92, color: 'bg-green-500' },
            { label: 'Evidence', value: '96%', pct: 96, color: 'bg-green-500' },
            { label: 'Offtake', value: '72%', pct: 72, color: 'bg-yellow-500' },
            { label: 'Permits', value: 'Done', pct: 100, color: 'bg-green-500' },
          ].map(metric => (
            <div key={metric.label}>
              <div className="text-sm text-gray-600 mb-1">{metric.label}</div>
              <div className="text-xl font-black text-gray-900">{metric.value}</div>
              <div className="w-full bg-gray-200 rounded-full h-1.5 mt-2">
                <div className={`${metric.color} h-1.5 rounded-full`} style={{ width: `${metric.pct}%` }} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
