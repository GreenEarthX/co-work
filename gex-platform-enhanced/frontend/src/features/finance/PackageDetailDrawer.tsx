// Screen: package detail drawer (opened from the register) — bridge Stop 3.
/**
 * PackageDetailDrawer — mature a package's cost basis and advance its state.
 *
 * Stop 3 is "cost maturity": a package starts at IDENTIFIED with a rough Class-5
 * number and is walked forward — scoped, then costed — while the estimate is
 * sharpened toward the Class-3 that FID demands, and P10/P50/P90 are recorded.
 *
 * Two governed actions, both audited server-side:
 *   • PATCH /packages/{id}          — edit cost basis (estimate_class change
 *                                     auto-appends to the AACE class history)
 *   • POST  /packages/{id}/transition — advance one step along the ladder; the
 *                                     server enforces forward-only + the guards
 *                                     for each target state (shown verbatim).
 */

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { X, Loader2, AlertTriangle, Check, ArrowRight, Pencil, Upload, FileText } from "lucide-react";
import {
  packagesAPI,
  type PackageUpdateInput,
  type PackageTransitionInput,
} from "@/api";

// Linear state machine — mirrors backend VALID_TRANSITIONS.
const LADDER = [
  "identified", "scoped", "costed", "evidenced", "eligible", "approved",
  "committed", "drawable", "drawn", "verified", "closed", "propagated",
];
const ESTIMATE_CLASSES = ["CLASS_5", "CLASS_4", "CLASS_3", "CLASS_2", "CLASS_1"];
const CLASS_BAND: Record<string, string> = {
  CLASS_5: "±50% · concept", CLASS_4: "±30% · feasibility", CLASS_3: "±20% · FID-support",
  CLASS_2: "±15% · control", CLASS_1: "±10% · check",
};

export interface PackageDetail {
  package_id: string;
  package_name: string;
  package_type: string;
  phase_required: string;
  workflow_state: string;
  capital_status: string;
  capital_eligible?: string[];
  cost_amount: number;
  cost_p10?: number | null;
  cost_p90?: number | null;
  estimate_class: string;
  gex_gate?: string | null;
  downstream_effect?: string[];
  unlock_condition?: string[];
  aace_class_history?: { class: string; date: string }[];
  version: number;
}

// Bankability gates a package can feed (short form stored on the package).
const GATES = ["G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10", "G11"];

// Capital-engagement ladder (orthogonal to workflow maturity).
const CAPITAL_LADDER = [
  "NOT_ELIGIBLE", "THEORETICALLY_ELIGIBLE", "INDICATED", "COMMITTED", "DRAWABLE", "DRAWN",
];
const CAPITAL_LABEL: Record<string, string> = {
  NOT_ELIGIBLE: "Not eligible", THEORETICALLY_ELIGIBLE: "Theoretically eligible",
  INDICATED: "Indicated", COMMITTED: "Committed", DRAWABLE: "Drawable", DRAWN: "Drawn",
};
// Steps a funder (not the developer) must perform — surfaced as an honest note.
const CAPITAL_NEEDS_FUNDER = new Set(["COMMITTED", "DRAWABLE", "DRAWN"]);

const inputClass =
  "w-full rounded border border-[var(--border)] bg-[var(--surface)] px-2.5 py-[7px] text-sm text-[var(--text-primary)] focus:border-[var(--brand)] focus:outline-none";

const fmtEur = (n?: number | null) =>
  n == null ? "—" : n >= 1_000_000 ? `€${(n / 1_000_000).toFixed(2)}M` : `€${(n / 1_000).toFixed(0)}k`;

// Keep audit-trail values readable — long list/JSON values are clipped.
const clip = (v: unknown) => {
  const s = v == null ? "—" : String(v);
  return s.length > 60 ? s.slice(0, 60) + "…" : s;
};

export function PackageDetailDrawer({
  pkg,
  changedBy,
  actorType,
  onClose,
  onChanged,
}: {
  pkg: PackageDetail;
  changedBy: string;
  actorType: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const idx = LADDER.indexOf(pkg.workflow_state);
  const nextState = idx >= 0 && idx < LADDER.length - 1 ? LADDER[idx + 1] : null;

  // ── Cost basis editor ──
  const [editing, setEditing] = useState(false);
  const [p10, setP10] = useState(pkg.cost_p10?.toString() ?? "");
  const [p50, setP50] = useState(pkg.cost_amount?.toString() ?? "");
  const [p90, setP90] = useState(pkg.cost_p90?.toString() ?? "");
  const [estClass, setEstClass] = useState(pkg.estimate_class);
  const [costErr, setCostErr] = useState<string | null>(null);

  const saveCost = useMutation({
    mutationFn: (body: PackageUpdateInput) => packagesAPI.update(pkg.package_id, body),
    onSuccess: () => { setEditing(false); onChanged(); },
    onError: (e: unknown) => setCostErr(e instanceof Error ? e.message : "Could not save"),
  });

  // ── Unlocks & dependencies editor ──
  const [editLinks, setEditLinks] = useState(false);
  const [gexGate, setGexGate] = useState(pkg.gex_gate ?? "");
  const [downstream, setDownstream] = useState((pkg.downstream_effect ?? []).join(", "));
  const [unlockCond, setUnlockCond] = useState((pkg.unlock_condition ?? []).join(", "));
  const [linksErr, setLinksErr] = useState<string | null>(null);
  const splitList = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
  const saveLinks = useMutation({
    mutationFn: (body: PackageUpdateInput) => packagesAPI.update(pkg.package_id, body),
    onSuccess: () => { setEditLinks(false); onChanged(); },
    onError: (e: unknown) => setLinksErr(e instanceof Error ? e.message : "Could not save"),
  });

  // ── Advance state ──
  const [advancing, setAdvancing] = useState(false);
  const [justification, setJustification] = useState("");
  const [advErr, setAdvErr] = useState<string | null>(null);

  const advance = useMutation({
    mutationFn: (body: PackageTransitionInput) => packagesAPI.transition(pkg.package_id, body),
    onSuccess: () => { setAdvancing(false); setJustification(""); onChanged(); },
    onError: (e: unknown) => setAdvErr(e instanceof Error ? e.message : "Could not advance"),
  });

  // ── Capital engagement (orthogonal axis) ──
  const capIdx = CAPITAL_LADDER.indexOf(pkg.capital_status);
  const nextCapital = capIdx >= 0 && capIdx < CAPITAL_LADDER.length - 1 ? CAPITAL_LADDER[capIdx + 1] : null;
  const [capAdvancing, setCapAdvancing] = useState(false);
  const [capJust, setCapJust] = useState("");
  const [capErr, setCapErr] = useState<string | null>(null);
  const advanceCapital = useMutation({
    mutationFn: (body: { new_status: string; changed_by: string; actor_type: string; justification: string }) =>
      packagesAPI.capitalTransition(pkg.package_id, body),
    onSuccess: () => { setCapAdvancing(false); setCapJust(""); onChanged(); },
    onError: (e: unknown) => setCapErr(e instanceof Error ? e.message : "Could not advance capital status"),
  });

  // ── Evidence documents ──
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [evTitle, setEvTitle] = useState("");
  const [evErr, setEvErr] = useState<string | null>(null);
  const { data: evidence = [] } = useQuery<any[]>({
    queryKey: ["packages", pkg.package_id, "evidence"],
    queryFn: () => packagesAPI.listEvidence(pkg.package_id).then((r) => r.documents ?? []),
  });
  const uploadEvidence = useMutation({
    mutationFn: ({ file, title }: { file: File; title: string }) =>
      packagesAPI.uploadEvidence(pkg.package_id, file, title),
    onSuccess: () => {
      setEvTitle("");
      if (fileRef.current) fileRef.current.value = "";
      queryClient.invalidateQueries({ queryKey: ["packages", pkg.package_id, "evidence"] });
      onChanged();
    },
    onError: (e: unknown) => setEvErr(e instanceof Error ? e.message : "Upload failed"),
  });

  // ── Audit trail ──
  const { data: events = [] } = useQuery<any[]>({
    queryKey: ["packages", pkg.package_id, "events"],
    queryFn: () => packagesAPI.events(pkg.package_id),
  });

  const history = pkg.aace_class_history ?? [];

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="relative flex h-full w-full max-w-md flex-col overflow-y-auto border-l border-[var(--border)] bg-[var(--surface)] shadow-xl">
        <div className="flex items-start justify-between gap-3 border-b border-[var(--border)] p-4">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--text-muted)]">
              {pkg.package_type} · {pkg.phase_required} · v{pkg.version}
            </div>
            <h2 className="font-display text-base font-bold text-[var(--text-primary)]">{pkg.package_name}</h2>
          </div>
          <button type="button" onClick={onClose} className="rounded p-1 text-[var(--text-muted)] hover:bg-[var(--surface-hover)]">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-5 p-4">
          {/* ── Cost basis ── */}
          <section>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">Cost basis</h3>
              {!editing && (
                <button type="button" onClick={() => { setEditing(true); setCostErr(null); }}
                  className="inline-flex items-center gap-1 text-xs text-[var(--brand)] hover:underline">
                  <Pencil className="h-3 w-3" /> Edit
                </button>
              )}
            </div>

            {!editing ? (
              <div className="grid grid-cols-3 gap-2">
                <Stat label="P10" value={fmtEur(pkg.cost_p10)} />
                <Stat label="P50" value={fmtEur(pkg.cost_amount)} />
                <Stat label="P90" value={fmtEur(pkg.cost_p90)} />
                <div className="col-span-3 mt-1 text-[11px] text-[var(--text-secondary)]">
                  Estimate: <span className="font-mono font-semibold">{pkg.estimate_class.replace("CLASS_", "Class ")}</span>{" "}
                  <span className="text-[var(--text-muted)]">({CLASS_BAND[pkg.estimate_class]})</span>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="grid grid-cols-3 gap-2">
                  <Labeled label="P10 (optimistic)"><input className={inputClass} type="number" value={p10} onChange={(e) => setP10(e.target.value)} /></Labeled>
                  <Labeled label="P50 (base)"><input className={inputClass} type="number" value={p50} onChange={(e) => setP50(e.target.value)} /></Labeled>
                  <Labeled label="P90 (pessimistic)"><input className={inputClass} type="number" value={p90} onChange={(e) => setP90(e.target.value)} /></Labeled>
                </div>
                <Labeled label="Estimate class (sharpen toward Class 3 for FID)">
                  <select className="gex-select w-full" value={estClass} onChange={(e) => setEstClass(e.target.value)}>
                    {ESTIMATE_CLASSES.map((c) => <option key={c} value={c}>{c.replace("CLASS_", "Class ")} — {CLASS_BAND[c]}</option>)}
                  </select>
                </Labeled>
                {costErr && <ErrorLine msg={costErr} />}
                <div className="flex justify-end gap-2">
                  <button type="button" onClick={() => setEditing(false)} className="rounded border border-[var(--border)] px-2.5 py-1.5 text-xs text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]">Cancel</button>
                  <button type="button" disabled={saveCost.isPending || !(Number(p50) > 0)}
                    onClick={() => { setCostErr(null); saveCost.mutate({ changed_by: changedBy, cost_amount: Number(p50), cost_p10: p10 ? Number(p10) : undefined, cost_p90: p90 ? Number(p90) : undefined, estimate_class: estClass }); }}
                    className="inline-flex items-center gap-1 rounded bg-[var(--brand)] px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50">
                    {saveCost.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />} Save cost basis
                  </button>
                </div>
              </div>
            )}

            {history.length > 0 && (
              <div className="mt-3">
                <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--text-muted)]">AACE class history</div>
                <ol className="mt-1 space-y-0.5">
                  {history.map((h, i) => (
                    <li key={i} className="flex justify-between text-[11px] text-[var(--text-secondary)]">
                      <span className="font-mono">{h.class.replace("CLASS_", "Class ")}</span>
                      <span className="text-[var(--text-muted)]">{(h.date || "").slice(0, 10)}</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </section>

          {/* ── Evidence ── */}
          <section>
            <h3 className="mb-2 text-sm font-semibold text-[var(--text-primary)]">
              Evidence <span className="font-normal text-[11px] text-[var(--text-muted)]">· a document, content-addressed by SHA-256</span>
            </h3>
            {evidence.length === 0 ? (
              <p className="text-[12px] text-[var(--text-secondary)]">
                No documents yet. Evidence without a document is a claim — attach one to unlock the
                <span className="font-mono"> evidenced</span> step.
              </p>
            ) : (
              <ol className="space-y-1">
                {evidence.map((d, i) => (
                  <li key={i} className="flex items-start gap-2 rounded bg-[var(--surface-muted)] px-2 py-1.5 text-[12px]">
                    <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--text-muted)]" />
                    <div className="min-w-0">
                      <div className="truncate font-medium text-[var(--text-primary)]">{d.title || d.filename}</div>
                      <div className="font-mono text-[10px] text-[var(--text-muted)]">
                        sha256 {String(d.sha256).slice(0, 16)}… · {(d.uploaded_by || "")} · {(d.uploaded_at || "").slice(0, 10)}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            )}
            <div className="mt-2 space-y-2">
              <input className={inputClass} placeholder="Document title (e.g. Owner's Engineer SoW)" value={evTitle} onChange={(e) => setEvTitle(e.target.value)} />
              <input ref={fileRef} type="file" className="block w-full text-[12px] text-[var(--text-secondary)] file:mr-2 file:rounded file:border-0 file:bg-[var(--surface-muted)] file:px-2 file:py-1 file:text-[12px] file:text-[var(--text-primary)]" />
              {evErr && <ErrorLine msg={evErr} />}
              <button type="button" disabled={uploadEvidence.isPending}
                onClick={() => { setEvErr(null); const f = fileRef.current?.files?.[0]; if (!f) { setEvErr("Choose a file to attach."); return; } uploadEvidence.mutate({ file: f, title: evTitle.trim() }); }}
                className="inline-flex items-center gap-1.5 rounded bg-[var(--brand)] px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50">
                {uploadEvidence.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />} Attach document
              </button>
            </div>
          </section>

          {/* ── Unlocks & dependencies ── */}
          <section>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">Unlocks & dependencies</h3>
              {!editLinks && (
                <button type="button" onClick={() => { setEditLinks(true); setLinksErr(null); }}
                  className="inline-flex items-center gap-1 text-xs text-[var(--brand)] hover:underline">
                  <Pencil className="h-3 w-3" /> Edit
                </button>
              )}
            </div>
            {!editLinks ? (
              <dl className="space-y-1 text-[12px]">
                <div className="flex gap-2"><dt className="w-28 shrink-0 text-[var(--text-muted)]">Feeds gate</dt>
                  <dd className="font-mono text-[var(--text-primary)]">{pkg.gex_gate || <span className="text-[var(--text-muted)]">— none declared</span>}</dd></div>
                <div className="flex gap-2"><dt className="w-28 shrink-0 text-[var(--text-muted)]">Unlocks</dt>
                  <dd className="text-[var(--text-secondary)]">{(pkg.downstream_effect ?? []).join(", ") || <span className="text-[var(--text-muted)]">—</span>}</dd></div>
                <div className="flex gap-2"><dt className="w-28 shrink-0 text-[var(--text-muted)]">Drawdown waits on</dt>
                  <dd className="text-[var(--text-secondary)]">{(pkg.unlock_condition ?? []).join(", ") || <span className="text-[var(--text-muted)]">—</span>}</dd></div>
              </dl>
            ) : (
              <div className="space-y-2">
                <Labeled label="Feeds bankability gate">
                  <select className="gex-select w-full" value={gexGate} onChange={(e) => setGexGate(e.target.value)}>
                    <option value="">— none —</option>
                    {GATES.map((g) => <option key={g} value={g}>{g}</option>)}
                  </select>
                </Labeled>
                <Labeled label="Unlocks (downstream gates/packages, comma-separated)">
                  <input className={inputClass} value={downstream} onChange={(e) => setDownstream(e.target.value)} placeholder="e.g. G1_GRID_WATER" />
                </Labeled>
                <Labeled label="Drawdown waits on (evidence/gate IDs, comma-separated)">
                  <input className={inputClass} value={unlockCond} onChange={(e) => setUnlockCond(e.target.value)} placeholder="e.g. permit_grant, G9" />
                </Labeled>
                {linksErr && <ErrorLine msg={linksErr} />}
                <div className="flex justify-end gap-2">
                  <button type="button" onClick={() => setEditLinks(false)} className="rounded border border-[var(--border)] px-2.5 py-1.5 text-xs text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]">Cancel</button>
                  <button type="button" disabled={saveLinks.isPending}
                    onClick={() => { setLinksErr(null); saveLinks.mutate({ changed_by: changedBy, gex_gate: gexGate || undefined, downstream_effect: splitList(downstream), unlock_condition: splitList(unlockCond) }); }}
                    className="inline-flex items-center gap-1 rounded bg-[var(--brand)] px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50">
                    {saveLinks.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />} Save links
                  </button>
                </div>
              </div>
            )}
          </section>

          {/* ── Maturity ladder ── */}
          <section>
            <h3 className="mb-2 text-sm font-semibold text-[var(--text-primary)]">Maturity</h3>
            <ol className="space-y-0.5">
              {LADDER.map((s, i) => {
                const done = i < idx, current = i === idx;
                return (
                  <li key={s} className="flex items-center gap-2 text-[12px]">
                    <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[9px] ${done ? "bg-[var(--brand)] text-white" : current ? "ring-2 ring-[var(--brand)] text-[var(--brand)]" : "bg-[var(--surface-muted)] text-[var(--text-muted)]"}`}>
                      {done ? <Check className="h-2.5 w-2.5" /> : i + 1}
                    </span>
                    <span className={`font-mono ${current ? "font-bold text-[var(--text-primary)]" : done ? "text-[var(--text-secondary)]" : "text-[var(--text-muted)]"}`}>{s}</span>
                    {current && <span className="ml-1 rounded bg-[var(--brand)]/10 px-1.5 text-[10px] text-[var(--brand)]">current</span>}
                  </li>
                );
              })}
            </ol>

            {nextState && !advancing && (
              <button type="button" onClick={() => { setAdvancing(true); setAdvErr(null); }}
                className="mt-3 inline-flex items-center gap-1.5 rounded bg-[var(--brand)] px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90">
                <ArrowRight className="h-3.5 w-3.5" /> Advance to {nextState}
              </button>
            )}
            {nextState && advancing && (
              <div className="mt-3 space-y-2 rounded border border-[var(--border)] p-3">
                <div className="text-xs font-semibold text-[var(--text-primary)]">Advance {pkg.workflow_state} → {nextState}</div>
                <textarea className={`${inputClass} min-h-[64px]`} placeholder="Justification (≥10 chars) — what was done to reduce this uncertainty?"
                  value={justification} onChange={(e) => setJustification(e.target.value)} />
                {advErr && <ErrorLine msg={advErr} />}
                <div className="flex justify-end gap-2">
                  <button type="button" onClick={() => { setAdvancing(false); setAdvErr(null); }} className="rounded border border-[var(--border)] px-2.5 py-1.5 text-xs text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]">Cancel</button>
                  <button type="button" disabled={advance.isPending || justification.trim().length < 10}
                    onClick={() => { setAdvErr(null); advance.mutate({ new_state: nextState, changed_by: changedBy, actor_type: actorType, justification: justification.trim() }); }}
                    className="inline-flex items-center gap-1 rounded bg-[var(--brand)] px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50">
                    {advance.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <ArrowRight className="h-3 w-3" />} Confirm
                  </button>
                </div>
              </div>
            )}
          </section>

          {/* ── Capital engagement (orthogonal to maturity) ── */}
          <section>
            <h3 className="mb-1 text-sm font-semibold text-[var(--text-primary)]">Capital engagement</h3>
            <p className="mb-2 text-[11px] text-[var(--text-muted)]">
              A separate ladder from maturity: not "is the knowledge good?" but "is a real funder engaging?".
              {pkg.capital_eligible && pkg.capital_eligible.length > 0 && (
                <> Eligible sources: <span className="font-mono text-[var(--text-secondary)]">{pkg.capital_eligible.join(", ")}</span>.</>
              )}
            </p>
            <ol className="space-y-0.5">
              {CAPITAL_LADDER.map((s, i) => {
                const done = i < capIdx, current = i === capIdx;
                return (
                  <li key={s} className="flex items-center gap-2 text-[12px]">
                    <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[9px] ${done ? "bg-amber-500 text-white" : current ? "ring-2 ring-amber-500 text-amber-600" : "bg-[var(--surface-muted)] text-[var(--text-muted)]"}`}>
                      {done ? <Check className="h-2.5 w-2.5" /> : i + 1}
                    </span>
                    <span className={`${current ? "font-bold text-[var(--text-primary)]" : done ? "text-[var(--text-secondary)]" : "text-[var(--text-muted)]"}`}>{CAPITAL_LABEL[s]}</span>
                    {current && <span className="ml-1 rounded bg-amber-500/10 px-1.5 text-[10px] text-amber-600">current</span>}
                    {CAPITAL_NEEDS_FUNDER.has(s) && !done && (
                      <span className="ml-1 text-[10px] text-[var(--text-muted)]">· funder action</span>
                    )}
                  </li>
                );
              })}
            </ol>

            {nextCapital && !capAdvancing && (
              <button type="button" onClick={() => { setCapAdvancing(true); setCapErr(null); }}
                className="mt-3 inline-flex items-center gap-1.5 rounded bg-amber-500 px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90">
                <ArrowRight className="h-3.5 w-3.5" /> Advance to {CAPITAL_LABEL[nextCapital]}
              </button>
            )}
            {nextCapital && CAPITAL_NEEDS_FUNDER.has(nextCapital) && (
              <p className="mt-2 text-[11px] text-[var(--text-muted)]">
                {CAPITAL_LABEL[nextCapital]} is a funder action — it requires a different party with a
                risk-absorbing role (bank, DFI, insurer) under four-eyes. The developer cannot self-commit
                capital; if you try, the server will say exactly who is needed.
              </p>
            )}
            {nextCapital && capAdvancing && (
              <div className="mt-3 space-y-2 rounded border border-[var(--border)] p-3">
                <div className="text-xs font-semibold text-[var(--text-primary)]">Advance {CAPITAL_LABEL[pkg.capital_status]} → {CAPITAL_LABEL[nextCapital]}</div>
                <textarea className={`${inputClass} min-h-[64px]`} placeholder="Justification (≥10 chars) — what changed in the capital engagement?"
                  value={capJust} onChange={(e) => setCapJust(e.target.value)} />
                {capErr && <ErrorLine msg={capErr} />}
                <div className="flex justify-end gap-2">
                  <button type="button" onClick={() => { setCapAdvancing(false); setCapErr(null); }} className="rounded border border-[var(--border)] px-2.5 py-1.5 text-xs text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]">Cancel</button>
                  <button type="button" disabled={advanceCapital.isPending || capJust.trim().length < 10}
                    onClick={() => { setCapErr(null); advanceCapital.mutate({ new_status: nextCapital, changed_by: changedBy, actor_type: actorType, justification: capJust.trim() }); }}
                    className="inline-flex items-center gap-1 rounded bg-amber-500 px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50">
                    {advanceCapital.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <ArrowRight className="h-3 w-3" />} Confirm
                  </button>
                </div>
              </div>
            )}
          </section>

          {/* ── Audit trail ── */}
          {events.length > 0 && (
            <section>
              <h3 className="mb-2 text-sm font-semibold text-[var(--text-primary)]">Audit trail</h3>
              <ol className="space-y-1">
                {events.slice().reverse().map((e, i) => (
                  <li key={i} className="rounded bg-[var(--surface-muted)] px-2 py-1 text-[11px]">
                    <span className="font-mono text-[var(--text-primary)]">{e.event_type || "event"}</span>
                    {e.field_changed && <span className="text-[var(--text-secondary)]"> · {e.field_changed}: {clip(e.old_value)} → {clip(e.new_value)}</span>}
                    <div className="text-[var(--text-muted)]">{(e.changed_by || "")} · {(e.created_at || "").slice(0, 16).replace("T", " ")}</div>
                  </li>
                ))}
              </ol>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-[var(--border)] px-2 py-1.5">
      <div className="font-mono text-[10px] uppercase text-[var(--text-muted)]">{label}</div>
      <div className="font-mono text-sm font-semibold text-[var(--text-primary)]">{value}</div>
    </div>
  );
}
function Labeled({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-[11px] font-medium text-[var(--text-secondary)]">{label}</span>
      <div className="mt-0.5">{children}</div>
    </label>
  );
}
function ErrorLine({ msg }: { msg: string }) {
  return (
    <div className="flex items-start gap-1.5 rounded border border-rose-300 bg-rose-50 px-2 py-1.5 text-[12px] text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> <span>{msg}</span>
    </div>
  );
}

export default PackageDetailDrawer;
