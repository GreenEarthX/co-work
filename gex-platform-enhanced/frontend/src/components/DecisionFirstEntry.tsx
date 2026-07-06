// Screen: Shared component — Finance decision screens
/**
 * DecisionFirstEntry — decision-first home screen entry point.
 * "What are you trying to figure out today?" with 4 persona paths.
 * Replaces the static onboarding banner on the main Dashboard.
 */
import { useNavigate } from "react-router-dom";

interface PersonaPath {
  id: string;
  question: string;
  subtitle: string;
  route: string;
}

const PERSONA_PATHS: PersonaPath[] = [
  {
    id: "finance",
    question: "Bankability Status",
    subtitle: "Scores, deal-killers, stage gates",
    route: "/finance-dashboard",
  },
  {
    id: "insurance",
    question: "Insurance Status",
    subtitle: "Coverage lines, exposure register, molecule hazard",
    route: "/insurance-coverage",
  },
  {
    id: "engineer",
    question: "Gates Status",
    subtitle: "Evidence progress, HAZOP status, permit milestones",
    route: "/stage-gates",
  },
  {
    id: "banker",
    question: "Capital Commitment",
    subtitle: "Term sheets, credit approvals, commitment pipeline",
    route: "/finance/capital-stack",
  },
];

export function DecisionFirstEntry() {
  const navigate = useNavigate();

  return (
    <div className="space-y-4">
      {/* <div className="rounded-2xl border border-gray-200 bg-white px-6 py-4 shadow-sm">
        <h2 className="text-base font-black text-gray-900">Today</h2>
        <p className="mt-0.5 text-xs text-gray-500">
          Jump straight to the answer.
        </p>
      </div> */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {PERSONA_PATHS.map((path) => (
          <button
            key={path.id}
            type="button"
            onClick={() => navigate(path.route)}
            className="rounded-[28px] border border-slate-200 bg-white px-7 py-6 text-left shadow-sm transition-all hover:border-slate-300 hover:shadow-md"
          >
            <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-slate-500">
              {path.question}
            </div>
            <div className="mt-4 text-base font-semibold leading-snug text-slate-900">
              {path.subtitle}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
