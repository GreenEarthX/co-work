// Screen: Offtake quality screen (/offtake-quality, /finance/offtake-quality)
import { useState, useEffect } from "react";
import {
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Wrench,
  Info,
} from "lucide-react";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import { HELP, TAB_DESCRIPTIONS } from "@/config/helpText";
import { useSelectedProject } from "@/contexts/ProjectContext";
import { useVisibleProjects } from "@/hooks/useVisibleProjects";
import type { CustomerProject } from "@/data/customerProjects";

// ═══════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════

type TestResult = "PASS" | "PASS_WITH_NOTE" | "FAIL";

interface OfftakeTest {
  id: string;
  label: string;
  result: TestResult;
  score: number;
  detail: string;
}

interface ProjectOfftake {
  overall: number;
  tests: OfftakeTest[];
  redFlags: string[];
  remedies: string[];
}

// ═══════════════════════════════════════════════════════════════
// DEMO DATA
// ═══════════════════════════════════════════════════════════════

const OFFTAKE_DATA: Record<string, ProjectOfftake> = {
  proj_le_havre_eng: {
    overall: 94,
    tests: [
      {
        id: "TENOR",
        label: "Tenor Match",
        result: "PASS",
        score: 100,
        detail:
          "20y offtake exceeds 15y debt by 5 years. Extension option included.",
      },
      {
        id: "CREDIT",
        label: "Counterparty Credit",
        result: "PASS",
        score: 98,
        detail:
          "GRTgaz AA- regulated utility + state backstop. Best-in-class counterparty.",
      },
      {
        id: "VOLUME_FIRMNESS",
        label: "Volume Firmness",
        result: "PASS",
        score: 95,
        detail:
          "92% contracted. Take-or-pay with force majeure curtailment protocol. Storage buffer confirmed.",
      },
      {
        id: "PRICING_INDEXATION",
        label: "Pricing & Indexation",
        result: "PASS",
        score: 90,
        detail:
          "TTF + green premium + capacity payment. Floor covers DSCR at P90. Reopener at year 10.",
      },
      {
        id: "CURTAILMENT_SHAPE",
        label: "Curtailment Shape",
        result: "PASS",
        score: 88,
        detail:
          "Pipeline injection with 8h buffer tank. Curtailment compensation clause at €0.85/kg.",
      },
    ],
    redFlags: [],
    remedies: [],
  },
  proj_bremen_h2: {
    overall: 79,
    tests: [
      {
        id: "TENOR",
        label: "Tenor Match",
        result: "PASS",
        score: 95,
        detail:
          "15y offtake matches 15y debt. 2-year extension option recommended.",
      },
      {
        id: "CREDIT",
        label: "Counterparty Credit",
        result: "PASS",
        score: 88,
        detail:
          "Vattenfall BBB+ + parent guarantee. Acceptable for senior lender.",
      },
      {
        id: "VOLUME_FIRMNESS",
        label: "Volume Firmness",
        result: "PASS_WITH_NOTE",
        score: 72,
        detail:
          "78% contracted. Take-or-pay but no make-good clause. Second offtaker for remaining 22% needed.",
      },
      {
        id: "PRICING_INDEXATION",
        label: "Pricing & Indexation",
        result: "PASS",
        score: 82,
        detail:
          "ICIS H₂ NWE + logistics escalator. Floor at €1.55/kg covers DSCR minimum.",
      },
      {
        id: "CURTAILMENT_SHAPE",
        label: "Curtailment Shape",
        result: "PASS_WITH_NOTE",
        score: 58,
        detail:
          "No dedicated H₂ storage on-site. Port tank access via off-take agreement — acceptable but fragile.",
      },
    ],
    redFlags: [
      "78% contracted below 85% target — second offtaker required",
      "No make-good clause — add to next offtake amendment",
      "Storage dependency on port operator creates single point of failure",
    ],
    remedies: [
      "Execute binding LOI with industrial H₂ user (refinery or transport hub) for remaining 22%",
      "Add make-good clause and outage protocol in next amendment",
      "Negotiate dedicated H₂ storage slot at port or install 500kg buffer tank",
    ],
  },
  proj_helios_emethanol: {
    overall: 62,
    tests: [
      {
        id: "TENOR",
        label: "Tenor Match",
        result: "PASS",
        score: 85,
        detail:
          "12y Maersk contract vs 15y debt — 3-year tail exposure. Recommend extension or balloon.",
      },
      {
        id: "CREDIT",
        label: "Counterparty Credit",
        result: "PASS",
        score: 88,
        detail:
          "Maersk A- direct. Strong counterparty but shipping demand is volume-cyclical.",
      },
      {
        id: "VOLUME_FIRMNESS",
        label: "Volume Firmness",
        result: "PASS_WITH_NOTE",
        score: 55,
        detail:
          "60% contracted. Maersk shipping volumes subject to route changes. Need volume firmness clause.",
      },
      {
        id: "PRICING_INDEXATION",
        label: "Pricing & Indexation",
        result: "PASS_WITH_NOTE",
        score: 60,
        detail:
          "ICIS Methanol NWE with carbon premium — good structure but premium schedule not fixed.",
      },
      {
        id: "CURTAILMENT_SHAPE",
        label: "Curtailment Shape",
        result: "PASS_WITH_NOTE",
        score: 22,
        detail:
          "No curtailment compensation clause. CO₂ feedstock interruption creates double exposure. Critical gap.",
      },
    ],
    redFlags: [
      "Offtake tenor 3 years short of debt — balloon risk",
      "60% contracted below 70% minimum",
      "No curtailment compensation — gas methanol synthesis cannot ramp quickly",
      "Carbon premium schedule undefined — revenue uncertainty in model",
    ],
    remedies: [
      "Add 3-year extension option to Maersk contract aligned with debt amortization tail",
      "Engage Shell Chemicals or HELM as second offtaker for 20–25%",
      "Insert curtailment compensation at €180/tonne missed delivery",
      "Fix carbon premium schedule: ICIS Methanol + €120/tonne CO₂ certificate",
    ],
  },
  proj_rotterdam_nh3: {
    overall: 38,
    tests: [
      {
        id: "TENOR",
        label: "Tenor Match",
        result: "FAIL",
        score: 30,
        detail:
          "10y contract vs 15y debt — 5-year unsecured tail. Unacceptable for senior lending.",
      },
      {
        id: "CREDIT",
        label: "Counterparty Credit",
        result: "PASS_WITH_NOTE",
        score: 55,
        detail:
          "Yara subsidiary BB — below BBB- threshold. Parent guarantee not yet confirmed.",
      },
      {
        id: "VOLUME_FIRMNESS",
        label: "Volume Firmness",
        result: "FAIL",
        score: 20,
        detail:
          "35% contracted. No take-or-pay. LOI only — not binding. Cannot be modelled as revenue.",
      },
      {
        id: "PRICING_INDEXATION",
        label: "Pricing & Indexation",
        result: "PASS_WITH_NOTE",
        score: 48,
        detail:
          "Argus NH₃ FOB Rotterdam — market index acceptable but no floor or collar in place.",
      },
      {
        id: "CURTAILMENT_SHAPE",
        label: "Curtailment Shape",
        result: "FAIL",
        score: 15,
        detail:
          "No curtailment provisions. NH₃ cannot be vented — storage critical but not costed.",
      },
    ],
    redFlags: [
      "Offtake tenor 5 years below debt — cannot be financed as structured",
      "35% contracted — project cannot reach financial close",
      "Yara subsidiary credit insufficient — need Yara AG parent guarantee",
      "No NH₃ storage plan — curtailment creates safety + liability exposure",
      "No pricing floor — full NH₃ price risk passed to model",
    ],
    remedies: [],
  },
  proj_wales_saf: {
    overall: 22,
    tests: [
      {
        id: "TENOR",
        label: "Tenor Match",
        result: "FAIL",
        score: 15,
        detail: "8y LOI vs undefined debt tenor. Cannot be structured.",
      },
      {
        id: "CREDIT",
        label: "Counterparty Credit",
        result: "FAIL",
        score: 20,
        detail:
          "Regional airline B+ credit. No parent guarantee. LOI non-binding.",
      },
      {
        id: "VOLUME_FIRMNESS",
        label: "Volume Firmness",
        result: "FAIL",
        score: 10,
        detail:
          "20% contracted, LOI only. Project cannot reach financial close at this coverage level.",
      },
      {
        id: "PRICING_INDEXATION",
        label: "Pricing & Indexation",
        result: "PASS_WITH_NOTE",
        score: 35,
        detail:
          "Platts Jet + SAF premium is the right index. But no binding pricing terms — LOI only.",
      },
      {
        id: "CURTAILMENT_SHAPE",
        label: "Curtailment Shape",
        result: "FAIL",
        score: 5,
        detail:
          "No curtailment plan. SAF Fischer-Tropsch cannot modulate quickly. No storage defined.",
      },
    ],
    redFlags: [
      "Project not bankable at current offtake coverage (20%)",
      "No binding offtake — all LOIs",
      "DSCR 0.98 at base case — below covenant minimum before any offtake stress",
      "No major airline or fuel buyer engaged",
    ],
    remedies: [],
  },
};

// ═══════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════

const RESULT_META: Record<
  TestResult,
  { label: string; bg: string; text: string; icon: React.ReactNode }
> = {
  PASS: {
    label: "PASS",
    bg: "bg-green-100",
    text: "text-green-700",
    icon: <CheckCircle2 size={14} className="text-green-600" />,
  },
  PASS_WITH_NOTE: {
    label: "PASS W/ NOTE",
    bg: "bg-amber-100",
    text: "text-amber-700",
    icon: <Info size={14} className="text-amber-600" />,
  },
  FAIL: {
    label: "FAIL",
    bg: "bg-red-100",
    text: "text-red-700",
    icon: <XCircle size={14} className="text-red-600" />,
  },
};

const BLOCKING_ITEM_LABELS: Record<string, string> = {
  signed_offtake_agreement: "Signed offtake agreement is still missing",
  volume_commitment_letter: "Volume commitment letter has not been secured",
  gabillon_pricing_agreed: "Gabillon-based pricing reference is not yet agreed",
  offtake_term_sheet: "Offtake term sheet is still open",
  spot_reference: "Spot pricing reference is still missing",
};

const BLOCKING_ITEM_REMEDIES: Record<string, string> = {
  signed_offtake_agreement:
    "Convert the current commercial discussion into a signed offtake agreement with delivery and default language.",
  volume_commitment_letter:
    "Obtain a volume commitment letter that fixes minimum annual lift and take-or-pay coverage.",
  gabillon_pricing_agreed:
    "Agree a Gabillon curve and fallback spot mechanism so treasury can defend the price structure.",
  offtake_term_sheet:
    "Close the offtake term sheet before credit discussion and lender model review.",
  spot_reference:
    "Add a clean spot reference and escalation logic to remove pricing ambiguity.",
};

function toResult(score: number): TestResult {
  if (score >= 80) return "PASS";
  if (score >= 50) return "PASS_WITH_NOTE";
  return "FAIL";
}

function clampScore(score: number) {
  return Math.max(5, Math.min(100, Math.round(score)));
}

function deriveOfftakeData(project: CustomerProject): ProjectOfftake {
  const offtakeGate = project.bankability.gates.find(
    (gate) => gate.id === "G4_OFFTAKE_BANKABLE",
  );
  const offtakeScore =
    offtakeGate?.completion_pct ??
    Math.round(project.bankability.overall_completion * 0.7);
  const overall = clampScore(
    offtakeGate ? offtakeScore : project.bankability.overall_completion * 0.8,
  );

  const tests: OfftakeTest[] = [
    {
      id: "TENOR",
      label: "Tenor Match",
      score: clampScore(offtakeScore + 18),
      result: toResult(clampScore(offtakeScore + 18)),
      detail: `${project.name} is still in ${project.phase}. The offtake tenor package needs to align with debt tenor before the project can be presented as fully bankable.`,
    },
    {
      id: "CREDIT",
      label: "Counterparty Credit",
      score: clampScore(project.bankability.overall_completion + 12),
      result: toResult(clampScore(project.bankability.overall_completion + 12)),
      detail: `Counterparty quality is linked to the current commercial package. Lenders will expect credit support, guarantee structure, and buyer obligation strength to be evidenced in the offtake package.`,
    },
    {
      id: "VOLUME_FIRMNESS",
      label: "Volume Firmness",
      score: clampScore(offtakeScore),
      result: toResult(clampScore(offtakeScore)),
      detail:
        offtakeGate?.description ??
        "Volume coverage is not yet firm enough to be treated as contracted revenue.",
    },
    {
      id: "PRICING_INDEXATION",
      label: "Pricing & Indexation",
      score: clampScore(offtakeScore - 5),
      result: toResult(clampScore(offtakeScore - 5)),
      detail:
        project.bankability.risk_alerts.find((alert) =>
          /pricing|spot|gabillon/i.test(alert),
        ) ??
        "Pricing still needs a defendable indexation and fallback mechanism before financial close.",
    },
    {
      id: "CURTAILMENT_SHAPE",
      label: "Curtailment Shape",
      score: clampScore(project.bankability.overall_completion - 10),
      result: toResult(clampScore(project.bankability.overall_completion - 10)),
      detail: `The current offtake structure still needs clearer outage, delivery shortfall, and curtailment language for ${project.molecule} offtake obligations.`,
    },
  ];

  const redFlags = [
    ...(offtakeGate?.blocking_items.map(
      (item) => BLOCKING_ITEM_LABELS[item] ?? item.replace(/_/g, " "),
    ) ?? []),
    ...project.bankability.risk_alerts,
  ].slice(0, 5);

  const remedies =
    offtakeGate?.blocking_items.map(
      (item) =>
        BLOCKING_ITEM_REMEDIES[item] ??
        `Resolve ${item.replace(/_/g, " ")} before lender review.`,
    ) ?? [];

  return {
    overall,
    tests,
    redFlags,
    remedies,
  };
}

function scoreColor(score: number) {
  if (score >= 75) return "#22c55e";
  if (score >= 50) return "#f59e0b";
  return "#ef4444";
}

// Overall quality score ring — 270° arc
function QualityRing({ score }: { score: number }) {
  const size = 120;
  const cx = size / 2;
  const cy = size / 2;
  const r = 46;
  // 270° arc starting at 225° going clockwise
  const startAngle = 225;
  const totalSweep = 270;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const arcEnd = startAngle + totalSweep;
  const arcFill = startAngle + (score / 100) * totalSweep;

  function polar(angle: number) {
    return {
      x: cx + r * Math.cos(toRad(angle)),
      y: cy + r * Math.sin(toRad(angle)),
    };
  }

  const s = polar(startAngle);
  const e = polar(arcEnd);
  const f = polar(arcFill);

  const bgPath = `M ${s.x} ${s.y} A ${r} ${r} 0 1 1 ${e.x} ${e.y}`;
  const fillPath = `M ${s.x} ${s.y} A ${r} ${r} 0 ${arcFill - startAngle > 180 ? 1 : 0} 1 ${f.x} ${f.y}`;

  const color = scoreColor(score);

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <path
        d={bgPath}
        fill="none"
        stroke="#e5e7eb"
        strokeWidth={10}
        strokeLinecap="round"
      />
      <path
        d={fillPath}
        fill="none"
        stroke={color}
        strokeWidth={10}
        strokeLinecap="round"
      />
      <text
        x={cx}
        y={cy - 4}
        textAnchor="middle"
        fontSize={22}
        fontWeight="bold"
        fill={color}
      >
        {score}
      </text>
      <text x={cx} y={cy + 14} textAnchor="middle" fontSize={10} fill="#94a3b8">
        /100
      </text>
    </svg>
  );
}

// Individual score bar
function ScoreBar({ score }: { score: number }) {
  const color = scoreColor(score);
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 rounded-full bg-gray-100 overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${score}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-xs font-bold w-8 text-right" style={{ color }}>
        {score}
      </span>
    </div>
  );
}

// Expandable test card
function TestCard({ test }: { test: OfftakeTest }) {
  const [open, setOpen] = useState(false);
  const meta = RESULT_META[test.result];

  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{ border: "1px solid var(--border, #e2e8f0)" }}
    >
      <button
        className="w-full flex items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-opacity-80"
        style={{ backgroundColor: "var(--surface-raised, #f8fafc)" }}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="shrink-0">{meta.icon}</span>
        <span className="flex-1 font-semibold text-sm flex items-center gap-1">
          {test.label}
          {test.id === "TENOR" && <InfoTooltip text={HELP.TENOR_TEST} />}
          {test.id === "CREDIT" && <InfoTooltip text={HELP.CREDIT_TEST} />}
          {test.id === "VOLUME_FIRMNESS" && (
            <InfoTooltip text={HELP.VOLUME_FIRMNESS} />
          )}
          {test.id === "CURTAILMENT_SHAPE" && (
            <InfoTooltip text={HELP.CURTAILMENT_TEST} />
          )}
        </span>
        <span
          className={`px-2 py-0.5 rounded-full text-xs font-bold ${meta.bg} ${meta.text}`}
        >
          {meta.label}
        </span>
        <div className="w-24 ml-2">
          <ScoreBar score={test.score} />
        </div>
        <span
          className="ml-2 shrink-0"
          style={{ color: "var(--text-muted, #64748b)" }}
        >
          {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </span>
      </button>
      {open && (
        <div
          className="px-4 py-3 text-sm"
          style={{
            borderTop: "1px solid var(--border, #e2e8f0)",
            color: "var(--text-muted, #64748b)",
          }}
        >
          {test.detail}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════

export function OfftakeQuality() {
  const { selectedProjectId, setSelectedProjectId } = useSelectedProject();
  const [data, setData] = useState<ProjectOfftake | null>(null);
  const { projects: visibleProjects } = useVisibleProjects();

  // ABAC: only show projects the current user has rights to
  const project =
    visibleProjects.find((p) => p.id === selectedProjectId) ??
    visibleProjects[0];

  // If the currently selected project is not in the user's visible set, auto-select first visible
  useEffect(() => {
    if (
      visibleProjects.length > 0 &&
      !visibleProjects.find((p) => p.id === selectedProjectId)
    ) {
      setSelectedProjectId(visibleProjects[0].id);
    }
  }, [visibleProjects, selectedProjectId, setSelectedProjectId]);

  useEffect(() => {
    // Demo data fallback — API not available
    const fallbackProject =
      visibleProjects.find((p) => p.id === selectedProjectId) ??
      visibleProjects[0];
    const d =
      OFFTAKE_DATA[selectedProjectId] ??
      (fallbackProject ? OFFTAKE_DATA[fallbackProject.id] : null) ??
      (fallbackProject ? deriveOfftakeData(fallbackProject) : null);
    setData(d ?? null);
  }, [selectedProjectId, visibleProjects]);

  // No visible projects → access denied state
  if (visibleProjects.length === 0) {
    return (
      <div
        className="min-h-screen p-6 flex items-center justify-center"
        style={{ backgroundColor: "var(--surface, #f8fafc)" }}
      >
        <div className="text-center max-w-md">
          <AlertTriangle size={40} className="mx-auto mb-4 text-amber-500" />
          <h2
            className="text-lg font-bold mb-2"
            style={{ color: "var(--text, #0f172a)" }}
          >
            No Projects Available
          </h2>
          <p
            className="text-sm"
            style={{ color: "var(--text-muted, #64748b)" }}
          >
            You do not have access rights to any projects. Contact your
            administrator to request project association.
          </p>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div
        className="min-h-screen p-6 flex items-center justify-center"
        style={{ backgroundColor: "var(--surface, #f8fafc)" }}
      >
        <div className="text-center max-w-md">
          <AlertTriangle size={40} className="mx-auto mb-4 text-amber-500" />
          <h2
            className="text-lg font-bold mb-2"
            style={{ color: "var(--text, #0f172a)" }}
          >
            Offtake assessment unavailable
          </h2>
          <p
            className="text-sm"
            style={{ color: "var(--text-muted, #64748b)" }}
          >
            No offtake quality dataset is available for the current project.
          </p>
        </div>
      </div>
    );
  }

  const hasFlags = data.redFlags.length > 0;
  const hasRemedies = data.remedies.length > 0;

  return (
    <div
      className="min-h-screen p-6"
      style={{
        backgroundColor: "var(--surface, #f8fafc)",
        color: "var(--text, #0f172a)",
      }}
    >
      {/* ── Header ──────────────────────────────────────────── */}
      <div className="mb-6">
        <h1 className="text-xl font-bold mb-1">Offtake Quality Assessment</h1>
        <p className="text-sm" style={{ color: "var(--text-muted, #64748b)" }}>
          {TAB_DESCRIPTIONS.OFFTAKE_QUALITY}
        </p>
      </div>

      {/* ── Project selector + quality ring ─────────────────── */}
      <div
        className="rounded-xl p-5 mb-6 flex flex-col sm:flex-row items-start sm:items-center gap-6"
        style={{
          border: "1px solid var(--border, #e2e8f0)",
          backgroundColor: "var(--surface-raised, #f8fafc)",
        }}
      >
        <div className="flex-1">
          <label
            className="block text-xs font-semibold uppercase tracking-wide mb-2"
            style={{ color: "var(--text-muted, #64748b)" }}
          >
            Project
          </label>
          <select
            value={selectedProjectId}
            onChange={(e) => setSelectedProjectId(e.target.value)}
            className="w-full rounded-lg px-3 py-2 text-sm font-medium focus:outline-none focus:ring-2"
            style={{
              border: "1px solid var(--border, #e2e8f0)",
              backgroundColor: "var(--surface, #fff)",
              color: "var(--text, #0f172a)",
            }}
          >
            {visibleProjects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <p
            className="text-xs mt-2"
            style={{ color: "var(--text-muted, #64748b)" }}
          >
            {project.location} · {project.molecule} · {project.phase}
          </p>
        </div>

        <div className="flex items-center gap-4">
          <QualityRing score={data.overall} />
          <div>
            <p
              className="text-xs font-semibold uppercase tracking-wide mb-1"
              style={{ color: "var(--text-muted, #64748b)" }}
            >
              Overall Offtake Quality
            </p>
            <p
              className="text-2xl font-bold"
              style={{ color: scoreColor(data.overall) }}
            >
              {data.overall}/100
            </p>
            <p
              className="text-xs mt-1"
              style={{ color: "var(--text-muted, #64748b)" }}
            >
              {data.overall >= 80
                ? "Bankable"
                : data.overall >= 60
                  ? "Requires improvement"
                  : data.overall >= 40
                    ? "Significant gaps"
                    : "Not bankable"}
            </p>
          </div>
        </div>
      </div>

      {/* ── Five Test Cards ──────────────────────────────────── */}
      <div className="flex flex-col gap-3 mb-6">
        <h2
          className="text-sm font-bold uppercase tracking-wide"
          style={{ color: "var(--brand, #0ea5e9)" }}
        >
          Five Bankability Tests
        </h2>
        {data.tests.map((test) => (
          <TestCard key={test.id} test={test} />
        ))}
      </div>

      {/* ── Red Flags ────────────────────────────────────────── */}
      {hasFlags && (
        <div
          className="rounded-xl p-5 mb-4"
          style={{ border: "1px solid #fca5a5", backgroundColor: "#fff1f2" }}
        >
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle size={16} className="text-red-600" />
            <h3 className="font-bold text-sm text-red-700 uppercase tracking-wide">
              Red Flags
            </h3>
          </div>
          <ul className="flex flex-col gap-2">
            {data.redFlags.map((flag, i) => (
              <li
                key={i}
                className="flex items-start gap-2 text-sm text-red-700"
              >
                <XCircle size={14} className="mt-0.5 shrink-0 text-red-500" />
                {flag}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Remedies ─────────────────────────────────────────── */}
      {hasRemedies && (
        <div
          className="rounded-xl p-5"
          style={{ border: "1px solid #93c5fd", backgroundColor: "#eff6ff" }}
        >
          <div className="flex items-center gap-2 mb-3">
            <Wrench size={16} className="text-blue-600" />
            <h3 className="font-bold text-sm text-blue-700 uppercase tracking-wide">
              Actionable Remedies
            </h3>
          </div>
          <ul className="flex flex-col gap-2">
            {data.remedies.map((remedy, i) => (
              <li
                key={i}
                className="flex items-start gap-2 text-sm text-blue-700"
              >
                {/* Visual checkbox — not interactive */}
                <span
                  className="mt-0.5 shrink-0 w-4 h-4 rounded border-2 border-blue-400 inline-flex items-center justify-center"
                  style={{ minWidth: 16 }}
                />
                {remedy}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* No flags — confirmation message */}
      {!hasFlags && !hasRemedies && (
        <div
          className="rounded-xl p-4 flex items-center gap-3"
          style={{ border: "1px solid #86efac", backgroundColor: "#f0fdf4" }}
        >
          <CheckCircle2 size={18} className="text-green-600 shrink-0" />
          <p className="text-sm text-green-700 font-medium">
            No red flags identified. Offtake structure meets senior lender
            requirements across all five tests.
          </p>
        </div>
      )}
    </div>
  );
}
