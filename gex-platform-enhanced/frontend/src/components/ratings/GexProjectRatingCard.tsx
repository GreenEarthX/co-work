import React from "react";
import type { ProjectRatingResponse, RatingLetter } from "@/types/projectRating";

// ─── Helpers ──────────────────────────────────────────────────────────────────

const SCORE_MIDPOINTS: Record<RatingLetter, number> = {
  AAA: 96, AA: 88, A: 80, BBB: 72, BB: 64,
  B: 56, CCC: 48, CC: 36, C: 15, D: 0,
};

function positionPct(score: number, scale: RatingLetter[]): number {
  const top    = SCORE_MIDPOINTS[scale[0]];
  const bottom = SCORE_MIDPOINTS[scale[scale.length - 1]];
  if (top === bottom) return 0;
  return Math.min(100, Math.max(0, ((top - score) / (top - bottom)) * 100));
}

function ratingDescriptor(r: RatingLetter): string {
  const MAP: Record<RatingLetter, string> = {
    AAA: "Exceptional", AA: "Very strong", A: "Strong",
    BBB: "Adequate", BB: "Speculative", B: "Highly speculative",
    CCC: "Currently vulnerable", CC: "Very high default risk",
    C: "Near default", D: "Default",
  };
  return MAP[r];
}

function ratingColor(r: RatingLetter): string {
  if (["AAA", "AA", "A"].includes(r))   return "text-emerald-700 dark:text-emerald-400";
  if (["BBB", "BB"].includes(r))         return "text-amber-600 dark:text-amber-400";
  return "text-red-600 dark:text-red-400";
}

function ratingAccent(r: RatingLetter): string {
  if (["AAA", "AA", "A"].includes(r))   return "border-emerald-600 bg-emerald-600 dark:border-emerald-400 dark:bg-emerald-400";
  if (["BBB", "BB"].includes(r))         return "border-amber-500 bg-amber-500";
  return "border-red-500 bg-red-500";
}

// ─── Component ────────────────────────────────────────────────────────────────

interface Props { data: ProjectRatingResponse }

export default function GexProjectRatingCard({ data }: Props) {
  const axisPosition = positionPct(data.final_score, data.displayed_scale);
  const accentDot    = ratingAccent(data.rating);
  const accentText   = ratingColor(data.rating);

  return (
    <div className="w-full max-w-[1000px] rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6 text-[var(--text-primary)] shadow-card dark:bg-slate-900 dark:border-slate-700">

      {/* ── Grid: main content + peer panel ── */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.45fr_0.55fr]">

        {/* ── LEFT ── */}
        <div className="min-w-0">

          {/* Methodology badge */}
          <div className="mb-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">
            {data.methodology_label}
          </div>

          {/* Header row */}
          <div className="flex flex-wrap items-end justify-between gap-4 border-b border-[var(--border)] pb-4 dark:border-slate-700">
            <div>
              <h2 className="font-display text-xl font-bold tracking-tight">{data.project_name}</h2>
              <p className="mt-0.5 text-sm text-[var(--text-secondary)]">{data.phase}</p>
            </div>
            <div className="text-right">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
                Indicative rating
              </div>
              <div className={`font-display text-4xl font-extrabold leading-none tracking-tight ${accentText}`}>
                {data.rating}
              </div>
              <div className="mt-1 text-sm text-[var(--text-secondary)]">
                {ratingDescriptor(data.rating)} · {data.outlook}
              </div>
            </div>
          </div>

          {/* Rating scale strip */}
          <div className="mt-5">
            <div className="mb-1.5 flex items-center justify-between text-xs text-[var(--text-secondary)]">
              <span>Rating scale</span>
              <span className="font-mono font-semibold text-[var(--text-primary)]">
                Score {data.final_score.toFixed(1)}
              </span>
            </div>
            <div className="relative rounded-xl border border-[var(--border)] bg-[var(--surface-muted,#f8fafc)] px-4 pb-5 pt-7 dark:bg-slate-800 dark:border-slate-700">
              <div className="relative h-10">
                {/* Track */}
                <div className="absolute left-0 right-0 top-[18px] h-[2px] bg-slate-200 dark:bg-slate-600" />
                {/* Nodes */}
                {data.displayed_scale.map((label, idx) => {
                  const left   = (idx / Math.max(data.displayed_scale.length - 1, 1)) * 100;
                  const active = label === data.rating;
                  return (
                    <div
                      key={label}
                      className="absolute top-0 -translate-x-1/2"
                      style={{ left: `${left}%` }}
                    >
                      <div className={`mb-2 text-center text-[10px] font-bold ${active ? accentText : "text-slate-400 dark:text-slate-500"}`}>
                        {label}
                      </div>
                      <div className={`mx-auto h-3 w-3 rounded-full border-2 ${active ? accentDot : "border-slate-300 bg-white dark:border-slate-600 dark:bg-slate-800"}`} />
                    </div>
                  );
                })}
                {/* Score needle */}
                <div
                  className={`absolute top-[6px] h-7 w-[2px] rounded-full ${accentDot.replace("bg-", "bg-").split(" ")[1]}`}
                  style={{ left: `${axisPosition}%` }}
                />
              </div>
            </div>
          </div>

          {/* Strengths + Constraints */}
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            {[
              { label: "Main strengths",   items: data.key_strengths,   dot: "bg-emerald-500" },
              { label: "Main constraints", items: data.key_constraints, dot: "bg-amber-500" },
            ].map(({ label, items, dot }) => (
              <div key={label} className="rounded-xl border border-[var(--border)] p-4 dark:border-slate-700">
                <div className="mb-3 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--text-muted)]">
                  {label}
                </div>
                <ul className="space-y-2">
                  {items.map((item) => (
                    <li key={item} className="flex gap-2.5 text-sm text-[var(--text-secondary)]">
                      <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          {/* Rating mechanics */}
          <div className="mt-5 rounded-xl border border-[var(--border)] p-4 dark:border-slate-700">
            <div className="mb-3 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--text-muted)]">
              Rating mechanics
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
              {[
                { label: "Base score",    value: data.base_score.toFixed(1) },
                { label: "Modifiers",     value: (data.modifier_points >= 0 ? "+" : "") + data.modifier_points.toFixed(1) },
                { label: "Preliminary",   value: data.preliminary_score.toFixed(1) },
                { label: "Cap status",    value: data.cap_reason },
              ].map(({ label, value }) => (
                <div key={label}>
                  <div className="text-[var(--text-muted)] text-xs">{label}</div>
                  <div className="mt-0.5 font-mono font-semibold text-[var(--text-primary)]">{value}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ── RIGHT — Peer panel ── */}
        <div className="rounded-2xl border border-[var(--border)] bg-slate-50 p-4 dark:bg-slate-800 dark:border-slate-700">
          <div className="mb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--text-muted)]">
            Relative peer position
          </div>
          <div className="mb-4 text-xs text-[var(--text-secondary)]">
            Anonymous · {data.peer_count} projects
          </div>

          {/* Y-axis labels */}
          <div className="flex items-start gap-3">
            <div className="flex h-[280px] w-8 flex-col justify-between text-[9px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
              <span>Top</span>
              <span>Mid</span>
              <span>Low</span>
            </div>

            {/* Bar chart */}
            <div className="relative h-[280px] flex-1 overflow-hidden rounded-xl border border-[var(--border)] bg-white px-4 py-3 dark:bg-slate-900 dark:border-slate-700">
              <div className="flex h-full flex-col justify-between">
                {data.anonymous_peer_scores.map((score, idx) => {
                  const isCurrent = Math.abs(score - data.final_score) < 0.0001;
                  const barPct    = Math.max(8, Math.min(100, ((score - 40) / 60) * 100));
                  return (
                    <div key={`${score}-${idx}`} className="flex items-center gap-2">
                      <div
                        className={`h-[5px] rounded-full transition-all ${isCurrent ? "bg-brand-500" : "bg-slate-200 dark:bg-slate-700"}`}
                        style={{ width: `${barPct}%` }}
                      />
                      {isCurrent && (
                        <span className="whitespace-nowrap text-[9px] font-bold text-brand-600 dark:text-brand-400">
                          #{data.current_rank}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Rank summary */}
          <div className="mt-4 rounded-xl border border-[var(--border)] bg-white p-3 text-xs text-[var(--text-secondary)] dark:bg-slate-900 dark:border-slate-700">
            Ranked{" "}
            <span className="font-mono font-bold text-[var(--text-primary)]">#{data.current_rank}</span>
            {" "}of{" "}
            <span className="font-mono font-bold text-[var(--text-primary)]">{data.peer_count}</span>
            {" "}active projects.
          </div>
        </div>

      </div>
    </div>
  );
}
