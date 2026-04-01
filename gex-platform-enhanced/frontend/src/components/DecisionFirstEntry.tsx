/**
 * DecisionFirstEntry — decision-first home screen entry point.
 * "What are you trying to figure out today?" with 4 persona paths.
 * Replaces the static onboarding banner on the main Dashboard.
 */
import { useNavigate } from 'react-router-dom'
import { TrendingUp, ShieldCheck, Zap, FileSearch } from 'lucide-react'

interface PersonaPath {
  id: string
  question: string
  subtitle: string
  route: string
  color: string
  border: string
  iconBg: string
  textColor: string
  Icon: React.ElementType
}

const PERSONA_PATHS: PersonaPath[] = [
  {
    id: 'finance',
    question: 'Is this project bankable?',
    subtitle: 'Bankability scores, deal-killers, stage gates',
    route: '/finance-dashboard',
    color: 'from-emerald-50 to-white',
    border: 'border-emerald-200 hover:border-emerald-400',
    iconBg: 'bg-emerald-100',
    textColor: 'text-emerald-700',
    Icon: TrendingUp,
  },
  {
    id: 'insurance',
    question: 'What risk is uninsured?',
    subtitle: 'Coverage lines, exposure register, molecule hazard',
    route: '/insurance-coverage',
    color: 'from-sky-50 to-white',
    border: 'border-sky-200 hover:border-sky-400',
    iconBg: 'bg-sky-100',
    textColor: 'text-sky-700',
    Icon: ShieldCheck,
  },
  {
    id: 'engineer',
    question: 'What gates are still open?',
    subtitle: 'Evidence progress, HAZOP status, permit milestones',
    route: '/stage-gates',
    color: 'from-violet-50 to-white',
    border: 'border-violet-200 hover:border-violet-400',
    iconBg: 'bg-violet-100',
    textColor: 'text-violet-700',
    Icon: Zap,
  },
  {
    id: 'banker',
    question: 'Where is capital committed?',
    subtitle: 'Term sheets, credit approvals, commitment pipeline',
    route: '/finance/capital-stack',
    color: 'from-amber-50 to-white',
    border: 'border-amber-200 hover:border-amber-400',
    iconBg: 'bg-amber-100',
    textColor: 'text-amber-700',
    Icon: FileSearch,
  },
]

export function DecisionFirstEntry() {
  const navigate = useNavigate()

  return (
    <div className="rounded-2xl border border-gray-200 bg-white overflow-hidden shadow-sm">
      <div className="px-6 py-4 border-b border-gray-100 bg-gray-50">
        <h2 className="text-base font-black text-gray-900">What are you trying to figure out today?</h2>
        <p className="text-xs text-gray-500 mt-0.5">Jump straight to the answer — no menu hunting.</p>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 divide-x divide-y md:divide-y-0 divide-gray-100">
        {PERSONA_PATHS.map(path => {
          const { Icon } = path
          return (
            <button
              key={path.id}
              type="button"
              onClick={() => navigate(path.route)}
              className={`flex flex-col items-start gap-3 p-5 text-left bg-gradient-to-br ${path.color} border-0 hover:shadow-sm transition-all group`}
            >
              <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${path.iconBg}`}>
                <Icon className={`w-4 h-4 ${path.textColor}`} />
              </div>
              <div>
                <div className={`text-sm font-bold ${path.textColor} group-hover:underline`}>
                  {path.question}
                </div>
                <div className="text-xs text-gray-500 mt-0.5 leading-snug">{path.subtitle}</div>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
