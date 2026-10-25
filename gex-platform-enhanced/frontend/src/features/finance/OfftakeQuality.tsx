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
import { useProjectDataset, DatasetNotice, UnverifiedBadge } from "./useProjectDataset";

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
  // project_dataset offtake_quality (PostgreSQL since 2026-10-25), UNVERIFIED.
  // It used to fall back to the first visible project's dataset, and then to
  // scores invented from gate completion (+18, +12, −5 …).
  const ds = useProjectDataset<ProjectOfftake>("offtake_quality", selectedProjectId);
  const data = ds.data;
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

  if (ds.loading || ds.error) return <DatasetNotice ds={ds} what="offtake quality assessment" />;

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
            No offtake quality assessment is recorded for this project yet.
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
        <h1 className="text-xl font-bold mb-1 flex items-center gap-2">Offtake Quality Assessment <UnverifiedBadge verification={ds.verification} /></h1>
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
