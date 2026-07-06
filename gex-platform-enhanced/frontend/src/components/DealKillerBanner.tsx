// Screen: Shared component — Finance screens with deal-killer alerts
/**
 * DealKillerBanner — R1 (Architectural Reform v6.0)
 *
 * Non-dismissable red banner that renders at the TOP of every workspace
 * page when one or more deal-killers are ACTIVE on the selected project.
 *
 * Visible to all actors who have visibility to the affected gates.
 * Cannot be dismissed — it persists until the killer is RESOLVED or WAIVED.
 *
 * Usage:
 *   <DealKillerBanner killers={activeKillers} />
 */

import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useUserRole } from "@/contexts/UserRoleContext";
import { canAccessGate } from "@/config/gateAccess";

// ─── Types ────────────────────────────────────────────────────────────────────

export type KillerSeverity = "FATAL" | "CRITICAL";

export interface ActiveKiller {
  id: string;
  gate: string;
  severity: KillerSeverity;
  plain_language: string;
  action: string;
  page: string;
}

interface DealKillerBannerProps {
  killers: ActiveKiller[];
  /** Project name for display context */
  projectName?: string;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function DealKillerBanner({
  killers,
  projectName,
}: DealKillerBannerProps) {
  const navigate = useNavigate();
  const { role } = useUserRole();
  const visibleKillers = useMemo(
    () => killers.filter((killer) => canAccessGate(role, killer.gate)),
    [killers, role],
  );
  const hiddenCount = killers.length - visibleKillers.length;

  if (visibleKillers.length === 0) return null;

  const fatalCount = visibleKillers.filter(
    (killer) => killer.severity === "FATAL",
  ).length;
  const criticalCount = visibleKillers.filter(
    (killer) => killer.severity === "CRITICAL",
  ).length;
  const headlineParts = [
    `${visibleKillers.length} ACTIVE BLOCKER${visibleKillers.length > 1 ? "S" : ""}`,
    fatalCount > 0 ? `${fatalCount} FATAL` : null,
    criticalCount > 0 ? `${criticalCount} CRITICAL` : null,
  ].filter(Boolean);

  const headline = headlineParts.join(" · ");

  // Left band color is taken from the highest active severity.
  const bandClass = fatalCount > 0 ? "border-l-red-700" : "border-l-amber-600";

  return (
    <section
      role="alert"
      aria-live="assertive"
      className={`w-full border border-l-2 border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 ${bandClass}`}
    >
      {/* Header row */}
      <header className="flex items-baseline justify-between gap-2 border-b border-slate-200 dark:border-slate-800 px-2 py-1">
        <div className="flex items-baseline gap-2 min-w-0">
          <span className="font-mono text-[10px] uppercase tracking-[0.12em] font-bold text-slate-900 dark:text-slate-100 whitespace-nowrap">
            {headline}
          </span>
          {projectName && (
            <span className="font-mono text-[10px] text-slate-500 dark:text-slate-400 truncate">
              · {projectName}
            </span>
          )}
        </div>
        <span className="font-mono text-[9px] uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400 select-none whitespace-nowrap">
          cannot be dismissed
        </span>
      </header>

      {/* Killer list */}
      <ul className="divide-y divide-slate-100 dark:divide-slate-900">
        {visibleKillers.map((killer) => {
          const sevTone = killer.severity === "FATAL"
            ? "border-l-red-700 text-red-800 dark:text-red-300"
            : "border-l-amber-600 text-amber-800 dark:text-amber-300";
          return (
            <li
              key={killer.id}
              className="grid grid-cols-[68px_minmax(0,1fr)_60px] items-center gap-2 px-2 py-1.5 hover:bg-slate-50 dark:hover:bg-slate-900"
            >
              <span
                className={`inline-flex h-[15px] items-center justify-center border border-l-2 border-slate-300 bg-white dark:bg-slate-950 px-1 font-mono text-[8px] font-bold uppercase tracking-[0.08em] leading-none whitespace-nowrap ${sevTone}`}
              >
                {killer.severity}
              </span>
              <span className="font-mono text-[11px] text-slate-800 dark:text-slate-200 leading-snug min-w-0">
                {killer.plain_language}
              </span>
              {killer.page ? (
                <button
                  onClick={() => navigate(killer.page)}
                  className="justify-self-end font-mono text-[10px] uppercase tracking-[0.08em] text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-slate-100 hover:underline whitespace-nowrap"
                >
                  resolve →
                </button>
              ) : <span />}
            </li>
          );
        })}
      </ul>

      {/* Footer notes */}
      {(fatalCount > 0 || hiddenCount > 0) && (
        <footer className="border-t border-slate-200 dark:border-slate-800 px-2 py-1 space-y-0.5">
          {fatalCount > 0 && (
            <p className="font-mono text-[10px] text-slate-600 dark:text-slate-400">
              IC Pack export, committee-ready signal, and capital unlock classification are blocked until all FATAL killers are resolved.
            </p>
          )}
          {hiddenCount > 0 && (
            <p className="font-mono text-[10px] text-slate-600 dark:text-slate-400">
              {hiddenCount} blocker{hiddenCount > 1 ? "s" : ""} outside your current gate scope.
            </p>
          )}
        </footer>
      )}
    </section>
  );
}

// ─── Hook: fetch active killers for a project ─────────────────────────────────

export function useActiveKillers(projectId: string | undefined): {
  killers: ActiveKiller[];
  loading: boolean;
} {
  const [killers, setKillers] = useState<ActiveKiller[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!projectId) return;
    setLoading(true);

    fetch(`/api/v1/deal-killers/${projectId}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r)))
      .then((data: { active_killers: ActiveKiller[] }) => {
        setKillers(data.active_killers);
      })
      .catch(() => {
        // Demo fallback — representative killers for demo projects
        setKillers(DEMO_KILLERS);
      })
      .finally(() => setLoading(false));
  }, [projectId]);

  return { killers, loading };
}

// Demo data — used when API is unavailable
const DEMO_KILLERS: ActiveKiller[] = [
  {
    id: "DK_G5_NO_EPC",
    gate: "G5",
    severity: "FATAL",
    plain_language:
      "No EPC or EPCM contract has been executed — construction cannot proceed without a signed engineering, procurement, and construction agreement.",
    action: "Execute an EPC or EPCM contract with an approved contractor.",
    page: "/finance/stage-gates",
  },
  {
    id: "DK_G8_NO_AUDIT_MODEL",
    gate: "G8",
    severity: "FATAL",
    plain_language:
      "The financial model has not been verified to audit grade — credit committees require an independently reviewed, audited model before approving debt.",
    action: "Commission a financial model audit from a named firm.",
    page: "/finance/bankability",
  },
];
